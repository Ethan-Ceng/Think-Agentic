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
        self._active_step_id: str | None = None
        self._active_run_step_id: str | None = None
        self._tool_started_at: Dict[str, datetime] = {}
        self._terminal_failed = False

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
        self._active_step_id = None
        self._active_run_step_id = None
        self._tool_started_at = {}
        self._terminal_failed = False
        now = datetime.now()
        run_data = {
            "id": self.run_id,
            "trace_id": self.trace_id,
            "user_id": user_id,
            "session_id": session_id,
            "task_id": task_id,
            "input_event_id": input_event.id,
            "status": "running",
            "input_summary": _preview(input_event.message),
            "tool_config_snapshot": _snapshot(self._tool_config),
            "agent_config_snapshot": _snapshot(self._agent_config),
            "llm_config_snapshot": _snapshot(self._llm_config),
            "started_at": now,
        }

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.create_run(run_data)
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="run.started",
                    event_id=input_event.id,
                    payload={
                        "message": _preview(input_event.message),
                        "attachments": _snapshot(input_event.attachments),
                    },
                    created_at=now,
                )
            )

        await self._write(write)
        return self.run_id

    async def project_event(self, event: BaseEvent) -> None:
        """Project one runtime event into trace tables."""
        if not self.run_id or not self.trace_id or not self.session_id:
            return

        async def write(uow: IUnitOfWork) -> None:
            await self._project_event(uow, event)

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
        request_preview = {
            "messages": _summarize_messages(messages),
            "tools": [_tool_name(tool) for tool in tools],
        }
        data = {
            "id": model_call_id,
            "run_id": self.run_id,
            "run_step_id": self._active_run_step_id,
            "step_id": self._active_step_id,
            "session_id": self.session_id,
            "agent_name": agent_name,
            "provider": _provider_from_base_url(base_url),
            "base_url": base_url,
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
        data = {
            "status": "failed" if error else "succeeded",
            "finish_reason": metadata.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "latency_ms": latency_ms,
            "response_preview": _snapshot(_summarize_model_response(message or {})),
            "error": error,
            "finished_at": finished_at,
        }

        async def write(uow: IUnitOfWork) -> None:
            await uow.trace.update_model_call(model_call_id, data)
            await uow.trace.append_event(
                self._trace_event_data(
                    event_type="model.failed" if error else "model.succeeded",
                    payload={
                        "model_call_id": model_call_id,
                        "latency_ms": latency_ms,
                        "finish_reason": metadata.get("finish_reason"),
                        "usage": _snapshot(usage),
                        "error": error,
                    },
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
            return await uow.trace.list_runs(user_id=user_id, session_id=session_id, limit=limit)

    async def get_run_detail(self, user_id: str, run_id: str) -> Dict[str, Any]:
        uow = self._uow_factory()
        async with uow:
            run = await uow.trace.get_run(user_id=user_id, run_id=run_id)
            if not run:
                raise NotFoundError("运行记录不存在")
            return {
                "run": run,
                "steps": await uow.trace.list_steps(run_id),
                "tool_calls": await uow.trace.list_tool_calls(run_id),
                "model_calls": await uow.trace.list_model_calls(run_id),
                "events": await uow.trace.list_trace_events(run_id),
                "skills": await uow.trace.list_run_skills(user_id, run_id),
            }

    async def list_events(self, user_id: str, run_id: str) -> List[Dict[str, Any]]:
        return (await self.get_run_detail(user_id, run_id))["events"]

    async def list_tool_calls(self, user_id: str, run_id: str) -> List[Dict[str, Any]]:
        return (await self.get_run_detail(user_id, run_id))["tool_calls"]

    async def list_model_calls(self, user_id: str, run_id: str) -> List[Dict[str, Any]]:
        return (await self.get_run_detail(user_id, run_id))["model_calls"]

    async def list_run_skills(
        self, user_id: str, run_id: str
    ) -> List[Dict[str, Any]]:
        uow = self._uow_factory()
        async with uow:
            run = await uow.trace.get_run(user_id=user_id, run_id=run_id)
            if not run:
                raise NotFoundError("运行记录不存在")
            return await uow.trace.list_run_skills(user_id, run_id)

    async def _project_event(self, uow: IUnitOfWork, event: BaseEvent) -> None:
        event_type = _event_type(event)
        await uow.trace.append_event(
            self._trace_event_data(
                event_type=event_type,
                event_id=event.id,
                payload=_event_payload(event),
                created_at=event.created_at,
            )
        )

        if isinstance(event, StepEvent):
            await self._project_step(uow, event)
        elif isinstance(event, ToolEvent):
            await self._project_tool_call(uow, event)
        elif isinstance(event, MessageEvent):
            if event.role == "assistant" and event.message:
                await uow.trace.update_run(self.run_id, {"final_summary": _preview(event.message)})
        elif isinstance(event, WaitEvent):
            await uow.trace.update_run(self.run_id, {"status": "waiting"})
        elif isinstance(event, ErrorEvent):
            self._terminal_failed = True
            await uow.trace.update_run(
                self.run_id,
                {
                    "status": "failed",
                    "error": _preview(event.error),
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
            result_data = _snapshot(event.function_result)
            result_preview = _preview(result_data)

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
            "arguments": _snapshot(event.function_args),
            "arguments_preview": _preview(event.function_args),
            "arguments_hash": _hash_value(event.function_args),
            "result": result_data,
            "result_preview": result_preview,
            "success": success,
            "error": error,
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
    ) -> Dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "event_id": event_id,
            "event_type": event_type,
            "payload": _snapshot(payload),
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
        source_type = "builtin"
        if executor_type == "api":
            source_type = "api"
            registration = self._registration_for_provider(provider_id)
            if registration:
                registration_id = registration.registration_id
        elif executor_type == "mcp":
            source_type = "mcp"
        elif executor_type == "a2a":
            source_type = "a2a"
        return {
            "tool_id": tool_id,
            "provider_id": provider_id,
            "registration_id": registration_id,
            "source_type": source_type,
            "executor_type": executor_type,
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


def _event_type(event: BaseEvent) -> str:
    if isinstance(event, PlanEvent):
        return f"plan.{event.status.value}"
    if isinstance(event, StepEvent):
        return f"step.{event.status.value}"
    if isinstance(event, ToolEvent):
        return f"tool.{event.status.value}"
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
    if isinstance(event, ToolEvent):
        return {
            "tool_call_id": event.tool_call_id,
            "tool_name": event.tool_name,
            "function_name": event.function_name,
            "function_args": _snapshot(event.function_args),
            "function_result": _snapshot(event.function_result),
            "status": event.status.value,
        }
    return event.model_dump(mode="json")


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


def _summarize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary = []
    for message in messages[-20:]:
        content = message.get("content", "")
        if (
            isinstance(content, str)
            and "<skill_runtime_context>" in content
        ):
            content = "[skill runtime context omitted]"
        summary.append(
            {
                "role": message.get("role"),
                "content": _preview(content),
                "has_tool_calls": bool(message.get("tool_calls")),
                "tool_call_id": message.get("tool_call_id"),
            }
        )
    return summary


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


def _summarize_model_response(message: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role": message.get("role"),
        "content": _preview(message.get("content", "")),
        "tool_calls": [
            {
                "id": item.get("id"),
                "function": {
                    "name": (item.get("function") or {}).get("name"),
                    "arguments": _preview((item.get("function") or {}).get("arguments", "")),
                },
            }
            for item in (message.get("tool_calls") or [])[:5]
        ],
        "reasoning_content": _preview(message.get("reasoning_content", "")),
    }


def _tool_name(tool_schema: Dict[str, Any]) -> str:
    return str(((tool_schema or {}).get("function") or {}).get("name") or "")


def _provider_from_base_url(base_url: str) -> str:
    hostname = urlparse(base_url).hostname or ""
    return hostname
