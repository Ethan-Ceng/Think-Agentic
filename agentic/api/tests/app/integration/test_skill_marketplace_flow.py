import shutil
from pathlib import Path

import pytest

from app.core.entities.skill import SkillInstallation, SkillRef, SkillScope
from app.services.marketplace_skill_service import MarketplaceSkillService
from app.services.skill_catalog_service import SkillCatalogService
from app.services.skill_service import SkillService
from app.services.skill_workspace_service import SkillWorkspaceService
from tests.app.integration.test_skill_runtime_flow import (
    FIXTURE_ROOT,
    Harness,
    MemoryRepository,
    MemoryUow,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MarketplaceRepository(MemoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.installations: dict[tuple[str, str], SkillInstallation] = {}

    async def list_marketplace(self):
        return [
            skill.model_copy(deep=True)
            for skill in self.skills.values()
            if skill.scope is SkillScope.MARKETPLACE and skill.status == "active"
        ]

    async def get_marketplace_by_id(self, skill_id: str):
        skill = self.skills.get(skill_id)
        if not skill or skill.scope is not SkillScope.MARKETPLACE:
            return None
        return skill.model_copy(deep=True)

    async def update_marketplace(self, skill_id: str, **changes):
        skill = await self.get_marketplace_by_id(skill_id)
        if not skill:
            return False
        self.skills[skill_id] = skill.model_copy(
            update={key: value for key, value in changes.items() if value is not None}
        )
        return True

    async def list_marketplace_versions(self, skill_id: str):
        return sorted(
            [
                version.model_copy(deep=True)
                for version in self.versions.values()
                if version.skill_id == skill_id
            ],
            key=lambda version: version.version,
        )

    async def get_marketplace_version(self, version_id: str):
        version = self.versions.get(version_id)
        skill = self.skills.get(version.skill_id) if version else None
        if not version or not skill or skill.scope is not SkillScope.MARKETPLACE:
            return None
        return version.model_copy(deep=True)

    async def save_installation(self, installation: SkillInstallation):
        self.installations[(installation.user_id, installation.skill_id)] = (
            installation.model_copy(deep=True)
        )

    async def get_installation(self, user_id: str, skill_id: str):
        installation = self.installations.get((user_id, skill_id))
        return installation.model_copy(deep=True) if installation else None

    async def list_installed_marketplace(self, user_id: str):
        return [
            installation.model_copy(deep=True)
            for (owner, _), installation in self.installations.items()
            if owner == user_id
        ]

    async def get_installed_marketplace_version(self, user_id: str, version_id: str):
        version = self.versions.get(version_id)
        if not version:
            return None
        installation = self.installations.get((user_id, version.skill_id))
        if (
            not installation
            or not installation.enabled
            or installation.pinned_version_id != version_id
        ):
            return None
        return version.model_copy(deep=True)

    async def delete_installation(self, user_id: str, skill_id: str):
        return self.installations.pop((user_id, skill_id), None) is not None


class MarketplaceHarness(Harness):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self.repository = MarketplaceRepository()
        self.restart_services()

    def restart_services(self) -> None:
        self.uow_factory = lambda: MemoryUow(self.repository)
        workspace = SkillWorkspaceService(
            root=self.settings.skill_workspace_storage_path,
            package_service=self.package_service,
        )
        self.skill_service = SkillService(
            uow_factory=self.uow_factory,
            package_service=self.package_service,
            package_storage=self.storage,
            workspace_service=workspace,
        )
        self.marketplace = MarketplaceSkillService(
            uow_factory=self.uow_factory,
            package_service=self.package_service,
            package_storage=self.storage,
            personal_skill_service=self.skill_service,
        )
        self.catalog = SkillCatalogService(uow_factory=self.uow_factory)


async def test_market_import_install_invoke_update_fork_restart_and_trace(
    tmp_path: Path,
) -> None:
    harness = MarketplaceHarness(tmp_path)
    version_one = await harness.marketplace.import_package(FIXTURE_ROOT)
    market_ref = SkillRef(
        source="marketplace",
        skill_id=version_one.skill.id,
        name=version_one.skill.name,
    )

    installed = await harness.marketplace.install(
        "user-a", version_one.skill.id, version_id=version_one.version.id
    )
    assert installed.installation
    assert installed.installation.auto_update is False
    assert (await harness.catalog.get_catalog("user-b")).items == ()
    denied, _ = await harness.prepare(
        user_id="user-b",
        session_id="session-b",
        run_id="run-b-denied",
        refs=[market_ref],
    )
    assert denied.prompt_block == ""

    selected, trace = await harness.prepare(
        user_id="user-a",
        session_id="session-a",
        run_id="run-a-v1",
        refs=[market_ref],
    )
    assert version_one.version.package_sha256 in {
        item.package_sha256 for item in selected.selected
    }
    historical_run_id = trace.run_id
    assert historical_run_id

    changed = tmp_path / "market-v2" / "report-writer"
    shutil.copytree(FIXTURE_ROOT, changed)
    skill_md = changed / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\n\nUse the explicit v2 checklist.\n",
        encoding="utf-8",
    )
    version_two = await harness.marketplace.import_package(changed)
    before_update = await harness.marketplace.get_marketplace(
        "user-a", version_one.skill.id
    )
    assert before_update.installation
    assert before_update.installation.pinned_version_id == version_one.version.id
    assert before_update.update_available is True
    old_trace = await trace.list_run_skills("user-a", historical_run_id)
    assert old_trace[0]["skill_version_id"] == version_one.version.id

    updated = await harness.marketplace.update("user-a", version_one.skill.id)
    assert updated.installation
    assert updated.installation.pinned_version_id == version_two.version.id
    fork = await harness.marketplace.fork("user-a", version_one.skill.id)
    validation = await harness.skill_service.validate_draft("user-a", fork.draft_id)
    published = await harness.skill_service.publish_draft(
        "user-a", fork.draft_id, expected_revision=validation.revision
    )
    assert published.skill.forked_from_skill_id == version_one.skill.id
    assert published.skill.forked_from_version_id == version_two.version.id

    # Reconstruct every application service while retaining deployment storage
    # and repository state, which models an API process restart.
    harness.restart_services()
    after_restart = await harness.marketplace.get_marketplace(
        "user-a", version_one.skill.id
    )
    assert after_restart.installation
    assert after_restart.installation.pinned_version_id == version_two.version.id
    reproduced = await trace.list_run_skills("user-a", historical_run_id)
    assert reproduced[0]["skill_version_id"] == version_one.version.id
    assert reproduced[0]["content_sha256"] == version_one.version.package_sha256
