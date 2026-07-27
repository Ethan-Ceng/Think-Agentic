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
    StepEvent,
    StepEventStatus,
    ToolEvent,
    ToolEventStatus,
)
from app.core.entities.plan import Step
from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.services.trace_service import TraceService, tool_schema_bytes


class FakeTraceRepository:
    def __init__(self) -> None:
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.steps: Dict[str, Dict[str, Any]] = {}
        self.tool_calls: Dict[str, Dict[str, Any]] = {}
        self.model_calls: Dict[str, Dict[str, Any]] = {}
        self.events: List[Dict[str, Any]] = []

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

    async def append_event(self, data: Dict[str, Any]) -> None:
        self.events.append(data)

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

    async def list_trace_events(self, run_id: str) -> List[Dict[str, Any]]:
        return [event for event in self.events if event["run_id"] == run_id]

    async def list_steps(self, run_id: str) -> List[Dict[str, Any]]:
        return [step for step in self.steps.values() if step["run_id"] == run_id]

    async def list_tool_calls(self, run_id: str) -> List[Dict[str, Any]]:
        return [call for call in self.tool_calls.values() if call["run_id"] == run_id]

    async def list_model_calls(self, run_id: str) -> List[Dict[str, Any]]:
        return [call for call in self.model_calls.values() if call["run_id"] == run_id]


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
        assert repo.runs[run_id]["llm_config_snapshot"]["api_key"] == "******"

        stored_step = next(iter(repo.steps.values()))
        assert stored_step["step_id"] == "step-1"
        assert stored_step["status"] == "started"

        stored_tool_call = next(iter(repo.tool_calls.values()))
        assert stored_tool_call["tool_id"] == "builtin.shell.shell_execute"
        assert stored_tool_call["risk_level"] == "high"
        assert stored_tool_call["executor_type"] == "builtin"
        assert stored_tool_call["arguments"]["api_key"] == "******"
        assert stored_tool_call["status"] == "called"
        assert stored_tool_call["success"] is True

        stored_model_call = repo.model_calls[model_call_id]
        assert stored_model_call["status"] == "succeeded"
        assert stored_model_call["prompt_tokens"] == 11
        assert stored_model_call["completion_tokens"] == 7
        assert stored_model_call["total_tokens"] == 18
        assert stored_model_call["latency_ms"] == 25

        event_types = {event["event_type"] for event in repo.events}
        expected = {"run.started", "step.started", "tool.calling", "tool.called", "model.started", "model.succeeded"}
        assert expected <= event_types
        run_started = next(event for event in repo.events if event["event_type"] == "run.started")
        registry_summary = run_started["payload"]["tool_registry"]
        assert registry_summary["function_count"] == 27
        assert registry_summary["categories"] == {
            "requires_sandbox": 10,
            "requires_browser": 12,
            "no_sandbox": 5,
        }
        assert "shell_execute" not in str(registry_summary)

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
        )

        stored = repo.model_calls[model_call_id]
        assert stored["tool_schema_count"] == 1
        assert stored["request_preview"]["tool_schema_bytes"] == tool_schema_bytes(tools)
        assert stored["request_preview"]["tools"] == ["api_private_search"]
        assert "private schema description" not in str(stored)

        started = next(event for event in repo.events if event["event_type"] == "model.started")
        assert started["payload"]["tool_schema_count"] == 1
        assert started["payload"]["tool_schema_bytes"] == tool_schema_bytes(tools)

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
