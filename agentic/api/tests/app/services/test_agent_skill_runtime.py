import io
from types import SimpleNamespace

import pytest

from app.core.entities.skill import (
    SelectedSkill,
    SkillManifest,
    SkillRef,
    SkillSelectionMode,
    SkillSource,
    SkillVersion,
)
from app.core.agent.agent_task_runner import AgentTaskRunner
from app.core.entities.event import MessageEvent
from app.core.entities.file import File
from app.core.entities.tool_result import ToolResult
from app.schemas.session import ChatRequest
from app.schemas.skill import SkillSelectionRequest, SkillSelectionResult
from app.services.skill_runtime_service import (
    SkillRuntimeContext,
    SkillRuntimeError,
    SkillRuntimeService,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def selected(
    source: SkillSource = SkillSource.PERSONAL,
    *,
    skill_id: str = "skill-1",
    version_id: str = "version-1",
    name: str = "report-writer",
) -> SelectedSkill:
    return SelectedSkill(
        ref=SkillRef(source=source, skill_id=skill_id, name=name),
        version_id=version_id,
        version=1,
        manifest=SkillManifest(name=name, description="Write reports."),
        selection_mode=SkillSelectionMode.MANUAL,
        reason="Selected manually by the user.",
        package_sha256="a" * 64,
    )


def version(
    *, skill_id: str = "skill-1", version_id: str = "version-1"
) -> SkillVersion:
    return SkillVersion(
        id=version_id,
        skill_id=skill_id,
        version=1,
        manifest={"name": "report-writer", "description": "Write reports."},
        storage_provider="local",
        storage_key=f"personal/user-1/{skill_id}/1.skill",
        package_sha256="a" * 64,
        package_size=7,
        file_count=2,
    )


class StaticSelectionService:
    def __init__(self, skills: list[SelectedSkill]) -> None:
        self.skills = skills
        self.requests: list[SkillSelectionRequest] = []

    async def select(self, request: SkillSelectionRequest) -> SkillSelectionResult:
        self.requests.append(request)
        return SkillSelectionResult(selected=self.skills)


class SkillRepository:
    def __init__(
        self,
        *,
        personal: SkillVersion | None = None,
        marketplace: SkillVersion | None = None,
    ) -> None:
        self.personal = personal
        self.marketplace = marketplace

    async def get_personal_version(self, user_id: str, version_id: str):
        if user_id == "user-1" and self.personal and self.personal.id == version_id:
            return self.personal
        return None

    async def get_installed_marketplace_version(
        self, user_id: str, version_id: str
    ):
        if (
            user_id == "user-1"
            and self.marketplace
            and self.marketplace.id == version_id
        ):
            return self.marketplace
        return None


class FakeUow:
    def __init__(self, skill: SkillRepository) -> None:
        self.skill = skill

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class RecordingPackageStorage:
    def __init__(self) -> None:
        self.personal_downloads: list[dict] = []
        self.marketplace_downloads: list[dict] = []

    async def download_personal(self, **kwargs):
        self.personal_downloads.append(kwargs)
        return io.BytesIO(b"package")

    async def download_marketplace(self, **kwargs):
        self.marketplace_downloads.append(kwargs)
        return io.BytesIO(b"package")


class RecordingSandbox:
    def __init__(self) -> None:
        self.uploads: list[dict] = []
        self.commands: list[dict] = []
        self.reads: list[str] = []

    async def upload_file(self, file_data, filepath: str, filename: str = None):
        self.uploads.append(
            {"filepath": filepath, "filename": filename, "data": file_data.read()}
        )
        return ToolResult(success=True)

    async def exec_command(self, session_id: str, exec_dir: str, command: str):
        self.commands.append(
            {"session_id": session_id, "exec_dir": exec_dir, "command": command}
        )
        return ToolResult(success=True, data={"returncode": 0})

    async def wait_process(self, session_id: str, seconds: int | None = None):
        return ToolResult(success=True, data={"returncode": 0})

    async def read_file(self, filepath: str, **kwargs):
        self.reads.append(filepath)
        return ToolResult(
            success=True,
            data={
                "content": "---\nname: report-writer\ndescription: Write reports.\n---\nFollow the report workflow."
            },
        )

    async def delete_file(self, filepath: str):
        return ToolResult(success=True)


def request(*refs: SkillRef) -> SkillSelectionRequest:
    return SkillSelectionRequest(
        user_id="user-1",
        message="Write a report",
        manual_refs=list(refs),
        available_tool_names={"shell", "file"},
    )


def runtime_service(
    skills: list[SelectedSkill], repository: SkillRepository
) -> tuple[SkillRuntimeService, RecordingPackageStorage, RecordingSandbox]:
    storage = RecordingPackageStorage()
    sandbox = RecordingSandbox()
    service = SkillRuntimeService(
        uow_factory=lambda: FakeUow(repository),
        selection_service=StaticSelectionService(skills),
        package_storage=storage,
        sandbox=sandbox,
    )
    return service, storage, sandbox


async def test_prepare_run_materializes_only_selected_package_and_injects_skill_md() -> None:
    chosen = selected()
    service, storage, sandbox = runtime_service(
        [chosen], SkillRepository(personal=version())
    )

    context = await service.prepare_run(
        "user-1", "session-1", "run-1", request(chosen.ref)
    )

    root = "/home/ubuntu/.agentic/skills/run-1/report-writer"
    assert context.sandbox_roots == {"report-writer": root}
    assert context.selected == [chosen]
    assert root in context.prompt_block
    assert "Follow the report workflow." in context.prompt_block
    assert "references/style.md" not in context.prompt_block
    assert sandbox.reads == [f"{root}/SKILL.md"]
    assert len(storage.personal_downloads) == 1
    assert storage.marketplace_downloads == []
    assert len(sandbox.uploads) == 1
    assert len(sandbox.commands) == 1


async def test_conflicting_selected_names_are_rejected_before_extraction() -> None:
    first = selected(skill_id="skill-1", version_id="version-1")
    second = selected(
        SkillSource.MARKETPLACE,
        skill_id="skill-2",
        version_id="version-2",
    )
    service, storage, sandbox = runtime_service(
        [first, second], SkillRepository(personal=version())
    )

    with pytest.raises(SkillRuntimeError, match="conflicting"):
        await service.prepare_run(
            "user-1", "session-1", "run-1", request(first.ref, second.ref)
        )

    assert storage.personal_downloads == []
    assert storage.marketplace_downloads == []
    assert sandbox.uploads == []
    assert sandbox.commands == []


@pytest.mark.parametrize(
    "chosen,repository",
    [
        (selected(), SkillRepository(personal=None)),
        (
            selected(
                SkillSource.MARKETPLACE,
                skill_id="market-1",
                version_id="market-version-1",
            ),
            SkillRepository(marketplace=None),
        ),
    ],
)
async def test_unowned_or_uninstalled_package_cannot_be_materialized(
    chosen: SelectedSkill, repository: SkillRepository
) -> None:
    service, storage, sandbox = runtime_service([chosen], repository)

    with pytest.raises(SkillRuntimeError, match="not available"):
        await service.prepare_run(
            "user-1", "session-1", "run-1", request(chosen.ref)
        )

    assert storage.personal_downloads == []
    assert storage.marketplace_downloads == []
    assert sandbox.uploads == []


async def test_empty_selection_clears_runtime_context() -> None:
    service, storage, sandbox = runtime_service([], SkillRepository())

    context = await service.prepare_run(
        "user-1", "session-1", "run-2", request()
    )

    assert context == SkillRuntimeContext()
    assert storage.personal_downloads == []
    assert sandbox.uploads == []


class OrderedTrace:
    def __init__(self) -> None:
        self.run_ids: list[str] = []

    async def start_run(self, **kwargs) -> str:
        run_id = f"run-{len(self.run_ids) + 1}"
        self.run_ids.append(run_id)
        return run_id


class OrderedRuntime:
    def __init__(self, trace: OrderedTrace) -> None:
        self.trace = trace
        self.calls: list[dict] = []

    async def prepare_run(self, **kwargs) -> SkillRuntimeContext:
        assert self.trace.run_ids
        self.calls.append(kwargs)
        return SkillRuntimeContext(prompt_block=f"context:{kwargs['run_id']}")


class RecordingFlow:
    def __init__(self) -> None:
        self.contexts: list[SkillRuntimeContext] = []

    def set_skill_runtime_context(self, context: SkillRuntimeContext) -> None:
        self.contexts.append(context)

    def get_available_tool_names(self) -> set[str]:
        return {"shell", "shell_execute"}


async def test_runner_starts_trace_before_preparing_each_run() -> None:
    trace = OrderedTrace()
    runtime = OrderedRuntime(trace)
    flow = RecordingFlow()
    runner = object.__new__(AgentTaskRunner)
    runner._trace_service = trace
    runner._skill_runtime_service = runtime
    runner._flow = flow
    runner._user_id = "user-1"
    runner._session_id = "session-1"
    chosen = selected()
    task = SimpleNamespace(id="task-1")

    first = MessageEvent(
        role="user",
        message="Write a report",
        attachments=[File(filename="brief.pdf", mime_type="application/pdf")],
        skills=[chosen.ref],
    )
    second = MessageEvent(role="user", message="Continue without a manual Skill")
    await runner._prepare_skill_runtime(task, first)
    await runner._prepare_skill_runtime(task, second)

    assert trace.run_ids == ["run-1", "run-2"]
    assert [call["run_id"] for call in runtime.calls] == trace.run_ids
    assert runtime.calls[0]["request"].manual_refs == [chosen.ref]
    assert runtime.calls[0]["request"].attachment_media_types == ["application/pdf"]
    assert runtime.calls[1]["request"].manual_refs == []
    assert flow.contexts[0] == SkillRuntimeContext()
    assert flow.contexts[2] == SkillRuntimeContext()


def test_chat_request_and_message_event_default_skills_for_compatibility() -> None:
    assert ChatRequest(message="hello").skills == []
    assert MessageEvent(role="user", message="hello").skills == []
