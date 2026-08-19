#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build a safe execution tree from append-only Trace events."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from app.schemas.run_execution import (
    ExecutionDetailKind,
    ExecutionFailure,
    ExecutionMetrics,
    ExecutionNode,
    ExecutionNodeKind,
    ExecutionNodeStatus,
    ExecutionPhase,
    RunExecutionOverview,
    RunExecutionView,
)


class ExecutionViewAssembler:
    """Pure projection. It never drives or mutates Agent runtime state."""

    def assemble(
        self,
        *,
        run: dict[str, Any],
        events: Iterable[dict[str, Any]],
        next_cursor: int | None,
        has_more: bool,
        detail: str = "summary",
    ) -> RunExecutionView:
        latest: dict[str, ExecutionNode] = {}
        mode: str | None = None
        warnings: list[str] = []
        trace_complete = True

        for event in sorted(events, key=_cursor):
            if int(event.get("schema_version") or 1) < 2:
                trace_complete = False
                if "historical_trace_v1" not in warnings:
                    warnings.append("historical_trace_v1")
            try:
                projected, event_mode = self._project_event(run, event, detail)
            except (TypeError, ValueError, KeyError):
                trace_complete = False
                if "trace_node_skipped" not in warnings:
                    warnings.append("trace_node_skipped")
                continue
            if event_mode:
                mode = event_mode
            for node in projected:
                current = latest.get(node.node_id)
                if current is None or node.cursor >= current.cursor:
                    latest[node.node_id] = _merge_node(current, node)

        nodes = sorted(latest.values(), key=lambda item: (item.cursor, item.node_id))
        active_steps_by_plan: dict[str, int] = {}
        for node in nodes:
            if (
                node.kind == ExecutionNodeKind.STEP
                and node.parent_node_id
                and node.status
                in {ExecutionNodeStatus.RUNNING, ExecutionNodeStatus.WAITING}
            ):
                active_steps_by_plan[node.parent_node_id] = (
                    active_steps_by_plan.get(node.parent_node_id, 0) + 1
                )
        if any(count > 1 for count in active_steps_by_plan.values()):
            trace_complete = False
            warnings.append("plan_parallel_state")
        overview = self._overview(run, nodes, mode)
        return RunExecutionView(
            run=overview,
            nodes=nodes,
            next_cursor=next_cursor,
            has_more=has_more,
            trace_complete=trace_complete,
            warnings=warnings,
        )

    def _project_event(
        self,
        run: dict[str, Any],
        event: dict[str, Any],
        detail: str,
    ) -> tuple[list[ExecutionNode], str | None]:
        event_type = str(event.get("event_type") or "event.created")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        cursor = _cursor(event)
        created_at = _datetime(event.get("created_at"))
        node_id = str(event.get("node_id") or _legacy_node_id(run, event_type, payload))
        parent_node_id = event.get("parent_node_id") or _legacy_parent_id(run, event_type, payload)
        summary = _clip(str(event.get("summary") or ""), 500)
        run_root = f"run:{run['id']}"

        if event_type == "run.started":
            return [
                ExecutionNode(
                    node_id=run_root,
                    parent_node_id=None,
                    kind=ExecutionNodeKind.RUN,
                    phase=ExecutionPhase.DECIDE,
                    status=ExecutionNodeStatus.RUNNING,
                    title="开始处理请求",
                    summary=summary or "开始处理请求",
                    cursor=cursor,
                    started_at=created_at,
                )
            ], None

        if event_type == "lead.strategy_selected":
            mode = str(payload.get("mode") or "direct")
            titles = {
                "direct": "直接回答",
                "react": "逐步执行",
                "plan": "计划执行",
            }
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.STRATEGY,
                    phase=ExecutionPhase.DECIDE,
                    status=ExecutionNodeStatus.SUCCEEDED,
                    title=titles.get(mode, "已选择执行方式"),
                    summary=summary or titles.get(mode, "已选择执行方式"),
                    cursor=cursor,
                    started_at=created_at,
                    finished_at=created_at,
                    latency_ms=_non_negative(payload.get("decision_latency_ms")),
                    metrics=ExecutionMetrics(
                        decision_latency_ms=_non_negative(
                            payload.get("decision_latency_ms")
                        )
                    ),
                )
            ], mode

        if event_type == "lead.fallback":
            reason_code = str(payload.get("reason_code") or "strategy_unavailable")
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.STRATEGY,
                    phase=ExecutionPhase.DECIDE,
                    status=ExecutionNodeStatus.SUCCEEDED,
                    title="已回退兼容执行链",
                    summary=reason_code,
                    cursor=cursor,
                    started_at=created_at,
                    finished_at=created_at,
                )
            ], None

        if event_type.startswith("plan."):
            return self._plan_nodes(run, event, payload, summary), "plan"

        if event_type == "lead.replanned":
            count = _non_negative(payload.get("count")) or 0
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.PLAN,
                    phase=ExecutionPhase.PLAN,
                    status=ExecutionNodeStatus.SUCCEEDED,
                    title=f"计划已调整 {count} 次",
                    summary=summary or "已根据执行结果调整后续计划",
                    cursor=cursor,
                    started_at=created_at,
                    finished_at=created_at,
                    metrics=ExecutionMetrics(replan_count=count),
                )
            ], "plan"

        if event_type.startswith("step."):
            status = _status(payload.get("status") or event_type.removeprefix("step."))
            step_id = str(payload.get("step_id") or node_id.removeprefix("step:"))
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.STEP,
                    phase=ExecutionPhase.EXECUTE,
                    status=status,
                    title=_clip(str(payload.get("description") or summary or "执行步骤"), 120),
                    summary=_clip(
                        str(payload.get("result_summary") or summary or ""), 500
                    ),
                    cursor=cursor,
                    started_at=created_at if status == ExecutionNodeStatus.RUNNING else None,
                    finished_at=(
                        created_at
                        if status
                        in {ExecutionNodeStatus.SUCCEEDED, ExecutionNodeStatus.FAILED}
                        else None
                    ),
                    failure=(
                        _generic_failure("STEP_FAILED", "步骤执行失败", "step")
                        if status == ExecutionNodeStatus.FAILED
                        else None
                    ),
                    detail_kind=ExecutionDetailKind.STEP,
                    detail_id=step_id,
                )
            ], None

        if event_type.startswith("tool."):
            success = payload.get("success")
            status = (
                ExecutionNodeStatus.RUNNING
                if event_type.endswith("calling")
                else ExecutionNodeStatus.SUCCEEDED
                if success is not False
                else ExecutionNodeStatus.FAILED
            )
            call_id = str(payload.get("tool_call_id") or node_id.removeprefix("tool:"))
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.TOOL,
                    phase=ExecutionPhase.EXECUTE,
                    status=status,
                    title=_clip(
                        str(
                            payload.get("function_name")
                            or payload.get("tool_name")
                            or summary
                            or "调用工具"
                        ),
                        120,
                    ),
                    summary=summary,
                    cursor=cursor,
                    started_at=created_at if status == ExecutionNodeStatus.RUNNING else None,
                    finished_at=created_at if status != ExecutionNodeStatus.RUNNING else None,
                    failure=(
                        _generic_failure(
                            str(payload.get("error_code") or "TOOL_CALL_FAILED"),
                            "工具调用失败",
                            "tool",
                            tool_call_id=call_id,
                        )
                        if status == ExecutionNodeStatus.FAILED
                        else None
                    ),
                    detail_kind=ExecutionDetailKind.TOOL,
                    detail_id=call_id,
                )
            ], None

        if event_type.startswith("model."):
            status = (
                ExecutionNodeStatus.RUNNING
                if event_type.endswith("started")
                else ExecutionNodeStatus.FAILED
                if event_type.endswith("failed")
                else ExecutionNodeStatus.SUCCEEDED
            )
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            call_id = str(payload.get("model_call_id") or node_id.removeprefix("model:"))
            metrics = ExecutionMetrics(
                prompt_tokens=_non_negative(usage.get("prompt_tokens")),
                completion_tokens=_non_negative(usage.get("completion_tokens")),
                total_tokens=_non_negative(usage.get("total_tokens")),
                ttft_ms=_non_negative(payload.get("ttft_ms")),
                message_count=_non_negative(payload.get("message_count")),
                tool_schema_count=_non_negative(payload.get("tool_schema_count")),
                tool_schema_bytes=_non_negative(payload.get("tool_schema_bytes")),
            )
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.MODEL,
                    phase=_model_phase(payload),
                    status=status,
                    title=_model_title(payload, status),
                    summary=summary,
                    cursor=cursor,
                    started_at=created_at if status == ExecutionNodeStatus.RUNNING else None,
                    finished_at=created_at if status != ExecutionNodeStatus.RUNNING else None,
                    latency_ms=_non_negative(payload.get("latency_ms")),
                    metrics=metrics,
                    failure=(
                        _generic_failure("MODEL_CALL_FAILED", "模型调用失败", "operation")
                        if status == ExecutionNodeStatus.FAILED
                        else None
                    ),
                    detail_kind=ExecutionDetailKind.MODEL,
                    detail_id=call_id,
                )
            ], None

        if event_type.startswith("interaction.") or event_type == "wait.created":
            resolved = event_type.endswith("resolved")
            action_id = str(payload.get("action_id") or node_id.removeprefix("interaction:"))
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.INTERACTION,
                    phase=ExecutionPhase.WAIT,
                    status=(
                        ExecutionNodeStatus.SUCCEEDED
                        if resolved
                        else ExecutionNodeStatus.WAITING
                    ),
                    title="已收到用户输入" if resolved else "等待你的输入",
                    summary=summary or "等待用户输入",
                    cursor=cursor,
                    started_at=created_at,
                    finished_at=created_at if resolved else None,
                    detail_kind=ExecutionDetailKind.INTERACTION,
                    detail_id=action_id,
                )
            ], None

        if event_type == "error.created":
            failure = payload.get("failure") if isinstance(payload.get("failure"), dict) else {}
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.ERROR,
                    phase=ExecutionPhase.FINALIZE,
                    status=ExecutionNodeStatus.FAILED,
                    title="执行失败",
                    summary=summary or str(failure.get("message") or "执行失败"),
                    cursor=cursor,
                    started_at=created_at,
                    finished_at=created_at,
                    failure=_failure(failure),
                )
            ], None

        if event_type == "lead.completed":
            completion_status = _status(payload.get("status") or "completed")
            mode = str(payload.get("mode") or "") or None
            if completion_status == ExecutionNodeStatus.WAITING:
                return [], mode
            failed = completion_status == ExecutionNodeStatus.FAILED
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.COMPLETION,
                    phase=ExecutionPhase.FINALIZE,
                    status=completion_status,
                    title="本次执行未完成" if failed else "任务已完成",
                    summary=summary or ("本次执行未完成" if failed else "任务已完成"),
                    cursor=cursor,
                    started_at=created_at,
                    finished_at=created_at,
                    failure=(
                        _generic_failure("AGENT_RUN_FAILED", "本次执行未完成", "run")
                        if failed
                        else None
                    ),
                )
            ], mode

        if event_type == "done.created":
            if _status(run.get("status")) == ExecutionNodeStatus.FAILED:
                return [], None
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.COMPLETION,
                    phase=ExecutionPhase.FINALIZE,
                    status=ExecutionNodeStatus.SUCCEEDED,
                    title="任务已完成",
                    summary=summary or "任务已完成",
                    cursor=cursor,
                    started_at=created_at,
                    finished_at=created_at,
                )
            ], None

        if event_type.startswith("skill."):
            return [
                ExecutionNode(
                    node_id=node_id,
                    parent_node_id=str(parent_node_id or run_root),
                    kind=ExecutionNodeKind.SKILL,
                    phase=ExecutionPhase.EXECUTE,
                    status=(
                        ExecutionNodeStatus.FAILED
                        if event_type.endswith("failed")
                        else ExecutionNodeStatus.SUCCEEDED
                    ),
                    title="Skill 准备",
                    summary=summary,
                    cursor=cursor,
                    started_at=created_at,
                    finished_at=created_at,
                )
            ], None

        # Message and technical-only events are deliberately absent from the user tree.
        return [], None

    def _plan_nodes(
        self,
        run: dict[str, Any],
        event: dict[str, Any],
        payload: dict[str, Any],
        summary: str,
    ) -> list[ExecutionNode]:
        cursor = _cursor(event)
        created_at = _datetime(event.get("created_at"))
        run_root = f"run:{run['id']}"
        plan_id = str(payload.get("plan_id") or run["id"])
        plan_node_id = str(event.get("node_id") or f"plan:{plan_id}")
        steps = [item for item in (payload.get("steps") or []) if isinstance(item, dict)]
        completed = sum(1 for item in steps if _status(item.get("status")) == ExecutionNodeStatus.SUCCEEDED)
        plan_status = _status(payload.get("status") or payload.get("event_status"))
        nodes = [
            ExecutionNode(
                node_id=plan_node_id,
                parent_node_id=str(event.get("parent_node_id") or run_root),
                kind=ExecutionNodeKind.PLAN,
                phase=ExecutionPhase.PLAN,
                status=plan_status,
                title=_clip(str(payload.get("title") or "任务计划"), 120),
                summary=_clip(str(payload.get("goal") or summary or ""), 500),
                cursor=cursor,
                started_at=created_at,
                finished_at=(
                    created_at
                    if plan_status in {ExecutionNodeStatus.SUCCEEDED, ExecutionNodeStatus.FAILED}
                    else None
                ),
                metrics=ExecutionMetrics(
                    step_count=len(steps),
                    completed_steps=completed,
                    revision=_non_negative(payload.get("revision")) or 1,
                    replan_count=_non_negative(payload.get("replan_count")) or 0,
                ),
            )
        ]
        for index, step in enumerate(steps):
            step_id = str(step.get("step_id") or f"index-{index}")
            status = _status(step.get("status"))
            nodes.append(
                ExecutionNode(
                    node_id=f"step:{step_id}",
                    parent_node_id=plan_node_id,
                    kind=ExecutionNodeKind.STEP,
                    phase=ExecutionPhase.EXECUTE,
                    status=status,
                    title=_clip(str(step.get("description") or f"步骤 {index + 1}"), 120),
                    summary=_clip(str(step.get("result_summary") or ""), 500),
                    cursor=cursor,
                    ordinal=index,
                    failure=(
                        _generic_failure("STEP_FAILED", "步骤执行失败", "step")
                        if status == ExecutionNodeStatus.FAILED
                        else None
                    ),
                    detail_kind=ExecutionDetailKind.STEP,
                    detail_id=step_id,
                )
            )
        return nodes

    @staticmethod
    def _overview(
        run: dict[str, Any], nodes: list[ExecutionNode], mode: str | None
    ) -> RunExecutionOverview:
        started_at = _datetime(run.get("started_at") or run.get("created_at"))
        finished_at = _datetime(run.get("finished_at"))
        latency_ms = None
        if started_at and finished_at:
            latency_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        step_nodes = [item for item in nodes if item.kind == ExecutionNodeKind.STEP]
        tool_nodes = [item for item in nodes if item.kind == ExecutionNodeKind.TOOL]
        model_nodes = [item for item in nodes if item.kind == ExecutionNodeKind.MODEL]
        latest = nodes[-1].summary if nodes else ""
        return RunExecutionOverview(
            run_id=str(run["id"]),
            session_id=str(run.get("session_id") or ""),
            input_event_id=run.get("input_event_id"),
            status=_status(run.get("status")),
            mode=mode,
            summary=_clip(latest, 500),
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            metrics=ExecutionMetrics(
                prompt_tokens=_sum_metric(model_nodes, "prompt_tokens"),
                completion_tokens=_sum_metric(model_nodes, "completion_tokens"),
                total_tokens=_sum_metric(model_nodes, "total_tokens"),
                ttft_ms=_min_metric(model_nodes, "ttft_ms"),
                step_count=len(step_nodes),
                completed_steps=sum(
                    1 for item in step_nodes if item.status == ExecutionNodeStatus.SUCCEEDED
                ),
                tool_count=len(tool_nodes),
                model_count=len(model_nodes),
                replan_count=max(
                    (item.metrics.replan_count or 0 for item in nodes), default=0
                ),
            ),
        )


