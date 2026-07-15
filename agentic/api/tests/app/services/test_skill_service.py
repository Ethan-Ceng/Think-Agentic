import asyncio
import copy
import io
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.entities.skill import Skill, SkillScope, SkillVersion
from app.core.entities.storage_config import StorageConfig
from app.core.skills.package import SkillPackageError, SkillPackageService
from app.extensions.skill_package_storage import SkillPackageStorage
from app.models import UserModel
from app.repositories.db_uow import DBUnitOfWork
from app.schemas.exceptions import ConflictError, NotFoundError, ValidationError
from app.services.skill_service import SkillService
from app.services.skill_workspace_service import SkillWorkspaceService


FIXTURE_ROOT = (
    Path(__file__).parents[2] / "fixtures" / "skills" / "report-writer"
)


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


class MemorySkillRepository:
    def __init__(self) -> None:
        self.skills: dict[str, Skill] = {}
        self.versions: dict[str, SkillVersion] = {}

    async def save_skill(self, skill: Skill) -> None:
        if skill.id in self.skills:
            raise ValueError("Skill already exists")
        self.skills[skill.id] = skill.model_copy(deep=True)

    async def get_personal_by_id(
        self, user_id: str, skill_id: str
    ) -> Skill | None:
        skill = self.skills.get(skill_id)
        if (
            not skill
            or skill.owner_user_id != user_id
            or skill.scope != SkillScope.PERSONAL
            or skill.status == "archived"
        ):
            return None
        return skill.model_copy(deep=True)

    async def list_personal(self, user_id: str) -> list[Skill]:
        return [
            skill.model_copy(deep=True)
            for skill in self.skills.values()
            if skill.owner_user_id == user_id
            and skill.scope == SkillScope.PERSONAL
            and skill.status != "archived"
        ]

    async def update_personal(
        self,
        user_id: str,
        skill_id: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        auto_invoke: bool | None = None,
        current_version_id: str | None = None,
    ) -> bool:
        skill = await self.get_personal_by_id(user_id, skill_id)
        if not skill:
            return False
        updates = {
            key: value
            for key, value in {
                "display_name": display_name,
                "description": description,
                "enabled": enabled,
                "auto_invoke": auto_invoke,
                "current_version_id": current_version_id,
            }.items()
            if value is not None
        }
        self.skills[skill_id] = skill.model_copy(update=updates)
        return bool(updates)

    async def archive_personal(self, user_id: str, skill_id: str) -> bool:
        skill = await self.get_personal_by_id(user_id, skill_id)
        if not skill:
            return False
        self.skills[skill_id] = skill.model_copy(
            update={"status": "archived", "enabled": False, "auto_invoke": False}
        )
        return True

    async def save_version(self, version: SkillVersion) -> None:
        if version.id not in self.versions:
            self.versions[version.id] = version.model_copy(deep=True)

    async def get_personal_version(
        self, user_id: str, version_id: str
    ) -> SkillVersion | None:
        version = self.versions.get(version_id)
        if not version:
            return None
        skill = self.skills.get(version.skill_id)
        if not skill or skill.owner_user_id != user_id:
            return None
        return version.model_copy(deep=True)


