from __future__ import annotations

from datetime import datetime, timedelta

from app.schemas.run_execution import ExecutionNodeKind, ExecutionNodeStatus
from app.services.execution_view import ExecutionViewAssembler


NOW = datetime(2026, 8, 19, 12, 0, 0)


def _run(**updates):
    data = {
        "id": "run-1",
        "session_id": "session-1",
        "input_event_id": "input-1",
        "status": "running",
        "started_at": NOW,
        "finished_at": None,
    }
    data.update(updates)
    return data


def _event(cursor, event_type, node_id, payload=None, parent=None, version=2):
    return {
        "ingest_seq": cursor,
        "schema_version": version,
        "event_type": event_type,
        "node_id": node_id,
        "parent_node_id": parent,
        "summary": event_type,
        "payload": payload or {},
        "created_at": NOW + timedelta(milliseconds=cursor),
    }


def test_assembler_builds_plan_tree_and_replaces_nodes_by_cursor() -> None:
    events = [
        _event(1, "run.started", "run:run-1"),
        _event(
            2,
            "lead.strategy_selected",
            "strategy:run-1",
            {"mode": "plan", "decision_latency_ms": 12},
            "run:run-1",
        ),
        _event(
            3,
            "plan.created",
            "plan:plan-1",
            {
                "plan_id": "plan-1",
                "title": "升级 Agent",
                "goal": "安全展示执行过程",
                "status": "running",
                "revision": 1,
                "replan_count": 0,
                "steps": [
                    {"step_id": "s1", "description": "检查实现", "status": "running"},
                    {"step_id": "s2", "description": "实现页面", "status": "pending"},
                ],
            },
            "run:run-1",
        ),
        _event(
            4,
            "tool.calling",
            "tool:t1",
            {"tool_call_id": "t1", "function_name": "search", "success": None},
            "step:s1",
        ),
        _event(
            5,
            "tool.called",
            "tool:t1",
            {"tool_call_id": "t1", "function_name": "search", "success": True},
            "step:s1",
        ),
        _event(
            6,
            "plan.updated",
            "plan:plan-1",
            {
                "plan_id": "plan-1",
                "title": "升级 Agent",
                "status": "running",
                "revision": 2,
                "replan_count": 1,
                "steps": [
                    {
                        "step_id": "s1",
                        "description": "检查实现",
                        "status": "completed",
                        "result_summary": "已完成",
                    },
                    {"step_id": "s2", "description": "实现页面", "status": "running"},
                ],
            },
            "run:run-1",
        ),
    ]

    view = ExecutionViewAssembler().assemble(
        run=_run(), events=reversed(events), next_cursor=6, has_more=False
    )

    by_id = {node.node_id: node for node in view.nodes}
    assert view.run.mode == "plan"
    assert view.next_cursor == 6
    assert by_id["plan:plan-1"].metrics.revision == 2
    assert by_id["plan:plan-1"].metrics.replan_count == 1
    assert by_id["step:s1"].status == ExecutionNodeStatus.SUCCEEDED
    assert by_id["step:s1"].cursor == 6
    assert by_id["step:s2"].status == ExecutionNodeStatus.RUNNING
    assert by_id["tool:t1"].status == ExecutionNodeStatus.SUCCEEDED
    assert by_id["tool:t1"].parent_node_id == "step:s1"
    assert len([node for node in view.nodes if node.node_id == "tool:t1"]) == 1


def test_assembler_projects_direct_ask_resume_and_failure_without_raw_payload() -> None:
    events = [
        _event(1, "run.started", "run:run-1"),
        _event(
            2,
            "lead.strategy_selected",
            "strategy:run-1",
            {"mode": "direct", "reason_code": "simple"},
            "run:run-1",
        ),
        _event(
            3,
            "interaction.pending",
            "interaction:a1",
            {"action_id": "a1", "prompt": "请选择", "status": "pending"},
            "run:run-1",
        ),
        _event(
            4,
            "interaction.resolved",
            "interaction:a1",
            {"action_id": "a1", "selected_values": ["yes"], "status": "resolved"},
            "run:run-1",
        ),
        _event(
            5,
            "error.created",
            "error:e1",
            {
                "failure": {
                    "code": "MODEL_UNAVAILABLE",
                    "category": "model",
                    "scope": "run",
                    "source": "lead",
                    "message": "模型服务暂时不可用",
                    "retryable": True,
                    "recovery_actions": ["retry"],
                    "debug_id": "debug-1",
                    "reasoning_content": "must-not-leak",
                },
                "messages": [{"content": "must-not-leak"}],
            },
            "run:run-1",
        ),
    ]

    view = ExecutionViewAssembler().assemble(
        run=_run(status="failed", finished_at=NOW + timedelta(seconds=2)),
        events=events,
        next_cursor=5,
        has_more=False,
    )
    by_kind = {node.kind: node for node in view.nodes}

    assert view.run.mode == "direct"
    assert view.run.status == ExecutionNodeStatus.FAILED
    assert by_kind[ExecutionNodeKind.INTERACTION].status == ExecutionNodeStatus.SUCCEEDED
    assert by_kind[ExecutionNodeKind.ERROR].failure.code == "MODEL_UNAVAILABLE"
    assert "must-not-leak" not in view.model_dump_json()


def test_assembler_marks_historical_v1_as_degraded_and_uses_stable_fallback_ids() -> None:
    event = _event(
        7,
        "step.completed",
        "",
        {"step_id": "legacy-step", "description": "旧步骤", "status": "completed"},
        version=1,
    )
    view = ExecutionViewAssembler().assemble(
        run=_run(status="completed"),
        events=[event],
        next_cursor=7,
        has_more=False,
    )

    assert view.trace_complete is False
    assert view.warnings == ["historical_trace_v1"]
    assert view.nodes[0].node_id == "step:legacy-step"
    assert view.nodes[0].status == ExecutionNodeStatus.SUCCEEDED


def test_assembler_detail_mode_controls_model_metrics() -> None:
    event = _event(
        8,
        "model.succeeded",
        "model:m1",
        {
            "model_call_id": "m1",
            "agent_name": "planner",
            "latency_ms": 120,
            "ttft_ms": 15,
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
        },
        "run:run-1",
    )

    summary = ExecutionViewAssembler().assemble(
        run=_run(), events=[event], next_cursor=8, has_more=False, detail="summary"
    )
    detail = ExecutionViewAssembler().assemble(
        run=_run(), events=[event], next_cursor=8, has_more=False, detail="detail"
    )

    assert summary.nodes[0].metrics.total_tokens is None
    assert detail.nodes[0].metrics.total_tokens == 28
    assert detail.nodes[0].phase.value == "plan"