def _cursor(event: dict[str, Any]) -> int:
    return max(0, int(event.get("ingest_seq") or 0))


def _merge_node(
    current: ExecutionNode | None,
    incoming: ExecutionNode,
) -> ExecutionNode:
    """Apply a newer node update without losing lifecycle metadata."""
    if current is None:
        return incoming
    metrics = {
        **current.metrics.model_dump(exclude_none=True),
        **incoming.metrics.model_dump(exclude_none=True),
    }
    return incoming.model_copy(
        update={
            "parent_node_id": incoming.parent_node_id or current.parent_node_id,
            "phase": current.phase,
            "summary": incoming.summary or current.summary,
            "ordinal": (
                incoming.ordinal
                if incoming.ordinal is not None
                else current.ordinal
            ),
            "started_at": current.started_at or incoming.started_at,
            "finished_at": incoming.finished_at or current.finished_at,
            "latency_ms": (
                incoming.latency_ms
                if incoming.latency_ms is not None
                else current.latency_ms
            ),
            "metrics": ExecutionMetrics(**metrics),
            "detail_kind": incoming.detail_kind or current.detail_kind,
            "detail_id": incoming.detail_id or current.detail_id,
        }
    )


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit]


def _sum_metric(nodes: list[ExecutionNode], field: str) -> int | None:
    values = [
        value
        for node in nodes
        if (value := getattr(node.metrics, field)) is not None
    ]
    return sum(values) if values else None


