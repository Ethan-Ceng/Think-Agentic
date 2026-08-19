#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
from typing import Any, Dict, List, Optional

from app.core.entities.app_config import AgentConfig, LLMConfig
from app.core.entities.event import (
    InteractionDecision,
    InteractionEvent,
    InteractionResolution,
    InteractionType,
    MessageEvent,
    PlanEvent,
    PlanEventStatus,
    StepEvent,
    StepEventStatus,
    ToolEvent,
    ToolEventStatus,
)
from app.core.entities.plan import ExecutionStatus, Plan, Step
from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.task.base import RunCancellationContext, RunCancellationReason
from app.core.tools.provider_runtime import ProviderFailureCode, provider_failure
from app.core.tools.registry import ToolRegistry
from app.services.trace_service import TraceService, tool_schema_bytes


class FakeTraceRepository:
    def __init__(self) -> None:
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.steps: Dict[str, Dict[str, Any]] = {}
        self.tool_calls: Dict[str, Dict[str, Any]] = {}
        self.model_calls: Dict[str, Dict[str, Any]] = {}
        self.events: List[Dict[str, Any]] = []
        self.run_skills: List[Dict[str, Any]] = []

    async def create_run(self, data: Dict[str, Any]) -> None:
        self.runs[data["id"]] = data

    async def update_run(self, run_id: str, data: Dict[str, Any]) -> None:
        self.runs[run_id].update(data)

    async def upsert_step(self, run_id: str, step_id: str, data: Dict[str, Any]) -> str:
        key = f"{run_id}:{step_id}"
        if key not in self.steps:
            self.steps[key] = {"id": f"step-record-{len(self.steps) + 1}"}
        self.steps[key].update(data)
        return self.steps[key]["id"]

    async def upsert_tool_call(self, run_id: str, tool_call_id: str, data: Dict[str, Any]) -> str:
        key = f"{run_id}:{tool_call_id}"
        if key not in self.tool_calls:
            self.tool_calls[key] = {"id": f"tool-call-{len(self.tool_calls) + 1}"}
        self.tool_calls[key].update(data)
        return self.tool_calls[key]["id"]

    async def create_model_call(self, data: Dict[str, Any]) -> None:
        self.model_calls[data["id"]] = data

    async def update_model_call(self, model_call_id: str, data: Dict[str, Any]) -> None:
        self.model_calls[model_call_id].update(data)

    async def append_event(self, data: Dict[str, Any]) -> int:
        stored = {**data, "ingest_seq": len(self.events) + 1}
        self.events.append(stored)
        return stored["ingest_seq"]

    async def save_run_skill(self, data: Dict[str, Any]) -> None:
        self.run_skills.append(data)

    async def list_runs(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return list(self.runs.values())[:limit]

    async def get_run(self, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        run = self.runs.get(run_id)
        return run if run and run["user_id"] == user_id else None

    async def list_trace_events(
        self,
        run_id: str,
        after: int | None = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        events = [
            event
            for event in self.events
            if event["run_id"] == run_id
            and (after is None or event["ingest_seq"] > after)
        ]
        return events[:limit]

    async def list_steps(self, run_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        return [step for step in self.steps.values() if step["run_id"] == run_id][:limit]

    async def list_tool_calls(
        self,
        run_id: str,
        after: str | None = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        calls = [call for call in self.tool_calls.values() if call["run_id"] == run_id]
        if after:
            ids = [call["id"] for call in calls]
            calls = calls[ids.index(after) + 1 :] if after in ids else []
        return calls[:limit]

    async def list_model_calls(
        self,
        run_id: str,
        after: str | None = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        calls = [call for call in self.model_calls.values() if call["run_id"] == run_id]
        if after:
            ids = [call["id"] for call in calls]
            calls = calls[ids.index(after) + 1 :] if after in ids else []
        return calls[:limit]

    async def list_run_skills(
        self,
        user_id: str,
        run_id: str,
    ) -> List[Dict[str, Any]]:
        return [skill for skill in self.run_skills if skill["run_id"] == run_id]


class FakeUow:
    def __init__(self, trace: FakeTraceRepository) -> None:
        self.trace = trace

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeLLM:
    model_name = "deepseek-chat"
    temperature = 0.2
    max_tokens = 1024
    base_url = "https://api.deepseek.com"


def test_trace_service_projects_run_step_tool_and_model_call() -> None:
    repo = FakeTraceRepository()
    service = TraceService(
        uow_factory=lambda: FakeUow(repo),
        tool_config=ToolConfig(),
        agent_config=AgentConfig(),
        llm_config=LLMConfig(
            base_url="https://api.deepseek.com",
            api_key="secret-key",
            model_name="deepseek-chat",
            temperature=0.2,
            max_tokens=1024,
        ),
    )

    async def run() -> None:
        input_event = MessageEvent(role="user", message="run pytest")
        input_event.id = "input-1"
        run_id = await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=input_event,
        )

        step = Step(id="step-1", description="Run tests")
        await service.project_event(
            StepEvent(
                id="event-step-start",
                step=step,
                status=StepEventStatus.STARTED,
            )
        )
        await service.project_event(
            ToolEvent(
                id="event-tool-start",
                tool_call_id="tool-call-1",
                tool_name="shell",
                function_name="shell_execute",
                function_args={"command": "pytest", "api_key": "should-redact"},
                status=ToolEventStatus.CALLING,
            )
        )
        await service.project_event(
            ToolEvent(
                id="event-tool-end",
                tool_call_id="tool-call-1",
                tool_name="shell",
                function_name="shell_execute",
                function_args={"command": "pytest", "api_key": "should-redact"},
                function_result=ToolResult(success=True, message="ok", data={"output": "passed"}),
                status=ToolEventStatus.CALLED,
            )
        )
        model_call_id = await service.record_model_call_started(
            agent_name="react",
            llm=FakeLLM(),
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            response_format=None,
            tool_choice=None,
        )
        await service.record_model_call_finished(
            model_call_id,
            message={
                "role": "assistant",
                "content": "done",
                "_trace_metadata": {
                    "finish_reason": "stop",
                    "ttft_ms": 8,
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 7,
                        "total_tokens": 18,
                    },
                },
            },
            latency_ms=25,
        )

        assert repo.runs[run_id]["status"] == "running"
        assert repo.runs[run_id]["llm_config_snapshot"] == {
            "provider": "deepseek",
            "model_name": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        assert repo.runs[run_id]["input_summary"] == ""

        stored_step = next(iter(repo.steps.values()))
        assert stored_step["step_id"] == "step-1"
        assert stored_step["status"] == "started"

        stored_tool_call = next(iter(repo.tool_calls.values()))
        assert stored_tool_call["tool_id"] == "builtin.shell.shell_execute"
        assert stored_tool_call["risk_level"] == "high"
        assert stored_tool_call["executor_type"] == "builtin"
        assert stored_tool_call["arguments"] == {}
        assert stored_tool_call["arguments_preview"] == ""
        assert stored_tool_call["result"] == {}
        assert stored_tool_call["result_preview"] == ""
        assert stored_tool_call["arguments_hash"]
        assert stored_tool_call["status"] == "called"
        assert stored_tool_call["success"] is True

        stored_model_call = repo.model_calls[model_call_id]
        assert stored_model_call["status"] == "succeeded"
        assert stored_model_call["prompt_tokens"] == 11
        assert stored_model_call["completion_tokens"] == 7
        assert stored_model_call["total_tokens"] == 18
        assert stored_model_call["latency_ms"] == 25
        assert stored_model_call["ttft_ms"] == 8
        assert stored_model_call["base_url"] == ""
        assert stored_model_call["request_preview"] == {
            "capability_groups": [],
            "provider_ids": [],
            "tool_ids": [],
            "tool_schema_bytes": 0,
            "tool_scope_excluded_count": 0,
        }
        assert stored_model_call["response_preview"] == {}

        event_types = {event["event_type"] for event in repo.events}
        expected = {"run.started", "step.started", "tool.calling", "tool.called", "model.started", "model.succeeded"}
        assert expected <= event_types
        model_succeeded = next(
            event for event in repo.events if event["event_type"] == "model.succeeded"
        )
        assert model_succeeded["payload"]["ttft_ms"] == 8
        run_started = next(event for event in repo.events if event["event_type"] == "run.started")
        registry_summary = run_started["payload"]["tool_registry"]
        assert registry_summary["function_count"] == 27
        assert registry_summary["categories"] == {
            "requires_sandbox": 10,
            "requires_browser": 12,
            "no_sandbox": 5,
        }
        assert "shell_execute" not in str(registry_summary)
        assert "run pytest" not in str(run_started)
        assert all(event["schema_version"] == 2 for event in repo.events)
        assert all(event["node_id"] for event in repo.events)

    asyncio.run(run())


def test_trace_service_projects_failure_code_and_explicit_cancellation_source() -> None:
    repo = FakeTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        input_event = MessageEvent(role="user", message="use provider")
        input_event.id = "input-provider"
        await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=input_event,
        )
        failure = provider_failure(
            ProviderFailureCode.PROTOCOL_ERROR,
            provider_id="mcp.github",
        )
        await service.project_event(
            ToolEvent(
                tool_call_id="tool-call-provider",
                tool_name="mcp",
                function_name="mcp_github_search",
                function_args={},
                function_result=ToolResult(failure=failure),
                status=ToolEventStatus.CALLED,
            )
        )
        await service.record_run_cancellation(
            RunCancellationContext(
                reason=RunCancellationReason.USER,
                requested_by="user-1",
            )
        )

    asyncio.run(run())

    tool_event = next(
        event for event in repo.events if event["event_type"] == "tool.called"
    )
    assert tool_event["payload"]["error_code"] == "PROVIDER_PROTOCOL_ERROR"
    assert tool_event["payload"]["failure_category"] == "provider"
    cancellation = next(
        event
        for event in repo.events
        if event["event_type"] == "run.cancellation_requested"
    )
    assert cancellation["payload"]["reason"] == "user"
    assert cancellation["payload"]["requested_by"] == "user-1"


def test_trace_service_uses_shared_dynamic_provider_registry() -> None:
    repo = FakeTraceRepository()
    service = TraceService(
        uow_factory=lambda: FakeUow(repo),
        tool_config=ToolConfig(),
    )
    registry = ToolRegistry(tool_config=ToolConfig())
    registry.register_runtime_schemas(
        [
            {
                "type": "function",
                "function": {
                    "name": "mcp_github_search_issues",
                    "description": "Search issues",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        provider_id="mcp.github",
        provider_label="github",
        group="mcp",
        executor_type="mcp",
        source_type="mcp",
        execution_backend="external_provider",
        execution_class="external_read",
        category="MCP",
        requires_credentials=True,
    )
    service.set_tool_registry(registry)

    async def run() -> None:
        await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=MessageEvent(role="user", message="search issues"),
        )
        await service.project_event(
            ToolEvent(
                tool_call_id="call-1",
                tool_name="mcp",
                function_name="mcp_github_search_issues",
                function_args={"query": "bug"},
                status=ToolEventStatus.CALLING,
            )
        )

    asyncio.run(run())

    stored = next(iter(repo.tool_calls.values()))
    assert stored["tool_id"] == "mcp.github.mcp_github_search_issues"
    assert stored["provider_id"] == "mcp.github"
    assert stored["source_type"] == "mcp"
    assert stored["executor_type"] == "mcp"
    event = next(item for item in repo.events if item["event_type"] == "tool.calling")
    assert event["payload"]["provider_id"] == "mcp.github"
    assert event["payload"]["execution_backend"] == "external_provider"


def test_trace_service_records_lead_strategy_lifecycle() -> None:
    repo = FakeTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        input_event = MessageEvent(role="user", message="research")
        await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=input_event,
        )
        await service.record_lead_decision(
            mode="plan",
            reason_code="plan_selected",
            latency_ms=17,
        )
        await service.record_lead_replan(
            count=1,
            step_id="step-1",
            reason_code="step_failed",
        )
        await service.record_lead_completion(
            mode="plan",
            status="completed",
            replan_count=1,
        )

    asyncio.run(run())

    events = {event["event_type"]: event["payload"] for event in repo.events}
    assert events["lead.strategy_selected"] == {
        "mode": "plan",
        "reason_code": "plan_selected",
        "decision_latency_ms": 17,
    }
    assert events["lead.replanned"]["count"] == 1
    assert events["lead.completed"] == {
        "mode": "plan",
        "status": "completed",
        "replan_count": 1,
    }


def test_trace_service_keeps_ttft_null_for_non_streaming_calls() -> None:
    repo = FakeTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=MessageEvent(role="user", message="answer normally"),
        )
        model_call_id = await service.record_model_call_started(
            agent_name="lead",
            llm=FakeLLM(),
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            response_format=None,
            tool_choice=None,
        )
        await service.record_model_call_finished(
            model_call_id,
            message={
                "role": "assistant",
                "content": "done",
                "_trace_metadata": {"finish_reason": "stop", "usage": {}},
            },
            latency_ms=20,
        )

        assert repo.model_calls[model_call_id]["ttft_ms"] is None
        model_succeeded = next(
            event for event in repo.events if event["event_type"] == "model.succeeded"
        )
        assert "ttft_ms" not in model_succeeded["payload"]

    asyncio.run(run())


def test_trace_service_projects_interaction_without_sensitive_arguments() -> None:
    repo = FakeTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=MessageEvent(role="user", message="deploy"),
        )
        pending = InteractionEvent(
            action_id="action-1",
            interaction_type=InteractionType.TOOL_APPROVAL,
            tool_call_id="call-1",
            tool_name="shell",
            function_name="shell_execute",
            function_args={"command": "deploy", "api_key": "must-not-appear"},
            prompt="Approve",
            risk_level="high",
        )
        await service.project_event(pending)
        await service.project_interaction_resolution(InteractionResolution(
            action_id=pending.action_id,
            interaction_type=pending.interaction_type,
            decision=InteractionDecision.APPROVE,
            tool_call_id=pending.tool_call_id,
            tool_name=pending.tool_name,
            function_name=pending.function_name,
            function_args=pending.function_args,
            risk_level=pending.risk_level,
        ))

        interaction_events = [
            event for event in repo.events if event["event_type"].startswith("interaction.")
        ]
        assert [event["event_type"] for event in interaction_events] == [
            "interaction.pending",
            "interaction.resolved",
        ]
        assert interaction_events[0]["payload"]["risk_level"] == "high"
        assert interaction_events[1]["payload"]["decision"] == "approve"
        assert all("function_args" not in event["payload"] for event in interaction_events)
        assert "must-not-appear" not in str(interaction_events)

    asyncio.run(run())


def test_trace_records_tool_schema_bytes_without_persisting_full_schema() -> None:
    repo = FakeTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repo))
    tools = [
        {
            "type": "function",
            "function": {
                "name": "api_private_search",
                "description": "private schema description must not be persisted",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "中文关键词"}},
                },
            },
        }
    ]

    async def run() -> None:
        await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=MessageEvent(role="user", message="search"),
        )
        model_call_id = await service.record_model_call_started(
            agent_name="planner",
            llm=FakeLLM(),
            messages=[{"role": "user", "content": "search"}],
            tools=tools,
            response_format=None,
            tool_choice="none",
            capability_groups=["search"],
            provider_ids=["builtin.search"],
            tool_ids=["builtin.search.search_web"],
            tool_scope_excluded_count=26,
        )

        stored = repo.model_calls[model_call_id]
        assert stored["tool_schema_count"] == 1
        assert stored["request_preview"]["tool_schema_bytes"] == tool_schema_bytes(tools)
        assert stored["request_preview"]["capability_groups"] == ["search"]
        assert stored["request_preview"]["provider_ids"] == ["builtin.search"]
        assert stored["request_preview"]["tool_ids"] == [
            "builtin.search.search_web"
        ]
        assert stored["request_preview"]["tool_scope_excluded_count"] == 26
        assert "messages" not in stored["request_preview"]
        assert "tools" not in stored["request_preview"]
        assert "private schema description" not in str(stored)

        started = next(event for event in repo.events if event["event_type"] == "model.started")
        assert started["payload"]["tool_schema_count"] == 1
        assert started["payload"]["tool_schema_bytes"] == tool_schema_bytes(tools)
        assert started["payload"]["capability_groups"] == ["search"]
        assert started["payload"]["provider_ids"] == ["builtin.search"]
        assert started["payload"]["tool_ids"] == ["builtin.search.search_web"]
        assert started["payload"]["tool_scope_excluded_count"] == 26

    asyncio.run(run())


