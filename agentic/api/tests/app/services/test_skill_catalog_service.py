import pytest

from app.core.entities.skill import (
    Skill,
    SkillInstallation,
    SkillManifest,
    SkillRef,
    SkillScope,
    SkillSource,
    SkillVersion,
)
from app.schemas.skill import SkillCatalogItem
from app.services.skill_catalog_service import SkillCatalogService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def version_for(skill: Skill, number: int = 1) -> SkillVersion:
    return SkillVersion(
        id=f"version-{skill.id}-{number}",
        skill_id=skill.id,
        version=number,
        manifest={"name": skill.name, "description": skill.description},
        storage_provider="local",
        storage_key=f"skills/{skill.id}/{number}.skill",
        package_sha256=(f"{number:x}" * 64)[:64],
        package_size=100,
        file_count=1,
    )


def bundled_item(name: str, *, auto_invoke: bool = True) -> SkillCatalogItem:
    return SkillCatalogItem(
        ref=SkillRef(source=SkillSource.BUNDLED, name=name),
        display_name=name.replace("-", " ").title(),
        manifest=SkillManifest(name=name, description=f"Use {name}."),
        package_sha256="a" * 64,
        auto_invoke=auto_invoke,
    )


class StaticBundledProvider:
    def __init__(self, items: list[SkillCatalogItem]) -> None:
        self.items = items

    async def list_skills(self) -> list[SkillCatalogItem]:
        return self.items


class CatalogRepository:
    def __init__(self) -> None:
        self.personal: list[Skill] = []
        self.marketplace: list[Skill] = []
        self.versions: dict[str, SkillVersion] = {}
        self.installations: list[SkillInstallation] = []

    async def list_personal(self, user_id: str) -> list[Skill]:
        return [skill for skill in self.personal if skill.owner_user_id == user_id]

    async def get_personal_version(
        self, user_id: str, version_id: str
    ) -> SkillVersion | None:
        return self.versions.get(version_id)

    async def list_marketplace(self) -> list[Skill]:
        return self.marketplace

    async def list_installed_marketplace(
        self, user_id: str
    ) -> list[SkillInstallation]:
        return [item for item in self.installations if item.user_id == user_id]

    async def get_installed_marketplace_version(
        self, user_id: str, version_id: str
    ) -> SkillVersion | None:
        installation = next(
            (
                item
                for item in self.installations
                if item.user_id == user_id
                and item.pinned_version_id == version_id
                and item.enabled
            ),
            None,
        )
        return self.versions.get(version_id) if installation else None


class CatalogUow:
    def __init__(self, repository: CatalogRepository) -> None:
        self.skill = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


async def test_catalog_merges_only_enabled_visible_skills_and_deduplicates() -> None:
    repository = CatalogRepository()
    personal = Skill(
        id="personal-1",
        owner_user_id="user-1",
        name="report-writer",
        display_name="Report Writer",
        description="Create reports.",
        scope=SkillScope.PERSONAL,
        current_version_id="version-personal-1-1",
    )
    disabled = personal.model_copy(
        update={"id": "personal-disabled", "name": "disabled-skill", "enabled": False}
    )
    market = Skill(
        id="market-1",
        name="market-research",
        display_name="Market Research",
        description="Research markets.",
        scope=SkillScope.MARKETPLACE,
        current_version_id="version-market-1-1",
    )
    uninstalled = market.model_copy(
        update={"id": "market-2", "name": "not-installed"}
    )
    personal_version = version_for(personal)
    market_version = version_for(market)
    repository.personal = [personal, disabled]
    repository.marketplace = [market, uninstalled]
    repository.versions = {
        personal_version.id: personal_version,
        market_version.id: market_version,
    }
    repository.installations = [
        SkillInstallation(
            user_id="user-1",
            skill_id=market.id,
            pinned_version_id=market_version.id,
        )
    ]
    bundled = bundled_item("skill-creator")
    service = SkillCatalogService(
        uow_factory=lambda: CatalogUow(repository),
        bundled_provider=StaticBundledProvider([bundled, bundled]),
    )

    catalog = await service.get_catalog("user-1")

    assert [item.selector_key for item in catalog.items] == [
        "bundled:skill-creator",
        "personal:personal-1",
        "marketplace:market-1",
    ]
    assert [item.selector_key for item in catalog.automatic_candidates] == [
        "bundled:skill-creator",
        "personal:personal-1",
        "marketplace:market-1",
    ]


async def test_catalog_limits_automatic_candidates_to_one_hundred() -> None:
    provider = StaticBundledProvider(
        [bundled_item(f"skill-{index}") for index in range(105)]
    )
    service = SkillCatalogService(
        uow_factory=lambda: CatalogUow(CatalogRepository()),
        bundled_provider=provider,
    )

    catalog = await service.get_catalog("user-1")

    assert len(catalog.items) == 105
    assert len(catalog.automatic_candidates) == 100
