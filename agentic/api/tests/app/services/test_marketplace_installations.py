import io

import pytest

from app.core.entities.skill import (
    RunSkill,
    Skill,
    SkillInstallation,
    SkillScope,
    SkillSelectionMode,
    SkillSource,
    SkillVersion,
)
from app.schemas.exceptions import ConflictError, NotFoundError
from app.services.marketplace_skill_service import MarketplaceSkillService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Repository:
    def __init__(self) -> None:
        self.skill = Skill(
            id="market-1",
            name="market-research",
            display_name="Market Research",
            description="Research a market.",
            scope=SkillScope.MARKETPLACE,
            current_version_id="version-2",
        )
        self.versions = [
            self.version("version-1", 1, "a" * 64),
            self.version("version-2", 2, "b" * 64),
        ]
        self.installations: dict[tuple[str, str], SkillInstallation] = {}
        self.run_skills: list[RunSkill] = []

    def version(self, version_id: str, number: int, digest: str) -> SkillVersion:
        return SkillVersion(
            id=version_id,
            skill_id="market-1",
            version=number,
            manifest={"name": "market-research", "description": "Research a market."},
            storage_provider="local",
            storage_key=f"marketplace/market-1/{number}.skill",
            package_sha256=digest,
            package_size=10,
            file_count=1,
        )

    async def list_marketplace(self):
        return [self.skill]

    async def get_marketplace_by_id(self, skill_id: str):
        return self.skill if skill_id == self.skill.id else None

    async def list_marketplace_versions(self, skill_id: str):
        return list(self.versions) if skill_id == self.skill.id else []

    async def get_marketplace_version(self, version_id: str):
        return next((item for item in self.versions if item.id == version_id), None)

    async def get_installation(self, user_id: str, skill_id: str):
        return self.installations.get((user_id, skill_id))

    async def list_installed_marketplace(self, user_id: str):
        return [
            item for (owner, _), item in self.installations.items() if owner == user_id
        ]

    async def save_installation(self, installation: SkillInstallation):
        self.installations[(installation.user_id, installation.skill_id)] = installation

    async def delete_installation(self, user_id: str, skill_id: str):
        return self.installations.pop((user_id, skill_id), None) is not None


class Uow:
    def __init__(self, repository: Repository) -> None:
        self.skill = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class Storage:
    async def download_marketplace(self, **kwargs):
        assert kwargs["storage_key"].startswith("marketplace/market-1/")
        return io.BytesIO(b"immutable-market-package")


class PersonalSkillService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def fork_marketplace_archive(self, user_id: str, archive, **kwargs):
        self.calls.append(
            {"user_id": user_id, "bytes": archive.read(), **kwargs}
        )
        return {"draft_id": "personal-fork-draft"}


def service(repository: Repository, personal=None) -> MarketplaceSkillService:
    return MarketplaceSkillService(
        uow_factory=lambda: Uow(repository),
        package_service=object(),
        package_storage=Storage(),
        personal_skill_service=personal,
    )


async def test_install_latest_and_explicit_version_are_user_scoped_and_pinned() -> None:
    repository = Repository()
    market = service(repository)

    latest = await market.install("user-a", "market-1")
    explicit = await market.install("user-b", "market-1", version_id="version-1")

    assert latest.installation.pinned_version_id == "version-2"
    assert explicit.installation.pinned_version_id == "version-1"
    assert latest.installation.auto_update is False
    repository.skill = repository.skill.model_copy(
        update={"current_version_id": "version-3"}
    )
    repository.versions.append(repository.version("version-3", 3, "c" * 64))
    listed = await market.list_marketplace("user-a")
    assert listed[0].installation.pinned_version_id == "version-2"
    assert listed[0].update_available is True


async def test_install_is_explicit_update_preserves_historical_run_and_flags() -> None:
    repository = Repository()
    market = service(repository)
    installed = await market.install("user-a", "market-1", version_id="version-1")
    with pytest.raises(ConflictError):
        await market.install("user-a", "market-1")

    historical = RunSkill(
        run_id="run-before-update",
        skill_id="market-1",
        skill_version_id=installed.installation.pinned_version_id,
        name="market-research",
        source=SkillSource.MARKETPLACE,
        selection_mode=SkillSelectionMode.MANUAL,
        content_sha256="a" * 64,
        reason="explicitly selected",
    )
    repository.run_skills.append(historical)
    await market.set_enabled("user-a", "market-1", False)
    await market.set_auto_invoke("user-a", "market-1", False)
    updated = await market.update("user-a", "market-1")

    assert updated.installation.pinned_version_id == "version-2"
    assert updated.installation.enabled is False
    assert updated.installation.auto_invoke is False
    assert updated.installation.auto_update is False
    assert repository.run_skills[0].skill_version_id == "version-1"


async def test_uninstall_and_cross_user_mutations_are_isolated() -> None:
    repository = Repository()
    market = service(repository)
    await market.install("user-a", "market-1")

    with pytest.raises(NotFoundError):
        await market.update("user-b", "market-1")
    with pytest.raises(NotFoundError):
        await market.uninstall("user-b", "market-1")
    await market.uninstall("user-a", "market-1")
    assert await market.list_marketplace("user-a")
    assert ("user-a", "market-1") not in repository.installations


async def test_fork_uses_immutable_market_bytes_and_records_lineage() -> None:
    repository = Repository()
    personal = PersonalSkillService()
    market = service(repository, personal)

    forked = await market.fork("user-a", "market-1", version_id="version-1")

    assert forked == {"draft_id": "personal-fork-draft"}
    assert personal.calls == [
        {
            "user_id": "user-a",
            "bytes": b"immutable-market-package",
            "source_skill": repository.skill,
            "source_version": repository.versions[0],
            "display_name": None,
        }
    ]
    assert repository.versions[0].package_sha256 == "a" * 64