class MemoryUow:
    def __init__(
        self, repository: MemorySkillRepository, *, fail_commit: bool = False
    ) -> None:
        self.skill = repository
        self._fail_commit = fail_commit
        self._snapshot: tuple[dict, dict] | None = None

    async def __aenter__(self):
        self._snapshot = (
            copy.deepcopy(self.skill.skills),
            copy.deepcopy(self.skill.versions),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.rollback()
            return None
        try:
            await self.commit()
        except Exception:
            await self.rollback()
            raise
        return None

    async def commit(self) -> None:
        if self._fail_commit:
            raise RuntimeError("database commit failed")

    async def rollback(self) -> None:
        if self._snapshot:
            self.skill.skills, self.skill.versions = copy.deepcopy(self._snapshot)


class UowFactory:
    def __init__(self, repository: MemorySkillRepository) -> None:
        self.repository = repository
        self.fail_commit = False

    def __call__(self) -> MemoryUow:
        return MemoryUow(self.repository, fail_commit=self.fail_commit)


def make_service(
    tmp_path: Path, *, storage_archive_max_bytes: int = 50 * 1024 * 1024
) -> tuple[SkillService, UowFactory]:
    settings = Settings(
        _env_file=None,
        skill_package_storage_path=str(tmp_path / "packages"),
        skill_workspace_storage_path=str(tmp_path / "workspaces"),
        marketplace_skill_storage_provider="local",
        skill_package_archive_max_bytes=storage_archive_max_bytes,
    )
    package_service = SkillPackageService()
    workspace_service = SkillWorkspaceService(
        root=settings.skill_workspace_storage_path,
        package_service=package_service,
    )
    repository = MemorySkillRepository()
    uow_factory = UowFactory(repository)
    service = SkillService(
        uow_factory=uow_factory,
        package_service=package_service,
        package_storage=SkillPackageStorage(
            StaticStorageConfigService(), settings=settings
        ),
        workspace_service=workspace_service,
    )
    return service, uow_factory


def test_first_and_second_publish_create_immutable_versions(tmp_path: Path) -> None:
    service, uow_factory = make_service(tmp_path)

    async def run() -> None:
        first_draft = await service.create_draft(
            "user-1",
            name="report-writer",
            display_name="Report Writer",
            description="Create evidence-based reports.",
        )
        first = await service.publish_draft(
            "user-1",
            first_draft.draft_id,
            expected_revision=first_draft.revision,
            changelog="Initial version",
        )
        assert first.version.version == 1
        assert first.skill.current_version_id == first.version.id
        assert first.version.package_sha256
        with pytest.raises(NotFoundError):
            await service.read_draft_file(
                "user-1", first_draft.draft_id, "SKILL.md"
            )

        second_draft = await service.create_draft(
            "user-1",
            name="report-writer",
            display_name="Report Writer",
            description="Create evidence-based reports.",
        )
        await service.write_draft_file(
            "user-1",
            second_draft.draft_id,
            "references/style.md",
            "# Style\n\nUse concise evidence.\n",
        )
        second_validation = await service.validate_draft(
            "user-1", second_draft.draft_id
        )
        second = await service.publish_draft(
            "user-1",
            second_draft.draft_id,
            expected_revision=second_validation.revision,
            changelog="Add style guide",
        )

        assert second.skill.id == first.skill.id
        assert second.version.id != first.version.id
        assert second.version.version == 2
        assert second.version.changelog == "Add style guide"
        assert len(uow_factory.repository.versions) == 2
        assert sorted(
            path.name for path in (tmp_path / "packages").rglob("*.skill")
        ) == ["1.skill", "2.skill"]

    asyncio.run(run())


def test_import_validates_and_publishes_standard_package(tmp_path: Path) -> None:
    service, uow_factory = make_service(tmp_path)
    archive = io.BytesIO()
    SkillPackageService().build_archive(FIXTURE_ROOT, archive)

    async def run() -> None:
        published = await service.import_archive(
            "user-1",
            archive,
            display_name="Imported Report Writer",
            changelog="Imported",
        )
        assert published.skill.display_name == "Imported Report Writer"
        assert published.version.version == 1
        assert len(uow_factory.repository.skills) == 1

    asyncio.run(run())


def test_invalid_import_returns_diagnostics_without_storage_or_database_rows(
    tmp_path: Path,
) -> None:
    service, uow_factory = make_service(tmp_path)

    async def run() -> None:
        with pytest.raises(ValidationError) as error:
            await service.import_archive("user-1", io.BytesIO(b"not a zip"))
        assert error.value.data["diagnostics"][0]["code"] == "skill_unsafe_archive"
        assert not uow_factory.repository.skills
        assert not list((tmp_path / "packages").rglob("*.skill"))

    asyncio.run(run())


def test_publish_rejects_stale_revision_and_preserves_draft(tmp_path: Path) -> None:
    service, uow_factory = make_service(tmp_path)

    async def run() -> None:
        draft = await service.create_draft(
            "user-1",
            name="report-writer",
            display_name="Report Writer",
            description="Create reports.",
        )
        await service.write_draft_file(
            "user-1", draft.draft_id, "references/new.md", "changed"
        )
        with pytest.raises(ConflictError):
            await service.publish_draft(
                "user-1", draft.draft_id, expected_revision=draft.revision
            )
        assert not uow_factory.repository.skills
        assert await service.read_draft_file(
            "user-1", draft.draft_id, "references/new.md"
        ) == "changed"

    asyncio.run(run())


def test_database_failure_removes_uploaded_object_and_keeps_draft(
    tmp_path: Path,
) -> None:
    service, uow_factory = make_service(tmp_path)

    async def run() -> None:
        draft = await service.create_draft(
            "user-1",
            name="report-writer",
            display_name="Report Writer",
            description="Create reports.",
        )
        uow_factory.fail_commit = True
        with pytest.raises(RuntimeError, match="database commit failed"):
            await service.publish_draft(
                "user-1", draft.draft_id, expected_revision=draft.revision
            )
        assert not uow_factory.repository.skills
        assert not uow_factory.repository.versions
        assert not list((tmp_path / "packages").rglob("*.skill"))
        assert await service.read_draft_file(
            "user-1", draft.draft_id, "SKILL.md"
        )

    asyncio.run(run())


def test_object_store_failure_creates_no_database_rows_and_keeps_draft(
    tmp_path: Path,
) -> None:
    service, uow_factory = make_service(
        tmp_path, storage_archive_max_bytes=1
    )

    async def run() -> None:
        draft = await service.create_draft(
            "user-1",
            name="report-writer",
            display_name="Report Writer",
            description="Create reports.",
        )
        with pytest.raises(SkillPackageError) as error:
            await service.publish_draft(
                "user-1", draft.draft_id, expected_revision=draft.revision
            )
        assert error.value.code == "skill_package_too_large"
        assert not uow_factory.repository.skills
        assert not uow_factory.repository.versions
        assert await service.read_draft_file(
            "user-1", draft.draft_id, "SKILL.md"
        )

    asyncio.run(run())


def test_personal_management_is_user_scoped(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)

    async def run() -> None:
        draft = await service.create_draft(
            "user-1",
            name="report-writer",
            display_name="Report Writer",
            description="Create reports.",
        )
        published = await service.publish_draft(
            "user-1", draft.draft_id, expected_revision=draft.revision
        )
        skill_id = published.skill.id

        await service.update_skill(
            "user-1", skill_id, display_name="Research Writer"
        )
        await service.set_enabled("user-1", skill_id, False)
        await service.set_auto_invoke("user-1", skill_id, False)
        updated = await service.get_skill("user-1", skill_id)
        assert updated.skill.display_name == "Research Writer"
        assert not updated.skill.enabled
        assert not updated.skill.auto_invoke
        assert [item.id for item in await service.list_skills("user-1")] == [
            skill_id
        ]

        with pytest.raises(NotFoundError):
            await service.get_skill("user-2", skill_id)
        with pytest.raises(NotFoundError):
            await service.set_enabled("user-2", skill_id, True)

        await service.archive_skill("user-1", skill_id)
        assert await service.list_skills("user-1") == []
        with pytest.raises(NotFoundError):
            await service.get_skill("user-1", skill_id)

    asyncio.run(run())


@pytest.mark.anyio
async def test_publish_commits_version_and_current_pointer_in_real_database(
) -> None:
    storage_root = Path(tempfile.gettempdir()) / f"agentic-skill-{uuid.uuid4().hex[:8]}"
    settings = Settings(
        _env_file=None,
        skill_package_storage_path=str(storage_root / "packages"),
        skill_workspace_storage_path=str(storage_root / "workspaces"),
        marketplace_skill_storage_provider="local",
    )
    engine = create_async_engine(settings.sqlalchemy_database_uri)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(
            UserModel(
                id=user_id,
                email=f"skill-service-{user_id}@example.com",
                name="Skill Service Test",
            )
        )
        await session.commit()

    package_service = SkillPackageService()
    service = SkillService(
        uow_factory=lambda: DBUnitOfWork(session_factory),
        package_service=package_service,
        package_storage=SkillPackageStorage(
            StaticStorageConfigService(), settings=settings
        ),
        workspace_service=SkillWorkspaceService(
            root=settings.skill_workspace_storage_path,
            package_service=package_service,
        ),
    )

    try:
        draft = await service.create_draft(
            user_id,
            name="report-writer",
            display_name="Report Writer",
            description="Create reports.",
        )
        published = await service.publish_draft(
            user_id, draft.draft_id, expected_revision=draft.revision
        )

        detail = await service.get_skill(user_id, published.skill.id)
        assert detail.skill.current_version_id == published.version.id
        assert detail.version == published.version
    finally:
        async with session_factory() as session:
            await session.execute(delete(UserModel).where(UserModel.id == user_id))
            await session.commit()
        await engine.dispose()
        shutil.rmtree(storage_root, ignore_errors=True)
