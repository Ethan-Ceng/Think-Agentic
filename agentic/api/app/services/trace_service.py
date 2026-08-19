#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run/trace projection and query service."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from time import perf_counter
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

from pydantic import BaseModel

from app.core.entities.app_config import AgentConfig, LLMConfig
from app.core.entities.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    InteractionEvent,
    InteractionResolution,
    MessageEvent,
    PlanEvent,
    StepEvent,
    StepEventStatus,
    ToolEvent,
    ToolEventStatus,
    WaitEvent,
)
from app.core.entities.tool_config import ToolConfig
from app.core.entities.skill import RunSkill, SelectedSkill
from app.core.tools.registry import ToolRegistry
from app.core.task.base import RunCancellationContext
from app.repositories.uow import IUnitOfWork
from app.schemas.exceptions import NotFoundError
from app.schemas.skill import SkillSelectionRequest, SkillSelectionResult

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "cookie",
    "set-cookie",
}
PREVIEW_LIMIT = 1200
SANDBOX_OPERATION_NAMES = {
    "create",
    "get",
    "ensure",
    "get_browser",
    "upload_file",
}


class TraceService:
    """Project runtime events into queryable run/trace tables."""

    def __init__(
        self,
        uow_factory: Callable[[], IUnitOfWork],
        *,
        tool_config: ToolConfig | None = None,
        agent_config: AgentConfig | None = None,
        llm_config: LLMConfig | None = None,
        fail_silently: bool = False,
    ) -> None:
        self._uow_factory = uow_factory
        self._tool_config = tool_config or ToolConfig()
        self._agent_config = agent_config
        self._llm_config = llm_config
        self._registry = ToolRegistry(tool_config=self._tool_config)
        self._fail_silently = fail_silently
        self.run_id: str | None = None
        self.trace_id: str | None = None
        self.session_id: str | None = None
        self.user_id: str | None = None
        self._active_plan_id: str | None = None
        self._active_step_id: str | None = None
        self._active_run_step_id: str | None = None
        self._tool_started_at: Dict[str, datetime] = {}
        self._terminal_failed = False

    def set_tool_registry(self, registry: ToolRegistry) -> None:
        """Share the live Agent registry so lazy Provider metadata stays exact."""
        self._registry = registry

    async def start_run(
        self,
        *,
        user_id: str,
        session_id: str,
        task_id: str | None,
        input_event: MessageEvent,
    ) -> str:
        """Create a new run for one user input message."""
        self.run_id = str(uuid.uuid4())
        self.trace_id = f"run:{self.run_id}"
        self.session_id = session_id
        self.user_id = user_id
        self._active_plan_id = None
        self._active_step_id = None
        self._active_run_step_id = None
        self._tool_started_at = {}
        self._terminal_failed = False
        now = datetime.now()
        tool_registry_summary = summarize_tool_registry(
            self._registry,
            self._tool_config,
        )
        run_data = {
            "id": self.run_id,
            "trace_id": self.trace_id,
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "input_event_id": input_event.id,
            "status": "running",
            "input_summary": "",
            "tool_config_snapshot": tool_registry_summary,
            "agent_config_snapshot": _safe_agent_snapshot(self._agent_config),
            "llm_config_snapshot": _safe_llm_snapshot(self._llm_config),
            "started_at": now,
        }

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.create_run(run_data)
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="run.started",
                    event_id=input_event.id,
                    payload={
                        "tool_registry": tool_registry_summary,
                        "attachment_count": len(input_event.attachments),
                    },
                    created_at=now,
                )
            )

        await self._write(write)
        return self.run_id

    async def record_sandbox_activation(
        self,
        *,
        activation_reason: str,
        first_capability: str | None,
        operation_counts: Dict[str, int],
        startup_ms: int | None,
        attachment_sync_bytes: int,
        outcome: str,
        error_type: str | None = None,
    ) -> None:
        """Record bounded Sandbox lifecycle metrics without user content."""
        if not self.run_id:
            return
        counts = {
            name: max(0, int(operation_counts.get(name, 0)))
            for name in sorted(SANDBOX_OPERATION_NAMES)
        }
        payload = {
            "activation_reason": activation_reason,
            "first_capability": first_capability or "",
            "operation_counts": counts,
            "startup_ms": max(0, int(startup_ms)) if startup_ms is not None else None,
            "attachment_sync_bytes": max(0, int(attachment_sync_bytes)),
            "outcome": outcome,
            "error_type": error_type or "",
        }

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type=(
                        "sandbox.activated"
                        if outcome == "succeeded"
                        else "sandbox.activation_failed"
                    ),
                    payload=payload,
                )
            )

        await self._write(write)

    async def record_run_cancellation(
        self,
        context: RunCancellationContext,
    ) -> None:
        """Record explicit cancellation provenance without inferring from exceptions."""
        if not self.run_id:
            return

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="run.cancellation_requested",
                    payload={
                        "reason": context.reason.value,
                        "requested_by": context.requested_by,
                        "requested_at": context.requested_at.isoformat(),
                    },
                )
            )

        await self._write(write)

    async def _record_lead_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        if not self.run_id:
            return

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type=event_type,
                    payload=payload,
                )
            )

        await self._write(write)

    async def record_lead_decision(
        self,
        *,
        mode: str,
        reason_code: str,
        latency_ms: int,
    ) -> None:
        await self._record_lead_event(
            "lead.strategy_selected",
            {
                "mode": mode,
                "reason_code": reason_code,
                "decision_latency_ms": max(0, int(latency_ms)),
            },
        )

    async def record_lead_fallback(
        self,
        *,
        reason_code: str,
        error_type: str = "",
    ) -> None:
        await self._record_lead_event(
            "lead.fallback",
            {
                "reason_code": reason_code,
                "error_type": error_type,
            },
        )

    async def record_lead_replan(
        self,
        *,
        count: int,
        step_id: str,
        reason_code: str,
    ) -> None:
        await self._record_lead_event(
            "lead.replanned",
            {
                "count": max(0, int(count)),
                "step_id": step_id,
                "reason_code": reason_code,
            },
        )

    async def record_lead_completion(
        self,
        *,
        mode: str,
        status: str,
        replan_count: int = 0,
    ) -> None:
        await self._record_lead_event(
            "lead.completed",
            {
                "mode": mode,
                "status": status,
                "replan_count": max(0, int(replan_count)),
            },
        )

    async def project_event(self, event: BaseEvent) -> None:
        """Project one runtime event into trace tables."""
        if not self.run_id or not self.trace_id or not self.session_id:
            return

        async def write(uow: IUnitOfWork) -> None:
            await self._project_event(uow, event)

        await self._write(write)

    async def project_interaction_resolution(self, resolution: InteractionResolution) -> None:
        """Record a resolved decision without persisting sensitive tool arguments."""
        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="interaction.resolved",
                    event_id=resolution.action_id,
                    payload={
                        "action_id": resolution.action_id,
                        "interaction_type": resolution.interaction_type.value,
                        "status": "resolved",
                        "decision": resolution.decision.value,
                        "tool_call_id": resolution.tool_call_id,
                        "tool_name": resolution.tool_name,
                        "function_name": resolution.function_name,
                        "risk_level": resolution.risk_level,
                    },
                )
            )

        await self._write(write)

    async def record_model_call_started(
        self,
        *,
        agent_name: str,
        llm: Any,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        response_format: Dict[str, Any] | None,
        tool_choice: str | None,
        capability_groups: List[str] | None = None,
        provider_ids: List[str] | None = None,
        tool_ids: List[str] | None = None,
        tool_scope_excluded_count: int = 0,
    ) -> str | None:
        """Insert a started model call and return its id."""
        if not self.run_id or not self.session_id:
            return None
        model_call_id = str(uuid.uuid4())
        started_at = datetime.now()
        llm_snapshot = _snapshot(self._llm_config)
        base_url = str(llm_snapshot.get("base_url") or getattr(llm, "base_url", "") or "")
        model_name = str(llm_snapshot.get("model_name") or getattr(llm, "model_name", "") or "")
        temperature = llm_snapshot.get("temperature", getattr(llm, "temperature", None))
        max_tokens = llm_snapshot.get("max_tokens", getattr(llm, "max_tokens", None))
        schema_bytes = tool_schema_bytes(tools)
        request_preview = {
            "tool_schema_bytes": schema_bytes,
            "capability_groups": list(capability_groups or []),
            "provider_ids": list(provider_ids or []),
            "tool_ids": list(tool_ids or []),
            "tool_scope_excluded_count": tool_scope_excluded_count,
        }
        data = {
            "id": model_call_id,
            "run_id": self.run_id,
            "run_step_id": self._active_run_step_id,
            "step_id": self._active_step_id,
            "session_id": self.session_id,
            "agent_name": agent_name,
            "provider": _provider_from_base_url(base_url),
            "base_url": "",
            "model_name": model_name,
            "temperature": float(temperature) if temperature is not None else None,
            "max_tokens": int(max_tokens) if max_tokens is not None else None,
            "tool_schema_count": len(tools or []),
            "message_count": len(messages or []),
            "tool_choice": tool_choice,
            "response_format": _snapshot(response_format),
            "status": "started",
            "request_preview": _snapshot(request_preview),
            "started_at": started_at,
        }

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.create_model_call(data)
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="model.started",
                    payload={
                        "model_call_id": model_call_id,
                        "agent_name": agent_name,
                        "model_name": model_name,
                        "tool_schema_count": len(tools or []),
                        "tool_schema_bytes": schema_bytes,
                        "capability_groups": list(capability_groups or []),
                        "provider_ids": list(provider_ids or []),
                        "tool_ids": list(tool_ids or []),
                        "tool_scope_excluded_count": tool_scope_excluded_count,
                        "message_count": len(messages or []),
                    },
                    created_at=started_at,
                )
            )

        await self._write(write)
        return model_call_id

    async def record_model_call_finished(
        self,
        model_call_id: str | None,
        *,
        message: Dict[str, Any] | None = None,
        error: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        """Update a model call after success or failure."""
        if not self.run_id or not model_call_id:
            return
        finished_at = datetime.now()
        metadata = (message or {}).get("_trace_metadata") or {}
        usage = metadata.get("usage") or {}
        ttft_ms = metadata.get("ttft_ms")
        data = {
            "status": "failed" if error else "succeeded",
            "finish_reason": metadata.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "latency_ms": latency_ms,
            "ttft_ms": ttft_ms,
            "response_preview": {},
            "error": "Model call failed" if error else None,
            "finished_at": finished_at,
        }

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.update_model_call(model_call_id, data)
            event_payload = {
                "model_call_id": model_call_id,
                "latency_ms": latency_ms,
                "finish_reason": metadata.get("finish_reason"),
                "usage": _snapshot(usage),
                "error_type": "model_call_failed" if error else "",
            }
            if ttft_ms is not None:
                event_payload["ttft_ms"] = ttft_ms
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="model.failed" if error else "model.succeeded",
                    payload=event_payload,
                    created_at=finished_at,
                )
            )

        await self._write(write)

    async def record_skill_selection_started(
        self, request: SkillSelectionRequest
    ) -> None:
        if not self.run_id:
            return

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="skill.selection.started",
                    payload={
                        "manual_refs": request.manual_refs,
                        "attachment_media_types": request.attachment_media_types,
                        "available_tool_names": sorted(request.available_tool_names),
                    },
                )
            )

        await self._write(write)

    async def record_skill_selection_completed(
        self,
        result: SkillSelectionResult,
        context: Any,
    ) -> None:
        """Persist selection events and materialized rows in one UoW."""
        if not self.run_id:
            return

        async def write(uow: IUnitOfWork) -> None:
            for selected in result.selected:
                payload = _selected_skill_payload(selected)
                await uow.trace.append_event(
                    self._trace_event_data(
                        event_type="skill.selected",
                        payload=payload,
                    )
                )
                sandbox_path = context.sandbox_roots[selected.manifest.name]
                run_skill = RunSkill(
                    run_id=self.run_id,
                    skill_id=selected.ref.skill_id,
                    skill_version_id=selected.version_id,
                    name=selected.manifest.name,
                    source=selected.ref.source,
                    selection_mode=selected.selection_mode,
                    content_sha256=selected.package_sha256,
                    confidence=selected.confidence,
                    reason=selected.reason,
                    sandbox_path=sandbox_path,
                )
                await uow.trace.save_run_skill(
                    run_skill.model_dump(mode="python")
                )
                await uow.trace.append_event(
                    self._trace_event_data(
                        event_type="skill.materialized",
                        payload={**payload, "sandbox_path": sandbox_path},
                    )
                )

            for skipped in result.skipped:
                await uow.trace.append_event(
                    self._trace_event_data(
                        event_type="skill.skipped",
                        payload={
                            "ref": skipped.ref,
                            "requested_key": skipped.requested_key,
                            "selection_mode": skipped.selection_mode,
                            "code": skipped.code,
                            "reason": skipped.reason,
                        },
                    )
                )

        await self._write(write)

    async def record_skill_selection_failed(self, error: Exception) -> None:
        if not self.run_id:
            return

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="skill.selection.failed",
                    payload={
                        "error_type": type(error).__name__,
                        "message": "Skill selection or materialization failed.",
                    },
                )
            )

        await self._write(write)

    async def list_runs(
        self,
        user_id: str,
        session_id: str | None = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 200))
        uow = self._uow_factory()
        async with uow:
            records = await uow.trace.list_runs(
                user_id=user_id,
                session_id=session_id,
                limit=limit,
            )
            return [_public_run(record) for record in records]

    async def get_run_detail(self, user_id: str, run_id: str) -> Dict[str, Any]:
        record_limit = 200
        uow = self._uow_factory()
        async with uow:
            run = await uow.trace.get_run(user_id=user_id, run_id=run_id)
            if not run:
                raise NotFoundError("运行记录不存在")
            steps = await uow.trace.list_steps(run_id, limit=record_limit + 1)
            tool_calls = await uow.trace.list_tool_calls(run_id, limit=record_limit + 1)
            model_calls = await uow.trace.list_model_calls(run_id, limit=record_limit + 1)
            events = await uow.trace.list_trace_events(run_id, limit=record_limit + 1)
            skills = await uow.trace.list_run_skills(user_id, run_id)
            return {
                "run": _public_run(run),
                "steps": [_public_step(item) for item in steps[:record_limit]],
                "tool_calls": [_public_tool_call(item) for item in tool_calls[:record_limit]],
                "model_calls": [_public_model_call(item) for item in model_calls[:record_limit]],
                "events": [
                    projected
                    for item in events[:record_limit]
                    if (projected := _public_trace_event(item)) is not None
                ],
                "skills": [_public_run_skill(item) for item in skills],
                "truncated": {
                    "steps": len(steps) > record_limit,
                    "tool_calls": len(tool_calls) > record_limit,
                    "model_calls": len(model_calls) > record_limit,
                    "events": len(events) > record_limit,
                },
            }

    async def list_events(
        self,
        user_id: str,
        run_id: str,
        *,
        after: int | None = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        limit = max(1, min(limit, 500))
        uow = self._uow_factory()
        async with uow:
            await self._require_run(uow, user_id, run_id)
            records = await uow.trace.list_trace_events(
                run_id,
                after=after,
                limit=limit + 1,
            )
        page = records[:limit]
        events = [
            projected
            for item in page
            if (projected := _public_trace_event(item)) is not None
        ]
        return {
            "events": events,
            "next_cursor": page[-1]["ingest_seq"] if page else after,
            "has_more": len(records) > limit,
        }

    async def list_tool_calls(
        self,
        user_id: str,
        run_id: str,
        *,
        after: str | None = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        limit = max(1, min(limit, 500))
        uow = self._uow_factory()
        async with uow:
            await self._require_run(uow, user_id, run_id)
            records = await uow.trace.list_tool_calls(
                run_id,
                after=after,
                limit=limit + 1,
            )
        page = records[:limit]
        return {
            "tool_calls": [_public_tool_call(item) for item in page],
            "next_cursor": page[-1]["id"] if page else after,
            "has_more": len(records) > limit,
        }

    async def list_model_calls(
        self,
        user_id: str,
        run_id: str,
        *,
        after: str | None = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        limit = max(1, min(limit, 500))
        uow = self._uow_factory()
        async with uow:
            await self._require_run(uow, user_id, run_id)
            records = await uow.trace.list_model_calls(
                run_id,
                after=after,
                limit=limit + 1,
            )
        page = records[:limit]
        return {
            "model_calls": [_public_model_call(item) for item in page],
            "next_cursor": page[-1]["id"] if page else after,
            "has_more": len(records) > limit,
        }

    async def list_run_skills(
        self, user_id: str, run_id: str
    ) -> List[Dict[str, Any]]:
        uow = self._uow_factory()
        async with uow:
            run = await uow.trace.get_run(user_id=user_id, run_id=run_id)
            if not run:
                raise NotFoundError("运行记录不存在")
            records = await uow.trace.list_run_skills(user_id, run_id)
            return [_public_run_skill(item) for item in records]

    @staticmethod
    async def _require_run(
        uow: IUnitOfWork,
        user_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        run = await uow.trace.get_run(user_id=user_id, run_id=run_id)
        if not run:
            raise NotFoundError("运行记录不存在")
        return run

    async def _project_event(self, uow: IUnitOfWork, event: BaseEvent) -> None:
        if isinstance(event, PlanEvent):
            self._active_plan_id = event.plan.id
        event_type = _event_type(event)
        payload = _event_payload(event)
        if isinstance(event, ToolEvent):
            metadata = self._tool_metadata(event)
            failure = (
                event.function_result.failure
                if event.function_result is not None
                else None
            )
            payload.update(
                {
                    "tool_id": metadata["tool_id"],
                    "provider_id": metadata.get("provider_id"),
                    "source_type": metadata.get("source_type"),
                    "execution_backend": metadata.get("execution_backend"),
                    "execution_class": metadata.get("execution_class"),
                    "generality": metadata.get("generality"),
                    "cost_class": metadata.get("cost_class"),
                    "error_code": failure.code if failure is not None else None,
                    "failure_category": (
                        failure.category.value if failure is not None else None
                    ),
                }
            )
        await uow.trace.append_event(
            self._trace_event_data(
                event_type=event_type,
                event_id=event.id,
                payload=payload,
                created_at=event.created_at,
            )
        )

        if isinstance(event, StepEvent):
            await self._project_step(uow, event)
        elif isinstance(event, ToolEvent):
            await self._project_tool_call(uow, event)
        elif isinstance(event, MessageEvent):
            if event.role == "assistant" and event.message:
                await uow.trace.update_run(self.run_id, {"final_summary": ""})
        elif isinstance(event, InteractionEvent):
            if event.status.value == "pending":
                await uow.trace.update_run(self.run_id, {"status": "waiting"})
        elif isinstance(event, WaitEvent):
            await uow.trace.update_run(self.run_id, {"status": "waiting"})
        elif isinstance(event, ErrorEvent):
            self._terminal_failed = True
            await uow.trace.update_run(
                self.run_id,
                {
                    "status": "failed",
                    "error": "Agent run failed",
                    "finished_at": event.created_at,
                },
            )
        elif isinstance(event, DoneEvent):
            if not self._terminal_failed:
                await uow.trace.update_run(
                    self.run_id,
                    {
                        "status": "completed",
                        "finished_at": event.created_at,
                    },
                )

    async def _project_step(self, uow: IUnitOfWork, event: StepEvent) -> None:
        terminal = event.status in {StepEventStatus.COMPLETED, StepEventStatus.FAILED}
        data = {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "event_id": event.id,
            "step_id": event.step.id,
            "description": event.step.description,
            "status": event.status.value,
            "success": event.step.success,
            "result_summary": _preview(event.step.result or ""),
            "error": _preview(event.step.error) if event.step.error else None,
            "attachments": _snapshot(event.step.attachments),
            "finished_at": event.created_at if terminal else None,
        }
        if event.status == StepEventStatus.STARTED:
            data["started_at"] = event.created_at
        run_step_id = await uow.trace.upsert_step(self.run_id, event.step.id, data)
        if event.status == StepEventStatus.STARTED:
            self._active_step_id = event.step.id
            self._active_run_step_id = run_step_id
        elif terminal and self._active_step_id == event.step.id:
            self._active_step_id = None
            self._active_run_step_id = None

    async def _project_tool_call(self, uow: IUnitOfWork, event: ToolEvent) -> None:
        metadata = self._tool_metadata(event)
        status = event.status.value
        success = None
        result_data: Dict[str, Any] = {}
        result_preview = ""
        error = None
        finished_at = None
        latency_ms = None
        if event.status == ToolEventStatus.CALLED:
            finished_at = event.created_at
            started_at = self._tool_started_at.get(event.tool_call_id)
            if started_at:
                latency_ms = int((event.created_at - started_at).total_seconds() * 1000)
            success = bool(event.function_result.success) if event.function_result else None
            status = "called" if success else "failed"
            if event.function_result and not event.function_result.success:
                error = _preview(event.function_result.message)
                if "禁用" in (event.function_result.message or ""):
                    status = "blocked"
            result_data = {}
            result_preview = ""

        data = {
            "run_id": self.run_id,
            "run_step_id": self._active_run_step_id,
            "step_id": self._active_step_id,
            "session_id": self.session_id,
            "event_id": event.id,
            "tool_call_id": event.tool_call_id,
            "tool_id": metadata["tool_id"],
            "tool_name": event.tool_name,
            "function_name": event.function_name,
            "provider_id": metadata.get("provider_id"),
            "registration_id": metadata.get("registration_id"),
            "source_type": metadata.get("source_type"),
            "executor_type": metadata.get("executor_type"),
            "risk_level": metadata.get("risk_level"),
            "enabled_effective": metadata.get("enabled_effective"),
            "requires_sandbox": metadata.get("requires_sandbox", False),
            "requires_browser": metadata.get("requires_browser", False),
            "requires_credentials": metadata.get("requires_credentials", False),
            "status": status,
            "arguments": {},
            "arguments_preview": "",
            "arguments_hash": _hash_value(event.function_args),
            "result": result_data,
            "result_preview": result_preview,
            "success": success,
            "error": "Tool call failed" if error else None,
            "latency_ms": latency_ms,
            "finished_at": finished_at,
        }
        if event.status == ToolEventStatus.CALLING:
            self._tool_started_at[event.tool_call_id] = event.created_at
            data["started_at"] = event.created_at
        await uow.trace.upsert_tool_call(self.run_id, event.tool_call_id, data)

    def _trace_event_data(
        self,
        *,
        event_type: str,
        payload: Dict[str, Any],
        event_id: str | None = None,
        created_at: datetime | None = None,
        node_id: str | None = None,
        parent_node_id: str | None = None,
        visibility: str = "user",
        summary: str | None = None,
    ) -> Dict[str, Any]:
        inferred_node_id, inferred_parent_id = _trace_node_identity(
            run_id=self.run_id or "",
            event_type=event_type,
            payload=payload,
            event_id=event_id,
            active_plan_id=self._active_plan_id,
            active_step_id=self._active_step_id,
        )
        return {
            "id": str(uuid.uuid4()),
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "event_id": event_id,
            "event_type": event_type,
            "schema_version": 2,
            "node_id": node_id or inferred_node_id,
            "parent_node_id": parent_node_id or inferred_parent_id,
            "visibility": visibility,
            "summary": _preview(summary or _event_summary(event_type, payload), 300),
            "payload": _safe_trace_payload(event_type, payload),
            "created_at": created_at or datetime.now(),
        }

    def _tool_metadata(self, event: ToolEvent) -> Dict[str, Any]:
        tool_id, binding, executor_type, source_enabled = self._registry.resolve_binding(
            self._tool_config,
            event.tool_name,
            event.function_name,
        )
        descriptor = self._registry.get_by_function_name(event.function_name, self._tool_config)
        provider_id = descriptor.provider_id if descriptor else None
        registration_id = provider_id
        source_type = descriptor.source_type if descriptor else "builtin"
        if source_type == "api":
            registration = self._registration_for_provider(provider_id)
            if registration:
                registration_id = registration.registration_id
        return {
            "tool_id": tool_id,
            "provider_id": provider_id,
            "registration_id": registration_id,
            "source_type": source_type,
            "executor_type": executor_type,
            "execution_backend": (
                descriptor.execution_backend if descriptor else "in_process"
            ),
            "execution_class": (
                descriptor.execution_class if descriptor else "external_read"
            ),
            "generality": (
                descriptor.generality if descriptor else "specialized"
            ),
            "cost_class": descriptor.cost_class if descriptor else "low",
            "risk_level": binding.risk_level,
            "enabled_effective": bool(source_enabled and binding.enabled),
            "requires_sandbox": bool(descriptor.requires_sandbox) if descriptor else False,
            "requires_browser": bool(descriptor.requires_browser) if descriptor else False,
            "requires_credentials": bool(descriptor.requires_credentials) if descriptor else False,
        }

    def _registration_for_provider(self, provider_id: str | None):
        if not provider_id:
            return None
        for registration in self._tool_config.registrations.values():
            if registration.provider_id == provider_id or registration.registration_id == provider_id:
                return registration
        return None

    async def _write(self, fn: Callable[[IUnitOfWork], Any]) -> None:
        try:
            uow = self._uow_factory()
            async with uow:
                await fn(uow)
        except Exception as exc:
            if self._fail_silently:
                logger.warning("Trace write failed: %s", exc)
                return
            raise


def model_call_timer() -> float:
    return perf_counter()


def elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def tool_schema_bytes(tools: List[Dict[str, Any]] | None) -> int:
    """Return UTF-8 bytes for the canonical schema payload, not a token estimate."""
    if not tools:
        return 0
    payload = json.dumps(
        tools,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_schema_json_default,
    )
    return len(payload.encode("utf-8"))


def summarize_tool_registry(
    registry: ToolRegistry,
    tool_config: ToolConfig,
) -> Dict[str, Any]:
    """Summarize effective Tool capabilities without retaining full schemas."""
    descriptors = [
        descriptor
        for descriptor in registry.apply_config(tool_config, effective=True)
        if descriptor.enabled
    ]
    categories = {
        "requires_sandbox": 0,
        "requires_browser": 0,
        "no_sandbox": 0,
    }
    groups: Dict[str, Dict[str, Any]] = {}
    for descriptor in descriptors:
        if descriptor.requires_browser:
            category = "requires_browser"
        elif descriptor.requires_sandbox:
            category = "requires_sandbox"
        else:
            category = "no_sandbox"
        categories[category] += 1
        group = groups.setdefault(
            descriptor.group,
            {"function_count": 0, "categories": set()},
        )
        group["function_count"] += 1
        group["categories"].add(category)

    group_summary = {}
    for group_name in sorted(groups):
        group = groups[group_name]
        group_categories = sorted(group["categories"])
        group_summary[group_name] = {
            "function_count": group["function_count"],
            "category": (
                group_categories[0] if len(group_categories) == 1 else "mixed"
            ),
        }
    return {
        "group_count": len(group_summary),
        "function_count": len(descriptors),
        "categories": categories,
        "groups": group_summary,
        "tool_schema_bytes": tool_schema_bytes(
            [descriptor.tool_schema for descriptor in descriptors]
        ),
    }


def _schema_json_default(value: Any) -> str:
    if callable(value):
        module = getattr(value, "__module__", type(value).__module__)
        name = getattr(value, "__qualname__", getattr(value, "__name__", type(value).__name__))
        return f"{module}.{name}"
    return type(value).__name__


def _event_type(event: BaseEvent) -> str:
    if isinstance(event, PlanEvent):
        return f"plan.{event.status.value}"
    if isinstance(event, StepEvent):
        return f"step.{event.status.value}"
    if isinstance(event, ToolEvent):
        return f"tool.{event.status.value}"
    if isinstance(event, InteractionEvent):
        return f"interaction.{event.status.value}"
    if isinstance(event, MessageEvent):
        return "message.created"
    if isinstance(event, WaitEvent):
        return "wait.created"
    if isinstance(event, ErrorEvent):
        return "error.created"
    if isinstance(event, DoneEvent):
        return "done.created"
    return f"{event.type}.created" if event.type else "event.created"


def _event_payload(event: BaseEvent) -> Dict[str, Any]:
    if isinstance(event, PlanEvent):
        return {
            "plan_id": event.plan.id,
            "title": _preview(event.plan.title, 120),
            "goal": _preview(event.plan.goal, 300),
            "status": event.plan.status.value,
            "event_status": event.status.value,
            "steps": [
                {
                    "step_id": step.id,
                    "description": _preview(step.description, 300),
                    "status": step.status.value,
                    "success": step.success,
                    "result_summary": _preview(step.result or "", 300),
                    "has_error": bool(step.error),
                }
                for step in event.plan.steps
            ],
        }
    if isinstance(event, StepEvent):
        return {
            "step_id": event.step.id,
            "description": _preview(event.step.description, 300),
            "status": event.status.value,
            "success": event.step.success,
            "result_summary": _preview(event.step.result or "", 300),
            "has_error": bool(event.step.error),
        }
    if isinstance(event, ToolEvent):
        return {
            "tool_call_id": event.tool_call_id,
            "tool_name": event.tool_name,
            "function_name": event.function_name,
            "arguments_hash": _hash_value(event.function_args),
            "status": event.status.value,
            "success": (
                event.function_result.success
                if event.function_result is not None
                else None
            ),
        }
    if isinstance(event, InteractionEvent):
        return {
            "action_id": event.action_id,
            "interaction_type": event.interaction_type.value,
            "status": event.status.value,
            "decision": event.decision.value if event.decision else None,
            "tool_call_id": event.tool_call_id,
            "tool_name": event.tool_name,
            "function_name": event.function_name,
            "risk_level": event.risk_level,
            "prompt": _preview(event.prompt, 300),
            "option_count": len(event.options),
            "allow_multiple": event.allow_multiple,
            "allow_text": event.allow_text,
            "selected_values": [_preview(item, 120) for item in event.selected_values[:20]],
            "plan_id": event.plan_id,
            "step_id": event.step_id,
        }
    if isinstance(event, MessageEvent):
        return {
            "role": event.role,
            "visible": event.visible,
            "stream_id": event.stream_id,
            "content_length": len(event.message or ""),
            "attachment_count": len(event.attachments),
        }
    if isinstance(event, ErrorEvent):
        failure = event.failure
        return {
            "has_failure": failure is not None,
            "failure": (
                {
                    "category": failure.category.value,
                    "scope": failure.scope.value,
                    "source": failure.source,
                    "code": failure.code,
                    "message": _preview(failure.message, 300),
                    "retryable": failure.retryable,
                    "debug_id": failure.debug_id,
                    "recovery_actions": [action.value for action in failure.recovery_actions],
                    "provider_id": failure.provider_id,
                    "tool_call_id": failure.tool_call_id,
                }
                if failure is not None
                else None
            ),
        }
    if isinstance(event, WaitEvent):
        return {"status": "waiting"}
    if isinstance(event, DoneEvent):
        return {"status": "completed"}
    return {"event_type": event.type or "event"}


def _safe_trace_payload(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the allowlisted payload persisted and exposed by Trace v2."""
    if event_type == "run.started":
        return _snapshot(
            {
                "attachment_count": payload.get("attachment_count", 0),
                "tool_registry": payload.get("tool_registry", {}),
            }
        )
    if event_type.startswith("lead."):
        return _allowlist(
            payload,
            "mode",
            "reason_code",
            "decision_latency_ms",
            "error_type",
            "count",
            "step_id",
            "status",
            "replan_count",
        )
    if event_type.startswith("model."):
        safe = _allowlist(
            payload,
            "model_call_id",
            "agent_name",
            "model_name",
            "tool_schema_count",
            "tool_schema_bytes",
            "capability_groups",
            "provider_ids",
            "tool_ids",
            "tool_scope_excluded_count",
            "message_count",
            "latency_ms",
            "ttft_ms",
            "finish_reason",
            "error_type",
        )
        usage = payload.get("usage")
        if isinstance(usage, dict):
            safe["usage"] = _allowlist(
                usage,
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
            )
        return _snapshot(safe)
    if event_type.startswith("plan."):
        return _safe_plan_payload(payload)
    if event_type.startswith("step."):
        return _snapshot(
            _allowlist(
                payload,
                "step_id",
                "description",
                "status",
                "success",
                "result_summary",
                "has_error",
            )
        )
    if event_type.startswith("tool."):
        return _snapshot(
            _allowlist(
                payload,
                "tool_call_id",
                "tool_id",
                "tool_name",
                "function_name",
                "arguments_hash",
                "status",
                "success",
                "provider_id",
                "source_type",
                "execution_backend",
                "execution_class",
                "generality",
                "cost_class",
                "error_code",
                "failure_category",
            )
        )
    if event_type.startswith("interaction."):
        return _snapshot(
            _allowlist(
                payload,
                "action_id",
                "interaction_type",
                "status",
                "decision",
                "tool_call_id",
                "tool_name",
                "function_name",
                "risk_level",
                "prompt",
                "option_count",
                "allow_multiple",
                "allow_text",
                "selected_values",
                "plan_id",
                "step_id",
            )
        )
    if event_type == "message.created":
        return _snapshot(
            _allowlist(
                payload,
                "role",
                "visible",
                "stream_id",
                "content_length",
                "attachment_count",
            )
        )
    if event_type == "error.created":
        return _snapshot(_allowlist(payload, "has_failure", "failure"))
    if event_type in {"wait.created", "done.created"}:
        return _snapshot(_allowlist(payload, "status"))
    if event_type.startswith("sandbox."):
        return _snapshot(
            _allowlist(
                payload,
                "activation_reason",
                "first_capability",
                "operation_counts",
                "startup_ms",
                "attachment_sync_bytes",
                "outcome",
                "error_type",
            )
        )
    if event_type.startswith("skill."):
        return _snapshot(
            _allowlist(
                payload,
                "version_id",
                "version",
                "selection_mode",
                "confidence",
                "package_sha256",
                "requested_key",
                "code",
                "error_type",
            )
        )
    if event_type == "run.cancellation_requested":
        return _snapshot(_allowlist(payload, "reason", "requested_by", "requested_at"))
    return {}


def _safe_plan_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    steps = []
    for item in payload.get("steps") or []:
        if not isinstance(item, dict):
            continue
        steps.append(
            _allowlist(
                item,
                "step_id",
                "description",
                "status",
                "success",
                "result_summary",
                "has_error",
            )
        )
    return _snapshot(
        {
            **_allowlist(
                payload,
                "plan_id",
                "title",
                "goal",
                "status",
                "event_status",
            ),
            "steps": steps,
        }
    )


def _allowlist(payload: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}


def _trace_node_identity(
    *,
    run_id: str,
    event_type: str,
    payload: Dict[str, Any],
    event_id: str | None,
    active_plan_id: str | None,
    active_step_id: str | None,
) -> tuple[str, str | None]:
    root = f"run:{run_id}"
    if event_type == "run.started":
        return root, None
    if event_type == "lead.strategy_selected":
        return f"strategy:{run_id}", root
    if event_type == "lead.replanned":
        return f"replan:{run_id}:{payload.get('count', 0)}", (
            f"plan:{active_plan_id}" if active_plan_id else root
        )
    if event_type in {"lead.completed", "done.created"}:
        return f"completion:{run_id}", root
    if event_type.startswith("plan."):
        plan_id = str(payload.get("plan_id") or active_plan_id or run_id)
        return f"plan:{plan_id}", root
    if event_type.startswith("step."):
        step_id = str(payload.get("step_id") or event_id or "unknown")
        parent = f"plan:{active_plan_id}" if active_plan_id else root
        return f"step:{step_id}", parent
    if event_type.startswith("tool."):
        call_id = str(payload.get("tool_call_id") or event_id or "unknown")
        parent = f"step:{active_step_id}" if active_step_id else root
        return f"tool:{call_id}", parent
    if event_type.startswith("model."):
        call_id = str(payload.get("model_call_id") or event_id or "unknown")
        parent = f"step:{active_step_id}" if active_step_id else root
        return f"model:{call_id}", parent
    if event_type.startswith("interaction."):
        action_id = str(payload.get("action_id") or event_id or "unknown")
        step_id = payload.get("step_id") or active_step_id
        parent = f"step:{step_id}" if step_id else root
        return f"interaction:{action_id}", parent
    if event_type == "message.created":
        prefix = "response" if payload.get("role") == "assistant" else "input"
        return f"{prefix}:{event_id or run_id}", root
    if event_type == "error.created":
        return f"error:{event_id or run_id}", root
    if event_type.startswith("sandbox."):
        return f"sandbox:{run_id}", root
    if event_type.startswith("skill."):
        return f"skill:{event_id or event_type}:{run_id}", root
    return f"event:{event_id or uuid.uuid4()}", root


def _event_summary(event_type: str, payload: Dict[str, Any]) -> str:
    if event_type == "run.started":
        return "开始处理请求"
    if event_type == "lead.strategy_selected":
        mode = payload.get("mode") or "direct"
        labels = {
            "direct": "直接回答，无需工具",
            "react": "逐步思考并使用工具",
            "plan": "任务较复杂，先制定计划",
        }
        return labels.get(str(mode), "已选择执行策略")
    if event_type.startswith("plan."):
        return str(payload.get("title") or payload.get("goal") or "任务计划")
    if event_type.startswith("step."):
        return str(payload.get("description") or "执行步骤")
    if event_type.startswith("tool."):
        return str(payload.get("function_name") or payload.get("tool_name") or "调用工具")
    if event_type.startswith("model."):
        return "模型调用失败" if event_type.endswith("failed") else "模型处理中"
    if event_type.startswith("interaction."):
        return str(payload.get("prompt") or "等待用户输入")
    if event_type == "error.created":
        failure = payload.get("failure") or {}
        return str(failure.get("message") or "执行失败")
    if event_type in {"lead.completed", "done.created"}:
        return "任务已完成"
    if event_type == "wait.created":
        return "等待用户输入"
    return event_type


def _snapshot(value: Any) -> Any:
    return _clip(_redact(_to_plain(value)))


def _to_plain(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                redacted[key] = "******"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _clip(value: Any, max_chars: int = PREVIEW_LIMIT) -> Any:
    if isinstance(value, dict):
        return {key: _clip(item, max_chars=max_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_clip(item, max_chars=max_chars) for item in value[:50]]
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + "...[truncated]"
    return value


def _preview(value: Any, max_chars: int = PREVIEW_LIMIT) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(_snapshot(value), ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
    return text if len(text) <= max_chars else text[:max_chars] + "...[truncated]"


def _hash_value(value: Any) -> str:
    try:
        payload = json.dumps(_snapshot(value), ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        payload = str(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_agent_snapshot(config: AgentConfig | None) -> Dict[str, Any]:
    if config is None:
        return {}
    return {
        "max_iterations": config.max_iterations,
        "max_retries": config.max_retries,
        "max_search_results": config.max_search_results,
    }


def _safe_llm_snapshot(config: LLMConfig | None) -> Dict[str, Any]:
    if config is None:
        return {}
    return {
        "provider": _provider_from_base_url(str(config.base_url)),
        "model_name": config.model_name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }


def _public_run(record: Dict[str, Any]) -> Dict[str, Any]:
    projected = _allowlist(
        record,
        "id",
        "trace_id",
        "user_id",
        "session_id",
        "task_id",
        "input_event_id",
        "status",
        "started_at",
        "finished_at",
        "updated_at",
        "created_at",
    )
    return {
        **projected,
        "input_summary": "",
        "final_summary": "",
        "error": "Agent run failed" if record.get("error") else None,
        "tool_config_snapshot": {},
        "agent_config_snapshot": _allowlist(
            record.get("agent_config_snapshot") or {},
            "max_iterations",
            "max_retries",
            "max_search_results",
        ),
        "llm_config_snapshot": _allowlist(
            record.get("llm_config_snapshot") or {},
            "provider",
            "model_name",
            "temperature",
            "max_tokens",
        ),
    }


def _public_step(record: Dict[str, Any]) -> Dict[str, Any]:
    projected = _allowlist(
        record,
        "id",
        "run_id",
        "session_id",
        "event_id",
        "step_id",
        "step_index",
        "title",
        "description",
        "status",
        "success",
        "result_summary",
        "started_at",
        "finished_at",
        "updated_at",
        "created_at",
    )
    projected["error"] = "Step failed" if record.get("error") else None
    projected["attachments"] = []
    return projected


def _public_tool_call(record: Dict[str, Any]) -> Dict[str, Any]:
    projected = _allowlist(
        record,
        "id",
        "run_id",
        "run_step_id",
        "step_id",
        "session_id",
        "event_id",
        "tool_call_id",
        "tool_id",
        "tool_name",
        "function_name",
        "provider_id",
        "registration_id",
        "source_type",
        "executor_type",
        "risk_level",
        "enabled_effective",
        "requires_sandbox",
        "requires_browser",
        "requires_credentials",
        "status",
        "arguments_hash",
        "success",
        "latency_ms",
        "started_at",
        "finished_at",
        "updated_at",
        "created_at",
    )
    return {
        **projected,
        "arguments": {},
        "arguments_preview": "",
        "result": {},
        "result_preview": "",
        "error": "Tool call failed" if record.get("error") else None,
    }


def _public_model_call(record: Dict[str, Any]) -> Dict[str, Any]:
    projected = _allowlist(
        record,
        "id",
        "run_id",
        "run_step_id",
        "step_id",
        "session_id",
        "agent_name",
        "model_name",
        "temperature",
        "max_tokens",
        "tool_schema_count",
        "message_count",
        "tool_choice",
        "status",
        "finish_reason",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "latency_ms",
        "ttft_ms",
        "started_at",
        "finished_at",
        "updated_at",
        "created_at",
    )
    return {
        **projected,
        "provider": _safe_provider_id(str(record.get("provider") or "")),
        "base_url": "",
        "response_format": {},
        "request_preview": {},
        "response_preview": {},
        "error": "Model call failed" if record.get("error") else None,
    }


def _public_trace_event(record: Dict[str, Any]) -> Dict[str, Any] | None:
    if record.get("visibility", "user") != "user":
        return None
    event_type = str(record.get("event_type") or "event.created")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    return {
        **_allowlist(
            record,
            "id",
            "trace_id",
            "run_id",
            "session_id",
            "event_id",
            "event_type",
            "ingest_seq",
            "schema_version",
            "node_id",
            "parent_node_id",
            "visibility",
            "summary",
            "created_at",
        ),
        "payload": _safe_trace_payload(event_type, payload),
    }


def _public_run_skill(record: Dict[str, Any]) -> Dict[str, Any]:
    return _allowlist(
        record,
        "id",
        "run_id",
        "skill_id",
        "skill_version_id",
        "name",
        "source",
        "selection_mode",
        "content_sha256",
        "confidence",
        "created_at",
    )


def _selected_skill_payload(selected: SelectedSkill) -> Dict[str, Any]:
    return {
        "ref": selected.ref,
        "version_id": selected.version_id,
        "version": selected.version,
        "selection_mode": selected.selection_mode,
        "confidence": selected.confidence,
        "reason": selected.reason,
        "package_sha256": selected.package_sha256,
    }


def _provider_from_base_url(base_url: str) -> str:
    hostname = urlparse(base_url).hostname or ""
    return _safe_provider_id(hostname)


def _safe_provider_id(value: str) -> str:
    normalized = value.lower()
    if "deepseek" in normalized:
        return "deepseek"
    if "openai" in normalized:
        return "openai"
    if "dashscope" in normalized or "aliyun" in normalized:
        return "dashscope"
    if "anthropic" in normalized:
        return "anthropic"
    if "google" in normalized or "gemini" in normalized:
        return "google"
    return "openai-compatible"