def test_trace_service_exposes_incremental_execution_view_and_plan_revision() -> None:
    repo = FakeTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        run_id = await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=MessageEvent(id="input-plan", role="user", message="upgrade"),
        )
        plan = Plan(
            id="plan-1",
            title="升级",
            goal="展示执行过程",
            status=ExecutionStatus.RUNNING,
            steps=[Step(id="step-1", description="检查实现")],
        )
        await service.project_event(
            PlanEvent(id="plan-event-1", plan=plan, status=PlanEventStatus.CREATED)
        )
        await service.record_lead_replan(
            count=1,
            step_id="step-1",
            reason_code="new_fact",
        )
        plan.steps[0].status = ExecutionStatus.COMPLETED
        plan.steps[0].success = True
        plan.steps[0].result = "完成"
        await service.project_event(
            PlanEvent(id="plan-event-2", plan=plan, status=PlanEventStatus.UPDATED)
        )

        first = await service.get_execution_view(
            "user-1", run_id, limit=2, detail="summary"
        )
        second = await service.get_execution_view(
            "user-1", run_id, after=first["next_cursor"], limit=10, detail="detail"
        )

        assert first["has_more"] is True
        assert all(node["cursor"] <= first["next_cursor"] for node in first["nodes"])
        assert all(node["cursor"] > first["next_cursor"] for node in second["nodes"])
        plan_node = next(node for node in second["nodes"] if node["node_id"] == "plan:plan-1")
        assert plan_node["metrics"]["revision"] == 2
        assert plan_node["metrics"]["replan_count"] == 1
        assert repo.steps[f"{run_id}:step-1"]["step_index"] == 0

    asyncio.run(run())


