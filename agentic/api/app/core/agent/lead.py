from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from time import perf_counter
from typing import Any

from app.core.agent.lead_decision import LeadDecisionCompleted, LeadDecisionPolicy
from app.core.browser.base import Browser
from app.core.entities.app_config import AgentConfig
from app.core.entities.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    InteractionEvent,
    MessageDeltaEvent,
    MessageEvent,
    PlanEvent,
    PlanEventStatus,
    TitleEvent,
    WaitEvent,
)
from app.core.entities.lead import DirectDecision, PlanDecision, ReactDecision
from app.core.entities.message import Message
from app.core.entities.plan import ExecutionStatus, Plan, Step
from app.core.entities.session import SessionStatus
from app.core.entities.tool_config import ToolConfig
from app.core.flows.planner_react import PlannerReActFlow
from app.core.json_parser.base import JSONParser
from app.core.llm.base import LLM
from app.core.sandbox.base import Sandbox
from app.core.search.base import SearchEngine
from app.core.tools.a2a import A2ATool
from app.core.tools.mcp import MCPTool
from app.core.tools.skill_draft import SkillDraftTool
from app.repositories.uow import IUnitOfWork
from app.services.skill_runtime_service import SkillRuntimeContext
from app.services.trace_service import TraceService


logger = logging.getLogger(__name__)


