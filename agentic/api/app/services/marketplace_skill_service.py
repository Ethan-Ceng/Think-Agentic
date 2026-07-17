"""Operator import and user installation orchestration for Marketplace Skills."""

import io
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Callable, Protocol

from app.core.entities.skill import Skill, SkillInstallation, SkillScope, SkillVersion
from app.core.skills.package import PackageBuildResult, SkillPackageService
from app.extensions.skill_package_storage import SkillPackageStorage, StoredSkillPackage
from app.repositories.uow import IUnitOfWork
from app.schemas.exceptions import BadRequestError, ConflictError, NotFoundError


class PersonalSkillForker(Protocol):
    async def fork_marketplace_archive(
        self,
        user_id: str,
        archive: BinaryIO,
        *,
        source_skill: Skill,
        source_version: SkillVersion,
        display_name: str | None,
    ) -> Any: ...


@dataclass(frozen=True)
class MarketplaceImportResult:
    skill: Skill
    version: SkillVersion
    idempotent: bool = False

    def structured_output(self) -> dict:
        return {
            "skill_id": self.skill.id,
            "version_id": self.version.id,
            "version": self.version.version,
            "hash": self.version.package_sha256,
            "storage_provider": self.version.storage_provider,
            "idempotent": self.idempotent,
        }


@dataclass(frozen=True)
class MarketplaceSkillView:
    skill: Skill
    versions: tuple[SkillVersion, ...]
    latest_version: SkillVersion
    installation: SkillInstallation | None

    @property
    def update_available(self) -> bool:
        return bool(
            self.installation
            and self.installation.pinned_version_id != self.latest_version.id
        )