def test_trace_drops_model_reasoning_prompts_and_unknown_provider_url() -> None:
    repo = FakeTraceRepository()

    class PrivateLLM(FakeLLM):
        base_url = "https://llm.internal.example.test/private?tenant=secret"

    service = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=MessageEvent(role="user", message="private user prompt"),
        )
        model_call_id = await service.record_model_call_started(
            agent_name="lead",
            llm=PrivateLLM(),
            messages=[
                {"role": "system", "content": "private system prompt"},
                {"role": "user", "content": "private user prompt"},
            ],
            tools=[],
            response_format=None,
            tool_choice=None,
        )
        await service.record_model_call_finished(
            model_call_id,
            message={
                "role": "assistant",
                "content": "private response",
                "reasoning_content": "hidden chain of thought",
                "_trace_metadata": {"finish_reason": "stop", "usage": {}},
            },
            latency_ms=9,
        )

        stored = repo.model_calls[model_call_id]
        serialized = str(stored)
        assert stored["provider"] == "openai-compatible"
        assert stored["base_url"] == ""
        assert stored["request_preview"]["tool_schema_bytes"] == 0
        assert stored["response_preview"] == {}
        assert "private" not in serialized
        assert "hidden chain" not in serialized
        assert "internal.example" not in serialized

    asyncio.run(run())


