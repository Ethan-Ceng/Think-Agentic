import copy
import io
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.core.entities.event import MessageEvent
from app.core.entities.skill import Skill, SkillRef, SkillScope, SkillVersion
from app.core.entities.storage_config import StorageConfig
from app.core.skills.package import SkillPackageService
from app.core.entities.tool_result import ToolResult
from app.extensions.skill_package_storage import SkillPackageStorage
from app.schemas.skill import SkillSelectionRequest
from app.schemas.exceptions import NotFoundError
from app.services.skill_catalog_service import SkillCatalogService
from app.services.skill_runtime_service import SkillRuntimeContext, SkillRuntimeService
from app.services.skill_selection_service import SkillSelectionService
from app.services.skill_service import SkillService
from app.services.skill_workspace_service import SkillWorkspaceService
from app.services.trace_service import TraceService


pytestmark = pytest.mark.anyio
FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "skills" / "report-writer"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class StaticStorageConfigService:
    async def get_storage_config(
        self, user_id: str, *, redact: bool = True
    ) -> StorageConfig:
        assert user_id
        assert redact is False
        return StorageConfig.model_validate(
            {
                "default_provider": "local",
                "providers": {"local": {"enabled": True}},
            }
        )


class MemoryRepository:
    def __init__(self) -> None:
        self.skills: dict[str, Skill] = {}
        self.versions: dict[str, SkillVersion] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.run_skills: list[dict[str, Any]] = []
        self.model_calls: dict[str, dict[str, Any]] = {}

    async def save_skill(self, skill: Skill) -> None:
        self.skills[skill.id] = skill.model_copy(deep=True)

    async def save_version(self, version: SkillVersion) -> None:
        self.versions[version.id] = version.model_copy(deep=True)

    async def get_personal_by_id(self, user_id: str, skill_id: str):
        skill = self.skills.get(skill_id)
        if not skill or skill.owner_user_id != user_id or skill.status == "archived":
            return None
        return skill.model_copy(deep=True)

    async def list_personal(self, user_id: str) -> list[Skill]:
        return [
            skill.model_copy(deep=True)
            for skill in self.skills.values()
            if skill.owner_user_id == user_id
            and skill.scope is SkillScope.PERSONAL
            and skill.status != "archived"
        ]

    async def update_personal(self, user_id: str, skill_id: str, **changes) -> bool:
        skill = await self.get_personal_by_id(user_id, skill_id)
        if not skill:
            return False
        updates = {key: value for key, value in changes.items() if value is not None}
        self.skills[skill_id] = skill.model_copy(update=updates)
        return True

    async def get_personal_version(self, user_id: str, version_id: str):
        version = self.versions.get(version_id)
        skill = self.skills.get(version.skill_id) if version else None
        if not version or not skill or skill.owner_user_id != user_id:
            return None
        return version.model_copy(deep=True)

    async def list_marketplace(self) -> list[Skill]:
        return []

    async def list_installed_marketplace(self, user_id: str) -> list:
        return []

    async def get_installed_marketplace_version(
        self, user_id: str, version_id: str
    ) -> None:
        return None

    async def create_run(self, data: dict[str, Any]) -> None:
        self.runs[data["id"]] = copy.deepcopy(data)

    async def append_event(self, data: dict[str, Any]) -> None:
        self.events.append(copy.deepcopy(data))

    async def save_run_skill(self, data: dict[str, Any]) -> None:
        self.run_skills.append(copy.deepcopy(data))

    async def get_run(self, user_id: str, run_id: str):
        run = self.runs.get(run_id)
        return copy.deepcopy(run) if run and run["user_id"] == user_id else None

    async def list_run_skills(self, user_id: str, run_id: str) -> list[dict]:
        if await self.get_run(user_id, run_id) is None:
            return []
        return [copy.deepcopy(row) for row in self.run_skills if row["run_id"] == run_id]

    async def create_model_call(self, data: dict[str, Any]) -> None:
        self.model_calls[data["id"]] = copy.deepcopy(data)

    async def update_model_call(self, model_call_id: str, data: dict[str, Any]) -> None:
        self.model_calls[model_call_id].update(copy.deepcopy(data))