def _min_metric(nodes: list[ExecutionNode], field: str) -> int | None:
    values = [
        value
        for node in nodes
        if (value := getattr(node.metrics, field)) is not None
    ]
    return min(values) if values else None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _non_negative(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return max(0, int(value))


def _status(value: Any) -> ExecutionNodeStatus:
    normalized = str(value or "pending").lower()
    if normalized in {"started", "running", "calling", "created", "updated"}:
        return ExecutionNodeStatus.RUNNING
    if normalized in {"completed", "called", "succeeded", "success", "resolved"}:
        return ExecutionNodeStatus.SUCCEEDED
    if normalized in {"failed", "error", "blocked"}:
        return ExecutionNodeStatus.FAILED
    if normalized in {"waiting", "pending_input"}:
        return ExecutionNodeStatus.WAITING
    if normalized in {"cancelled", "canceled", "stopped"}:
        return ExecutionNodeStatus.CANCELLED
    return ExecutionNodeStatus.PENDING


def _model_phase(payload: dict[str, Any]) -> ExecutionPhase:
    agent_name = str(payload.get("agent_name") or "").lower()
    if "planner" in agent_name:
        return ExecutionPhase.PLAN
    if "lead" in agent_name:
        return ExecutionPhase.DECIDE
    return ExecutionPhase.RESPOND


def _model_title(payload: dict[str, Any], status: ExecutionNodeStatus) -> str:
    if status == ExecutionNodeStatus.FAILED:
        return "模型调用失败"
    phase = _model_phase(payload)
    if phase == ExecutionPhase.PLAN:
        return "正在制定计划"
    if phase == ExecutionPhase.DECIDE:
        return "正在判断执行方式"
    return "正在组织回答" if status == ExecutionNodeStatus.RUNNING else "已完成模型调用"


def _failure(payload: dict[str, Any]) -> ExecutionFailure:
    return ExecutionFailure(
        code=str(payload.get("code") or "AGENT_RUN_FAILED"),
        category=str(payload.get("category") or "runtime"),
        scope=str(payload.get("scope") or "run"),
        source=str(payload.get("source") or "agent"),
        message=_clip(str(payload.get("message") or "执行失败"), 500),
        retryable=bool(payload.get("retryable", False)),
        recovery_actions=[str(item) for item in (payload.get("recovery_actions") or [])],
        provider_id=payload.get("provider_id"),
        tool_call_id=payload.get("tool_call_id"),
        debug_id=str(payload.get("debug_id") or ""),
    )


def _generic_failure(
    code: str,
    message: str,
    scope: str,
    *,
    tool_call_id: str | None = None,
) -> ExecutionFailure:
    return ExecutionFailure(
        code=code,
        category="tool" if scope == "tool" else "runtime",
        scope=scope,
        source="agent",
        message=message,
        tool_call_id=tool_call_id,
    )


def _legacy_node_id(
    run: dict[str, Any], event_type: str, payload: dict[str, Any]
) -> str:
    run_id = str(run["id"])
    if event_type == "run.started":
        return f"run:{run_id}"
    if event_type == "lead.strategy_selected":
        return f"strategy:{run_id}"
    if event_type.startswith("plan."):
        return f"plan:{payload.get('plan_id') or run_id}"
    if event_type.startswith("step."):
        return f"step:{payload.get('step_id') or run_id}"
    if event_type.startswith("tool."):
        return f"tool:{payload.get('tool_call_id') or run_id}"
    if event_type.startswith("model."):
        return f"model:{payload.get('model_call_id') or run_id}"
    if event_type.startswith("interaction."):
        return f"interaction:{payload.get('action_id') or run_id}"
    if event_type == "error.created":
        return f"error:{run_id}"
    if event_type in {"lead.completed", "done.created"}:
        return f"completion:{run_id}"
    return f"event:{event_type}:{run_id}"


def _legacy_parent_id(
    run: dict[str, Any], event_type: str, payload: dict[str, Any]
) -> str | None:
    root = f"run:{run['id']}"
    if event_type == "run.started":
        return None
    step_id = payload.get("step_id")
    if step_id and (
        event_type.startswith("tool.")
        or event_type.startswith("model.")
        or event_type.startswith("interaction.")
    ):
        return f"step:{step_id}"
    return root
