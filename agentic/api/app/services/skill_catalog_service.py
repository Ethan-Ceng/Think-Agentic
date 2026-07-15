"""Merge the user-visible Skill catalog without exposing package contents."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from app.core.entities.skill import (
    Skill,
    SkillManifest,
    SkillRef,
    SkillSource,
    SkillStatus,
    SkillVersion,
)
from app.repositories.uow import IUnitOfWork
from app.schemas.skill import SkillCatalogItem


AUTOMATIC_CANDIDATE_LIMIT = 100


class BundledSkillProvider(Protocol):
    async def list_skills(self) -> list[SkillCatalogItem]: ...


class EmptyBundledSkillProvider:
    async def list_skills(self) -> list[SkillCatalogItem]:
        return []


@dataclass(frozen=True)
class SkillCatalog:
    items: tuple[SkillCatalogItem, ...]
    automatic_candidates: tuple[SkillCatalogItem, ...]

    def resolve(self, ref: SkillRef) -> SkillCatalogItem | None:
        return next((item for item in self.items if item.ref == ref), None)


class SkillCatalogService:
    def __init__(
        self,
        *,
        uow_factory,
        bundled_provider: BundledSkillProvider | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._bundled_provider = bundled_provider or EmptyBundledSkillProvider()

    async def get_catalog(self, user_id: str) -> SkillCatalog:
        items: list[SkillCatalogItem] = []
        items.extend(await self._bundled_provider.list_skills())

        uow: IUnitOfWork = self._uow_factory()
        async with uow:
            items.extend(await self._personal_items(uow, user_id))
            items.extend(await self._marketplace_items(uow, user_id))

        deduplicated = self._deduplicate(items)
        automatic = tuple(
            item for item in deduplicated if item.auto_invoke
        )[:AUTOMATIC_CANDIDATE_LIMIT]
        return SkillCatalog(
            items=tuple(deduplicated),
            automatic_candidates=automatic,
        )

    async def _personal_items(
        self, uow: IUnitOfWork, user_id: str
    ) -> list[SkillCatalogItem]:
        result: list[SkillCatalogItem] = []
        for skill in await uow.skill.list_personal(user_id):
            if (
                not skill.enabled
                or skill.status is not SkillStatus.ACTIVE
                or not skill.current_version_id
            ):
                continue
            version = await uow.skill.get_personal_version(
                user_id, skill.current_version_id
            )
            item = self._versioned_item(skill, version, SkillSource.PERSONAL)
            if item:
                result.append(item)
        return result

    async def _marketplace_items(
        self, uow: IUnitOfWork, user_id: str
    ) -> list[SkillCatalogItem]:
        market_by_id = {
            skill.id: skill for skill in await uow.skill.list_marketplace()
        }
        result: list[SkillCatalogItem] = []
        for installation in await uow.skill.list_installed_marketplace(user_id):
            skill = market_by_id.get(installation.skill_id)
            if (
                not installation.enabled
                or not skill
                or not skill.enabled
                or skill.status is not SkillStatus.ACTIVE
            ):
                continue
            version = await uow.skill.get_installed_marketplace_version(
                user_id, installation.pinned_version_id
            )
            item = self._versioned_item(
                skill,
                version,
                SkillSource.MARKETPLACE,
                auto_invoke=installation.auto_invoke,
            )
            if item:
                result.append(item)
        return result

    @staticmethod
    def _versioned_item(
        skill: Skill,
        version: SkillVersion | None,
        source: SkillSource,
        *,
        auto_invoke: bool | None = None,
    ) -> SkillCatalogItem | None:
        if version is None or version.skill_id != skill.id:
            return None
        try:
            manifest = SkillManifest.model_validate(version.manifest)
        except ValidationError:
            return None
        return SkillCatalogItem(
            ref=SkillRef(source=source, skill_id=skill.id, name=skill.name),
            display_name=skill.display_name,
            manifest=manifest,
            version_id=version.id,
            version=version.version,
            package_sha256=version.package_sha256,
            auto_invoke=skill.auto_invoke
            if auto_invoke is None
            else auto_invoke,
        )

    @staticmethod
    def _deduplicate(items: list[SkillCatalogItem]) -> list[SkillCatalogItem]:
        result: list[SkillCatalogItem] = []
        seen: set[str] = set()
        for item in items:
            if item.selector_key in seen:
                continue
            seen.add(item.selector_key)
            result.append(item)
        return result