class MemoryUow:
    def __init__(self, repository: MemoryRepository) -> None:
        self.skill = repository
        self.trace = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class EmptySelectorLlm:
    model_name = "empty-skill-selector"
    temperature = 0
    max_tokens = 128

    async def invoke(self, messages, tools=None, response_format=None, tool_choice=None):
        return {"role": "assistant", "content": '{"skills": []}'}


class ExtractingSandbox:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.uploads: list[dict[str, Any]] = []

    async def upload_file(self, file_data, filepath: str, filename: str = None):
        package = file_data.read()
        self.uploads.append({"filepath": filepath, "data": package})
        self.files[filepath] = package
        run_root = filepath.split("/.packages/", 1)[0]
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            for member in archive.infolist():
                if not member.is_dir():
                    self.files[f"{run_root}/{member.filename}"] = archive.read(member)
        return ToolResult(success=True)

    async def exec_command(self, session_id: str, exec_dir: str, command: str):
        return ToolResult(success=True, data={"returncode": 0})

    async def wait_process(self, session_id: str, seconds: int | None = None):
        return ToolResult(success=True, data={"returncode": 0})

    async def read_file(self, filepath: str, **kwargs):
        content = self.files.get(filepath)
        if content is None:
            return ToolResult(success=False)
        return ToolResult(success=True, data={"content": content.decode("utf-8")})

    async def delete_file(self, filepath: str):
        self.files.pop(filepath, None)
        return ToolResult(success=True)


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.settings = Settings(
            _env_file=None,
            skill_package_storage_path=str(tmp_path / "packages"),
            skill_workspace_storage_path=str(tmp_path / "workspaces"),
            marketplace_skill_storage_provider="local",
        )
        self.repository = MemoryRepository()
        self.uow_factory = lambda: MemoryUow(self.repository)
        self.package_service = SkillPackageService()
        self.storage = SkillPackageStorage(
            StaticStorageConfigService(), settings=self.settings
        )
        self.skill_service = SkillService(
            uow_factory=self.uow_factory,
            package_service=self.package_service,
            package_storage=self.storage,
            workspace_service=SkillWorkspaceService(
                root=self.settings.skill_workspace_storage_path,
                package_service=self.package_service,
            ),
        )
        self.catalog = SkillCatalogService(uow_factory=self.uow_factory)
        self.sandbox = ExtractingSandbox()

    async def import_fixture(self, tmp_path: Path, user_id: str, marker: str):
        root = tmp_path / f"fixture-{marker}" / "report-writer"
        shutil.copytree(FIXTURE_ROOT, root)
        skill_md = root / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8") + f"\n\nOwner marker: {marker}\n",
            encoding="utf-8",
        )
        archive = io.BytesIO()
        self.package_service.build_archive(root, archive)
        archive.seek(0)
        return await self.skill_service.import_archive(user_id, archive)

    async def prepare(
        self,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        refs: list[SkillRef],
    ) -> tuple[SkillRuntimeContext, TraceService]:
        trace = TraceService(uow_factory=self.uow_factory)
        actual_run_id = await trace.start_run(
            user_id=user_id,
            session_id=session_id,
            task_id=f"task-{run_id}",
            input_event=MessageEvent(role="user", message="Write a report", skills=refs),
        )

        async def llm_provider(_: str):
            return EmptySelectorLlm()

        selection = SkillSelectionService(
            catalog_service=self.catalog,
            llm_provider=llm_provider,
            trace_service=trace,
        )
        runtime = SkillRuntimeService(
            uow_factory=self.uow_factory,
            selection_service=selection,
            package_storage=self.storage,
            sandbox=self.sandbox,
            trace_service=trace,
        )
        context = await runtime.prepare_run(
            user_id=user_id,
            session_id=session_id,
            run_id=actual_run_id,
            request=SkillSelectionRequest(
                user_id=user_id,
                message="Write a report",
                manual_refs=refs,
                available_tool_names={"search_web", "read_file", "write_file"},
            ),
        )
        return context, trace


