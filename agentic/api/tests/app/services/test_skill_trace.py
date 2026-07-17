from typing import Any

import pytest

from app.core.entities.event import MessageEvent
from app.core.entities.skill import (
    SelectedSkill,
    SkillManifest,
    SkillRef,
    SkillSelectionMode,
    SkillSource,
)
from app.schemas.exceptions import NotFoundError
from app.schemas.skill import (
    SkillSelectionRequest,
    SkillSelectionResult,
    SkillSelectionSkip,
)
from app.services.skill_runtime_service import SkillRuntimeContext
from app.services.trace_service import TraceService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MemoryTraceRepository:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.run_skills: list[dict[str, Any]] = []
        self.model_calls: dict[str, dict[str, Any]] = {}

    async def create_run(self, data: dict[str, Any]) -> None:
        self.runs[data["id"]] = data

    async def append_event(self, data: dict[str, Any]) -> None:
        self.events.append(data)

    async def save_run_skill(self, data: dict[str, Any]) -> None:
        self.run_skills.append(data)

    async def get_run(self, user_id: str, run_id: str):
        run = self.runs.get(run_id)
        return run if run and run["user_id"] == user_id else None

    async def list_run_skills(self, user_id: str, run_id: str):
        if await self.get_run(user_id, run_id) is None:
            return []
        return [row for row in self.run_skills if row["run_id"] == run_id]

    async def create_model_call(self, data: dict[str, Any]) -> None:
        self.model_calls[data["id"]] = data


class FakeUow:
    def __init__(self, trace: MemoryTraceRepository) -> None:
        self.trace = trace

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


def selected(
    *,
    source: SkillSource,
    name: str,
    mode: SkillSelectionMode,
    skill_id: str | None,
    version_id: str | None,
    confidence: float | None = None,
) -> SelectedSkill:
    return SelectedSkill(
        ref=SkillRef(source=source, skill_id=skill_id, name=name),
        version_id=version_id,
        version=1 if version_id else None,
        manifest=SkillManifest(name=name, description=f"Use {name}."),
        selection_mode=mode,
        confidence=confidence,
        reason="Matched the report request." if confidence else "Selected manually.",
        package_sha256=("a" if mode is SkillSelectionMode.MANUAL else "b") * 64,
    )


async def started_service() -> tuple[TraceService, MemoryTraceRepository, str]:
    repository = MemoryTraceRepository()
    service = TraceService(uow_factory=lambda: FakeUow(repository))
    run_id = await service.start_run(
        user_id="user-1",
        session_id="session-1",
        task_id="task-1",
        input_event=MessageEvent(role="user", message="Write a report"),
    )
    return service, repository, run_id


async def test_skill_outcome_persists_rows_and_trace_events_atomically() -> None:
    service, repository, run_id = await started_service()
    manual = selected(
        source=SkillSource.PERSONAL,
        name="report-writer",
        mode=SkillSelectionMode.MANUAL,
        skill_id="skill-1",
        version_id="version-1",
    )
    automatic = selected(
        source=SkillSource.BUNDLED,
        name="skill-creator",
        mode=SkillSelectionMode.AUTOMATIC,
        skill_id=None,
        version_id=None,
        confidence=0.91,
    )
    result = SkillSelectionResult(
        selected=[manual, automatic],
        skipped=[
            SkillSelectionSkip(
                ref=SkillRef(source=SkillSource.BUNDLED, name="shell-helper"),
                selection_mode=SkillSelectionMode.AUTOMATIC,
                code="missing_tools",
                reason="Required tools are unavailable: shell.",
            )
        ],
    )
    context = SkillRuntimeContext(
        selected=[manual, automatic],
        prompt_block="must never be persisted",
        sandbox_roots={
            "report-writer": f"/home/ubuntu/.agentic/skills/{run_id}/report-writer",
            "skill-creator": f"/home/ubuntu/.agentic/skills/{run_id}/skill-creator",
        },
    )

    await service.record_skill_selection_started(
        SkillSelectionRequest(
            user_id="user-1",
            message="raw selector prompt must not be stored",
            manual_refs=[manual.ref],
        )
    )
    await service.record_skill_selection_completed(result, context)

    assert len(repository.run_skills) == 2
    first, second = repository.run_skills
    assert first["run_id"] == run_id
    assert first["skill_id"] == "skill-1"
    assert first["skill_version_id"] == "version-1"
    assert first["selection_mode"] == "manual"
    assert first["content_sha256"] == "a" * 64
    assert first["sandbox_path"].endswith("/report-writer")
    assert second["skill_id"] is None
    assert second["skill_version_id"] is None
    assert second["source"] == "bundled"
    assert second["confidence"] == 0.91
    assert second["reason"] == "Matched the report request."

    event_types = [event["event_type"] for event in repository.events]
    assert event_types == [
        "run.started",
        "skill.selection.started",
        "skill.selected",
        "skill.materialized",
        "skill.selected",
        "skill.materialized",
        "skill.skipped",
    ]
    serialized = str(repository.events)
    assert "raw selector prompt" not in serialized
    assert "must never be persisted" not in serialized


async def test_run_skill_query_is_user_authorized_and_included_in_detail() -> None:
    service, repository, run_id = await started_service()
    repository.run_skills.append(
        {
            "id": "run-skill-1",
            "run_id": run_id,
            "name": "report-writer",
            "source": "personal",
        }
    )

    assert (await service.list_run_skills("user-1", run_id))[0]["id"] == "run-skill-1"
    with pytest.raises(NotFoundError):
        await service.list_run_skills("user-2", run_id)


async def test_skill_failure_and_model_preview_do_not_store_sensitive_content() -> None:
    service, repository, _ = await started_service()

    await service.record_skill_selection_failed(
        RuntimeError(
            "secret_key=storage-secret raw selector prompt and full SKILL.md body"
        )
    )
    await service.record_model_call_started(
        agent_name="planner",
        llm=object(),
        messages=[
            {"role": "system", "content": "base"},
            {
                "role": "system",
                "content": "<skill_runtime_context>private full SKILL.md</skill_runtime_context>",
            },
        ],
        tools=[],
        response_format=None,
        tool_choice=None,
    )

    failure = next(
        event
        for event in repository.events
        if event["event_type"] == "skill.selection.failed"
    )
    assert failure["payload"] == {
        "error_type": "RuntimeError",
        "message": "Skill selection or materialization failed.",
    }
    model_call = next(iter(repository.model_calls.values()))
    assert "private full SKILL.md" not in str(model_call["request_preview"])
    assert "skill runtime context omitted" in str(model_call["request_preview"])