def test_trace_query_projection_sanitizes_historical_records_and_pages_directly() -> None:
    repo = FakeTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        run_id = await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=MessageEvent(role="user", message="sensitive input"),
        )
        repo.model_calls["model-old"] = {
            "id": "model-old",
            "run_id": run_id,
            "session_id": "session-1",
            "agent_name": "lead",
            "provider": "private.internal",
            "base_url": "https://private.internal/api?token=secret",
            "model_name": "model",
            "request_preview": {"messages": [{"content": "secret prompt"}]},
            "response_preview": {"reasoning_content": "hidden"},
            "created_at": repo.events[0]["created_at"],
        }
        repo.tool_calls[f"{run_id}:old"] = {
            "id": "tool-old",
            "run_id": run_id,
            "session_id": "session-1",
            "tool_call_id": "old",
            "tool_name": "shell",
            "function_name": "shell_execute",
            "arguments": {"command": "cat /secret"},
            "arguments_preview": "cat /secret",
            "arguments_hash": "hash",
            "result": {"output": "secret"},
            "result_preview": "secret",
            "created_at": repo.events[0]["created_at"],
        }
        repo.events.append(
            {
                "id": "legacy-event",
                "trace_id": f"run:{run_id}",
                "run_id": run_id,
                "session_id": "session-1",
                "event_id": "legacy",
                "event_type": "message.created",
                "payload": {"message": "secret historical message"},
                "created_at": repo.events[0]["created_at"],
                "ingest_seq": 2,
                "schema_version": 1,
                "node_id": "",
                "parent_node_id": None,
                "visibility": "user",
                "summary": "",
            }
        )

        detail = await service.get_run_detail("user-1", run_id)
        assert detail["run"]["input_summary"] == ""
        assert detail["run"]["tool_config_snapshot"] == {}
        assert detail["tool_calls"][0]["arguments"] == {}
        assert detail["tool_calls"][0]["result"] == {}
        assert detail["model_calls"][0]["base_url"] == ""
        assert detail["model_calls"][0]["request_preview"] == {}
        assert detail["model_calls"][0]["response_preview"] == {}
        assert "secret historical message" not in str(detail["events"])

        page = await service.list_events("user-1", run_id, after=1, limit=1)
        assert len(page["events"]) == 1
        assert page["events"][0]["ingest_seq"] == 2
        assert page["next_cursor"] == 2

    asyncio.run(run())


def test_trace_records_sandbox_activation_summary_without_content() -> None:
    repo = FakeTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        await service.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-1",
            input_event=MessageEvent(role="user", message="open a shell"),
        )
        await service.record_sandbox_activation(
            activation_reason="task_initialization",
            first_capability=None,
            operation_counts={
                "create": 1,
                "get": 0,
                "ensure": 1,
                "get_browser": 1,
                "upload_file": 2,
            },
            startup_ms=420,
            attachment_sync_bytes=8192,
            outcome="succeeded",
        )

        event = next(
            item for item in repo.events if item["event_type"] == "sandbox.activated"
        )
        assert event["payload"] == {
            "activation_reason": "task_initialization",
            "first_capability": "",
            "operation_counts": {
                "create": 1,
                "get": 0,
                "ensure": 1,
                "get_browser": 1,
                "upload_file": 2,
            },
            "startup_ms": 420,
            "attachment_sync_bytes": 8192,
            "outcome": "succeeded",
            "error_type": "",
        }
        assert "open a shell" not in str(event["payload"])

    asyncio.run(run())