async def test_import_manual_runtime_trace_and_next_run_is_transient(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    published = await harness.import_fixture(tmp_path, "user-1", "user-one")
    ref = SkillRef(
        source="personal", skill_id=published.skill.id, name=published.skill.name
    )

    first, first_trace = await harness.prepare(
        user_id="user-1",
        session_id="session-1",
        run_id="run-1",
        refs=[ref],
    )
    first_run_id = first_trace.run_id
    assert first_run_id
    root = f"/home/ubuntu/.agentic/skills/{first_run_id}/report-writer"
    assert first.sandbox_roots == {"report-writer": root}
    assert "Owner marker: user-one" in first.prompt_block
    assert f"{root}/SKILL.md" in harness.sandbox.files
    traced = await first_trace.list_run_skills("user-1", first_run_id)
    assert traced[0]["skill_id"] == published.skill.id
    assert traced[0]["content_sha256"] == published.version.package_sha256

    second, second_trace = await harness.prepare(
        user_id="user-1",
        session_id="session-1",
        run_id="run-2",
        refs=[],
    )
    second_run_id = second_trace.run_id
    assert second_run_id
    assert second == SkillRuntimeContext()
    assert "Owner marker: user-one" not in second.prompt_block
    assert not any(
        path.startswith(f"/home/ubuntu/.agentic/skills/{second_run_id}/")
        for path in harness.sandbox.files
    )
    assert await second_trace.list_run_skills("user-1", second_run_id) == []


async def test_identically_named_personal_skills_are_isolated_by_user(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    first = await harness.import_fixture(tmp_path, "user-1", "user-one")
    second = await harness.import_fixture(tmp_path, "user-2", "user-two")
    assert first.skill.id != second.skill.id
    assert first.version.package_sha256 != second.version.package_sha256

    catalog_one = await harness.catalog.get_catalog("user-1")
    catalog_two = await harness.catalog.get_catalog("user-2")
    assert [item.ref.skill_id for item in catalog_one.items] == [first.skill.id]
    assert [item.ref.skill_id for item in catalog_two.items] == [second.skill.id]

    context_one, trace_one = await harness.prepare(
        user_id="user-1",
        session_id="session-1",
        run_id="run-user-1",
        refs=[catalog_one.items[0].ref],
    )
    context_two, trace_two = await harness.prepare(
        user_id="user-2",
        session_id="session-2",
        run_id="run-user-2",
        refs=[catalog_two.items[0].ref],
    )
    assert "Owner marker: user-one" in context_one.prompt_block
    assert "Owner marker: user-two" not in context_one.prompt_block
    assert "Owner marker: user-two" in context_two.prompt_block
    assert "Owner marker: user-one" not in context_two.prompt_block
    assert context_one.sandbox_roots["report-writer"] != context_two.sandbox_roots["report-writer"]
    assert context_one.sandbox_roots["report-writer"].endswith("/report-writer")
    assert context_two.sandbox_roots["report-writer"].endswith("/report-writer")
    assert harness.sandbox.uploads[-2]["data"] != harness.sandbox.uploads[-1]["data"]
    assert trace_one.run_id
    assert trace_two.run_id
    assert (await trace_one.list_run_skills("user-1", trace_one.run_id))[0][
        "skill_id"
    ] == first.skill.id
    assert (await trace_two.list_run_skills("user-2", trace_two.run_id))[0][
        "skill_id"
    ] == second.skill.id
    with pytest.raises(NotFoundError):
        await trace_one.list_run_skills("user-2", trace_one.run_id)