class MarketplaceSkillService:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], IUnitOfWork],
        package_service: SkillPackageService,
        package_storage: SkillPackageStorage,
        personal_skill_service: PersonalSkillForker | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._package_service = package_service
        self._package_storage = package_storage
        self._personal_skill_service = personal_skill_service

    async def list_marketplace(self, user_id: str) -> list[MarketplaceSkillView]:
        uow = self._uow_factory()
        async with uow:
            installations = {
                item.skill_id: item
                for item in await uow.skill.list_installed_marketplace(user_id)
            }
            result: list[MarketplaceSkillView] = []
            for skill in await uow.skill.list_marketplace():
                versions = await uow.skill.list_marketplace_versions(skill.id)
                result.append(
                    self._view(skill, versions, installations.get(skill.id))
                )
        return result

    async def get_marketplace(
        self, user_id: str, skill_id: str
    ) -> MarketplaceSkillView:
        uow = self._uow_factory()
        async with uow:
            skill = await uow.skill.get_marketplace_by_id(skill_id)
            if skill is None:
                raise NotFoundError("Marketplace Skill does not exist")
            versions = await uow.skill.list_marketplace_versions(skill_id)
            installation = await uow.skill.get_installation(user_id, skill_id)
        return self._view(skill, versions, installation)

    async def install(
        self,
        user_id: str,
        skill_id: str,
        *,
        version_id: str | None = None,
    ) -> MarketplaceSkillView:
        uow = self._uow_factory()
        async with uow:
            skill, versions, selected = await self._resolve_version(
                uow, skill_id, version_id
            )
            if await uow.skill.get_installation(user_id, skill_id):
                raise ConflictError(
                    "Marketplace Skill is already installed; use explicit update"
                )
            installation = SkillInstallation(
                user_id=user_id,
                skill_id=skill_id,
                pinned_version_id=selected.id,
                auto_update=False,
            )
            await uow.skill.save_installation(installation)
        return self._view(skill, versions, installation)

    async def update(
        self,
        user_id: str,
        skill_id: str,
        *,
        version_id: str | None = None,
    ) -> MarketplaceSkillView:
        uow = self._uow_factory()
        async with uow:
            skill, versions, selected = await self._resolve_version(
                uow, skill_id, version_id
            )
            installation = await uow.skill.get_installation(user_id, skill_id)
            if installation is None:
                raise NotFoundError("Marketplace Skill is not installed")
            installation = installation.model_copy(
                update={
                    "pinned_version_id": selected.id,
                    "auto_update": False,
                    "updated_at": datetime.now(),
                }
            )
            await uow.skill.save_installation(installation)
        return self._view(skill, versions, installation)

    async def uninstall(self, user_id: str, skill_id: str) -> None:
        uow = self._uow_factory()
        async with uow:
            if not await uow.skill.delete_installation(user_id, skill_id):
                raise NotFoundError("Marketplace Skill is not installed")

    async def set_enabled(
        self, user_id: str, skill_id: str, enabled: bool
    ) -> MarketplaceSkillView:
        return await self._set_installation_flag(
            user_id, skill_id, enabled=enabled
        )

    async def set_auto_invoke(
        self, user_id: str, skill_id: str, enabled: bool
    ) -> MarketplaceSkillView:
        return await self._set_installation_flag(
            user_id, skill_id, auto_invoke=enabled
        )

    async def fork(
        self,
        user_id: str,
        skill_id: str,
        *,
        version_id: str | None = None,
        display_name: str | None = None,
    ) -> Any:
        if self._personal_skill_service is None:
            raise RuntimeError("Personal Skill service is required for Marketplace forks")
        uow = self._uow_factory()
        async with uow:
            skill, _, version = await self._resolve_version(uow, skill_id, version_id)
        archive = await self._package_storage.download_marketplace(
            storage_provider=version.storage_provider,
            storage_key=version.storage_key,
            storage_config=version.storage_config,
            expected_sha256=version.package_sha256,
        )
        return await self._personal_skill_service.fork_marketplace_archive(
            user_id,
            archive,
            source_skill=skill,
            source_version=version,
            display_name=display_name,
        )

    async def _set_installation_flag(
        self,
        user_id: str,
        skill_id: str,
        *,
        enabled: bool | None = None,
        auto_invoke: bool | None = None,
    ) -> MarketplaceSkillView:
        uow = self._uow_factory()
        async with uow:
            skill = await uow.skill.get_marketplace_by_id(skill_id)
            installation = await uow.skill.get_installation(user_id, skill_id)
            if skill is None or installation is None:
                raise NotFoundError("Marketplace Skill is not installed")
            versions = await uow.skill.list_marketplace_versions(skill_id)
            changes: dict[str, Any] = {"updated_at": datetime.now()}
            if enabled is not None:
                changes["enabled"] = enabled
            if auto_invoke is not None:
                changes["auto_invoke"] = auto_invoke
            installation = installation.model_copy(update=changes)
            await uow.skill.save_installation(installation)
        return self._view(skill, versions, installation)

    async def _resolve_version(
        self, uow: IUnitOfWork, skill_id: str, version_id: str | None
    ) -> tuple[Skill, list[SkillVersion], SkillVersion]:
        skill = await uow.skill.get_marketplace_by_id(skill_id)
        if skill is None:
            raise NotFoundError("Marketplace Skill does not exist")
        versions = sorted(
            await uow.skill.list_marketplace_versions(skill_id),
            key=lambda item: item.version,
        )
        selected_id = version_id or skill.current_version_id
        selected = next((item for item in versions if item.id == selected_id), None)
        if selected is None:
            raise NotFoundError("Marketplace Skill version does not exist")
        return skill, versions, selected

    @staticmethod
    def _view(
        skill: Skill,
        versions: list[SkillVersion],
        installation: SkillInstallation | None,
    ) -> MarketplaceSkillView:
        ordered = tuple(sorted(versions, key=lambda item: item.version))
        latest = next(
            (item for item in ordered if item.id == skill.current_version_id),
            ordered[-1] if ordered else None,
        )
        if latest is None:
            raise ConflictError("Marketplace Skill has no published version")
        return MarketplaceSkillView(
            skill=skill,
            versions=ordered,
            latest_version=latest,
            installation=installation,
        )

    async def import_package(
        self,
        source: str | Path,
        *,
        display_name: str | None = None,
        description: str | None = None,
        changelog: str = "",
        expected_version: int | None = None,
    ) -> MarketplaceImportResult:
        package_bytes, build = self._build_source(Path(source))
        manifest = build.inspected.manifest
        existing, versions = await self._find_marketplace(manifest.name)

        if expected_version is not None and expected_version < 1:
            raise BadRequestError("Marketplace Skill version must be greater than zero")
        by_number = {version.version: version for version in versions}
        if expected_version is not None and expected_version in by_number:
            version = by_number[expected_version]
            if version.package_sha256 != build.archive_sha256:
                raise ConflictError(
                    "Marketplace Skill version already exists with different package bytes"
                )
            if existing is None:
                raise ConflictError("Marketplace Skill version has no owning Skill")
            return MarketplaceImportResult(existing, version, idempotent=True)

        duplicate = next(
            (
                version
                for version in versions
                if version.package_sha256 == build.archive_sha256
            ),
            None,
        )
        if duplicate is not None:
            if existing is None:
                raise ConflictError("Marketplace Skill version has no owning Skill")
            return MarketplaceImportResult(existing, duplicate, idempotent=True)

        next_version = versions[-1].version + 1 if versions else 1
        version_number = expected_version or next_version
        if version_number != next_version:
            raise ConflictError(
                f"Marketplace Skill version must be the next immutable version: {next_version}"
            )

        skill = existing or Skill(
            owner_user_id=None,
            name=manifest.name,
            display_name=(display_name or self._display_name(manifest.name)).strip(),
            description=(description or manifest.description).strip(),
            scope=SkillScope.MARKETPLACE,
        )
        stored = await self._package_storage.upload_marketplace(
            skill_id=skill.id,
            version=version_number,
            body=io.BytesIO(package_bytes),
            expected_sha256=build.archive_sha256,
        )
        version = self._version(
            skill=skill,
            number=version_number,
            build=build,
            stored=stored,
            changelog=changelog,
        )
        resolved_display_name = (
            display_name.strip() if display_name else skill.display_name
        )
        resolved_description = (
            description.strip() if description else manifest.description
        )
        try:
            uow = self._uow_factory()
            async with uow:
                if existing is None:
                    await uow.skill.save_skill(skill)
                await uow.skill.save_version(version)
                updated = await uow.skill.update_marketplace(
                    skill.id,
                    display_name=resolved_display_name,
                    description=resolved_description,
                    current_version_id=version.id,
                )
                if not updated:
                    raise RuntimeError("Unable to update Marketplace Skill pointer")
        except Exception:
            await self._delete_uploaded(stored)
            raise

        published_skill = skill.model_copy(
            update={
                "display_name": resolved_display_name,
                "description": resolved_description,
                "current_version_id": version.id,
            }
        )
        return MarketplaceImportResult(published_skill, version)

    async def _find_marketplace(
        self, name: str
    ) -> tuple[Skill | None, list[SkillVersion]]:
        uow = self._uow_factory()
        async with uow:
            matches = [skill for skill in await uow.skill.list_marketplace() if skill.name == name]
            if len(matches) > 1:
                raise ConflictError(f"Duplicate Marketplace Skill name: {name}")
            skill = matches[0] if matches else None
            versions = (
                await uow.skill.list_marketplace_versions(skill.id) if skill else []
            )
        return skill, sorted(versions, key=lambda version: version.version)

    def _build_source(self, source: Path) -> tuple[bytes, PackageBuildResult]:
        if source.is_dir():
            output = io.BytesIO()
            build = self._package_service.build_archive(source, output)
            return output.getvalue(), build
        if not source.is_file():
            raise BadRequestError(f"Marketplace Skill source does not exist: {source}")
        with source.open("rb") as archive, tempfile.TemporaryDirectory(
            prefix="agentic-market-import-"
        ) as temp:
            destination = Path(temp) / "extracted"
            extracted = self._package_service.extract_archive(archive, destination)
            output = io.BytesIO()
            build = self._package_service.build_archive(
                destination / extracted.inspected.root_name,
                output,
            )
            return output.getvalue(), build

    async def _delete_uploaded(self, stored: StoredSkillPackage) -> None:
        try:
            await self._package_storage.delete_marketplace(
                storage_provider=stored.storage_provider,
                storage_key=stored.storage_key,
                storage_config=stored.storage_config,
            )
        except Exception:
            # The operator run still reports the original database failure. Orphan
            # cleanup procedures use the structured key and hash from storage logs.
            pass

    @staticmethod
    def _version(
        *,
        skill: Skill,
        number: int,
        build: PackageBuildResult,
        stored: StoredSkillPackage,
        changelog: str,
    ) -> SkillVersion:
        return SkillVersion(
            skill_id=skill.id,
            version=number,
            manifest=build.inspected.manifest.model_dump(mode="json", by_alias=True),
            storage_provider=stored.storage_provider,
            storage_key=stored.storage_key,
            storage_config=stored.storage_config,
            package_sha256=stored.package_sha256,
            package_size=stored.package_size,
            file_count=len(build.inspected.files),
            changelog=changelog.strip(),
            created_by_user_id=None,
        )

    @staticmethod
    def _display_name(name: str) -> str:
        return " ".join(part.capitalize() for part in name.split("-"))