class LeadAgent:
    """The only top-level Agent entry, with a reversible legacy strategy."""

    def __init__(
        self,
        uow_factory: Callable[[], IUnitOfWork],
        session_id: str,
        enabled: bool,
        *,
        streaming_enabled: bool = False,
        llm: LLM | None = None,
        agent_config: AgentConfig | None = None,
        tool_config: ToolConfig | None = None,
        json_parser: JSONParser | None = None,
        browser: Browser | None = None,
        sandbox: Sandbox | None = None,
        search_engine: SearchEngine | None = None,
        mcp_tool: MCPTool | None = None,
        a2a_tool: A2ATool | None = None,
        trace_service: TraceService | None = None,
        skill_draft_tool: SkillDraftTool | None = None,
        legacy_flow: PlannerReActFlow | Any | None = None,
        decision_policy: LeadDecisionPolicy | Any | None = None,
        react_agent: Any | None = None,
        planner_agent: Any | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._uow = uow_factory()
        self._session_id = session_id
        self._enabled = enabled
        self._streaming_enabled = streaming_enabled
        self._trace_service = trace_service
        self._running = False
        self._using_legacy = not enabled

        if legacy_flow is None:
            required = {
                "llm": llm,
                "agent_config": agent_config,
                "tool_config": tool_config,
                "json_parser": json_parser,
                "browser": browser,
                "sandbox": sandbox,
                "search_engine": search_engine,
                "mcp_tool": mcp_tool,
                "a2a_tool": a2a_tool,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ValueError(
                    "创建 LeadAgent 缺少 Legacy Flow 依赖: " + ", ".join(missing)
                )
            legacy_flow = PlannerReActFlow(
                uow_factory=uow_factory,
                llm=llm,
                agent_config=agent_config,
                tool_config=tool_config,
                session_id=session_id,
                json_parser=json_parser,
                browser=browser,
                sandbox=sandbox,
                search_engine=search_engine,
                mcp_tool=mcp_tool,
                a2a_tool=a2a_tool,
                trace_service=trace_service,
                skill_draft_tool=skill_draft_tool,
                streaming_enabled=streaming_enabled,
            )
        self._legacy_flow = legacy_flow

        if decision_policy is None:
            if llm is None or agent_config is None or json_parser is None:
                raise ValueError("创建 Lead 决策策略需要 llm、agent_config 和 json_parser")
            decision_policy = LeadDecisionPolicy(
                uow_factory=uow_factory,
                session_id=session_id,
                agent_config=agent_config,
                llm=llm,
                json_parser=json_parser,
                tools=self._legacy_flow._tools,
                trace_service=trace_service,
                tool_registry=self._legacy_flow._tool_factory.registry,
                runtime_tool_scope=self._legacy_flow._tool_factory.runtime_scope,
                streaming_enabled=streaming_enabled,
            )
        self._decision_policy = decision_policy
        self._react_agent = react_agent or getattr(self._legacy_flow, "react", None)
        self._planner_agent = planner_agent or getattr(
            self._legacy_flow,
            "planner",
            None,
        )
        self._max_replans = 2
        self._skill_refs = []

    async def _record_trace(self, method_name: str, **kwargs: Any) -> None:
        if self._trace_service is None:
            return
        method = getattr(self._trace_service, method_name, None)
        if method is not None:
            await method(**kwargs)

    def set_skill_runtime_context(self, context: SkillRuntimeContext) -> None:
        self._skill_refs = [selected.ref for selected in context.selected]
        self._legacy_flow.set_skill_runtime_context(context)
        self._decision_policy.set_skill_runtime_context(context)

    def get_available_tool_names(self) -> set[str]:
        return self._legacy_flow.get_available_tool_names()

    def refresh_mcp_tools(self) -> None:
        self._legacy_flow.refresh_mcp_tools()

    async def _roll_back_legacy(self, message: Message) -> None:
        rollback = getattr(self._legacy_flow, "roll_back", None)
        if rollback is not None:
            await rollback(message)
            return
        await self._legacy_flow.planner.roll_back(message)
        await self._legacy_flow.react.roll_back(message)

    async def _prepare_new_message(self, message: Message) -> None:
        async with self._uow:
            session = await self._uow.session.get_by_id(self._session_id)
        if session is None:
            raise ValueError(f"会话[{self._session_id}]不存在, 请核实后尝试")
        if session.status != SessionStatus.PENDING:
            await self._decision_policy.roll_back(message)
            await self._roll_back_legacy(message)
        async with self._uow:
            await self._uow.session.update_status(
                self._session_id,
                SessionStatus.RUNNING,
            )

    async def _prepare_resume(self) -> Any:
        async with self._uow:
            session = await self._uow.session.get_by_id(self._session_id)
        if session is None:
            raise ValueError(f"会话[{self._session_id}]不存在, 请核实后尝试")
        if session.status != SessionStatus.WAITING:
            raise ValueError(f"会话[{self._session_id}]当前没有等待处理的交互")
        async with self._uow:
            await self._uow.session.update_status(
                self._session_id,
                SessionStatus.RUNNING,
            )
        return session

    async def _stream_react(
        self,
        stream: AsyncGenerator[BaseEvent, None],
        *,
        goal: str,
        language: str,
        capabilities: list[str],
    ) -> AsyncGenerator[BaseEvent, None]:
        completed = False
        async for event in stream:
            if isinstance(event, InteractionEvent):
                event.lead_mode = "react"
                event.lead_goal = goal
                event.lead_language = language
                event.lead_capabilities = list(capabilities)
                event.skills = list(self._skill_refs)
            yield event
            if isinstance(event, (WaitEvent, ErrorEvent)):
                await self._record_trace(
                    "record_lead_completion",
                    mode="react",
                    status="waiting" if isinstance(event, WaitEvent) else "failed",
                )
                return
            if isinstance(event, MessageEvent):
                completed = True
        if completed:
            await self._record_trace(
                "record_lead_completion",
                mode="react",
                status="completed",
            )
            yield DoneEvent()

    async def _run_react(
        self,
        decision: ReactDecision,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        await self._prepare_new_message(message)
        yield TitleEvent(title=decision.title)
        stream = self._react_agent.execute_goal(
            decision.goal,
            decision.language,
            decision.capabilities,
            message,
        )
        async for event in self._stream_react(
            stream,
            goal=decision.goal,
            language=decision.language,
            capabilities=decision.capabilities,
        ):
            yield event

    async def _resume_react(
        self,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        resolution = message.interaction_response
        if resolution is None:
            raise ValueError("恢复 React 目标时缺少 InteractionResolution")
        await self._prepare_resume()
        stream = self._react_agent.resume_goal(resolution)
        async for event in self._stream_react(
            stream,
            goal=resolution.lead_goal or "",
            language=resolution.lead_language or "",
            capabilities=resolution.lead_capabilities,
        ):
            yield event

    @staticmethod
    def _plan_from_decision(decision: PlanDecision) -> Plan:
        return Plan(
            title=decision.title,
            goal=decision.goal,
            language=decision.language,
            message=decision.message,
            steps=[step.model_copy(deep=True) for step in decision.steps],
        )

    @staticmethod
    def _find_step(plan: Plan, step_id: str | None) -> Step:
        step = next((item for item in plan.steps if item.id == step_id), None)
        if step is None:
            raise ValueError(f"计划中不存在待恢复步骤[{step_id}]")
        return step

    @staticmethod
    def _annotate_plan_interaction(
        event: InteractionEvent,
        plan: Plan,
        step: Step,
        replan_count: int,
        skill_refs: list[Any],
    ) -> None:
        event.lead_mode = "plan"
        event.lead_goal = plan.goal
        event.lead_language = plan.language
        event.lead_capabilities = list(step.capabilities)
        event.plan_id = plan.id
        event.step_id = step.id
        event.lead_replan_count = replan_count
        event.skills = list(skill_refs)

    async def _continue_plan(
        self,
        plan: Plan,
        message: Message,
        resolution: Any | None = None,
        replan_count: int = 0,
    ) -> AsyncGenerator[BaseEvent, None]:
        plan.status = ExecutionStatus.RUNNING
        terminal_failure = False

        while True:
            if resolution is not None:
                if resolution.plan_id != plan.id:
                    raise ValueError("无法恢复计划：Plan ID 不匹配")
                step = self._find_step(plan, resolution.step_id)
                stream = self._react_agent.resume_step(plan, step, resolution)
                resolution = None
            else:
                step = plan.get_next_step()
                if step is None:
                    break
                stream = self._react_agent.execute_step(plan, step, message)

            async for event in stream:
                if isinstance(event, InteractionEvent):
                    self._annotate_plan_interaction(
                        event,
                        plan,
                        step,
                        replan_count,
                        self._skill_refs,
                    )
                yield event
                if isinstance(event, (WaitEvent, ErrorEvent)):
                    await self._record_trace(
                        "record_lead_completion",
                        mode="plan",
                        status=(
                            "waiting" if isinstance(event, WaitEvent) else "failed"
                        ),
                        replan_count=replan_count,
                    )
                    return

            await self._react_agent.compact_memory()
            requires_replan = not step.success or step.needs_replan
            if requires_replan:
                terminal_failure = terminal_failure or not step.success
                if replan_count >= self._max_replans:
                    break
                replan_count += 1
                await self._record_trace(
                    "record_lead_replan",
                    count=replan_count,
                    step_id=step.id,
                    reason_code=(
                        "step_failed"
                        if not step.success
                        else "model_requested_replan"
                    ),
                )
                async for event in self._planner_agent.update_plan(plan, step):
                    yield event
                    if isinstance(event, ErrorEvent):
                        await self._record_trace(
                            "record_lead_completion",
                            mode="plan",
                            status="failed",
                            replan_count=replan_count,
                        )
                        return
                if plan.get_next_step() is None:
                    break
                continue

            yield PlanEvent(plan=plan, status=PlanEventStatus.UPDATED)
            if terminal_failure and plan.get_next_step() is None:
                terminal_failure = False

        plan.status = (
            ExecutionStatus.FAILED
            if terminal_failure or plan.get_next_step() is not None
            else ExecutionStatus.COMPLETED
        )
        async for event in self._react_agent.summarize(plan.language):
            yield event
            if isinstance(event, ErrorEvent):
                await self._record_trace(
                    "record_lead_completion",
                    mode="plan",
                    status="failed",
                    replan_count=replan_count,
                )
                return
        yield PlanEvent(plan=plan, status=PlanEventStatus.COMPLETED)
        await self._record_trace(
            "record_lead_completion",
            mode="plan",
            status=(
                "completed"
                if plan.status == ExecutionStatus.COMPLETED
                else "failed"
            ),
            replan_count=replan_count,
        )
        yield DoneEvent()

    async def _run_plan(
        self,
        decision: PlanDecision,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        await self._prepare_new_message(message)
        plan = self._plan_from_decision(decision)
        yield TitleEvent(title=plan.title)
        if plan.message:
            yield MessageEvent(role="assistant", message=plan.message)
        yield PlanEvent(plan=plan, status=PlanEventStatus.CREATED)
        async for event in self._continue_plan(plan, message):
            yield event

    async def _resume_plan(
        self,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        resolution = message.interaction_response
        if resolution is None:
            raise ValueError("恢复 Plan 时缺少 InteractionResolution")
        session = await self._prepare_resume()
        plan = session.get_latest_plan()
        if plan is None:
            raise ValueError("无法恢复计划：会话中没有 Plan")
        async for event in self._continue_plan(
            plan,
            message,
            resolution=resolution,
            replan_count=resolution.lead_replan_count,
        ):
            yield event

    async def _invoke_legacy(
        self,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        self._using_legacy = True
        async for event in self._legacy_flow.invoke(message):
            yield event

    async def invoke(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Choose the lightest sufficient strategy for one user message."""
        self._running = True
        try:
            resolution = message.interaction_response
            if resolution is not None:
                if resolution.lead_mode == "react" and self._react_agent is not None:
                    self._using_legacy = False
                    async for event in self._resume_react(message):
                        yield event
                elif (
                    resolution.lead_mode == "plan"
                    and self._react_agent is not None
                    and self._planner_agent is not None
                ):
                    self._using_legacy = False
                    async for event in self._resume_plan(message):
                        yield event
                else:
                    await self._record_trace(
                        "record_lead_fallback",
                        reason_code="interaction_without_lead_context",
                    )
                    async for event in self._invoke_legacy(message):
                        yield event
                return

            if not self._enabled:
                await self._record_trace(
                    "record_lead_fallback",
                    reason_code="feature_disabled",
                )
                async for event in self._invoke_legacy(message):
                    yield event
                return

            try:
                decision_started = perf_counter()
                decision_stream_id: str | None = None
                decide_stream = getattr(self._decision_policy, "decide_stream", None)
                if self._streaming_enabled and callable(decide_stream):
                    decision_result: LeadDecisionCompleted | None = None
                    async for decision_event in decide_stream(message):
                        if isinstance(decision_event, MessageDeltaEvent):
                            yield decision_event
                        elif isinstance(decision_event, LeadDecisionCompleted):
                            decision_result = decision_event
                    if decision_result is None:
                        raise ValueError("Lead 决策流没有返回完成结果")
                    decision = decision_result.decision
                    decision_stream_id = decision_result.stream_id
                else:
                    decision = await self._decision_policy.decide(message)
            except Exception as exc:
                logger.warning("Lead 决策失败，回退 Legacy Planner-ReAct: %s", exc)
                await self._record_trace(
                    "record_lead_fallback",
                    reason_code="decision_error",
                    error_type=type(exc).__name__,
                )
                async for event in self._invoke_legacy(message):
                    yield event
                return
            await self._record_trace(
                "record_lead_decision",
                mode=decision.mode,
                reason_code=f"{decision.mode}_selected",
                latency_ms=int((perf_counter() - decision_started) * 1000),
            )

            if isinstance(decision, ReactDecision) and self._react_agent is not None:
                self._using_legacy = False
                async for event in self._run_react(decision, message):
                    yield event
                return

            if (
                isinstance(decision, PlanDecision)
                and self._react_agent is not None
                and self._planner_agent is not None
            ):
                self._using_legacy = False
                async for event in self._run_plan(decision, message):
                    yield event
                return

            if not isinstance(decision, DirectDecision):
                await self._record_trace(
                    "record_lead_fallback",
                    reason_code="strategy_unavailable",
                )
                async for event in self._invoke_legacy(message):
                    yield event
                return

            self._using_legacy = False
            await self._prepare_new_message(message)
            yield TitleEvent(title=decision.title)
            yield MessageEvent(
                role="assistant",
                message=decision.answer,
                stream_id=decision_stream_id,
            )
            await self._record_trace(
                "record_lead_completion",
                mode="direct",
                status="completed",
            )
            yield DoneEvent()
        finally:
            self._running = False

    @property
    def done(self) -> bool:
        if self._running:
            return False
        if self._using_legacy:
            return self._legacy_flow.done
        return True
