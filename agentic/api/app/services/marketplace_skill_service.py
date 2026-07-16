"""Operator import and user installation orchestration for Marketplace Skills."""

import io
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.core.entities.skill import Skill, SkillScope, SkillVersion
from app.core.skills.package import PackageBuildResult, SkillPackageService
from app.extensions.skill_package_storage import SkillPackageStorage, StoredSkillPackage
from app.repositories.uow import IUnitOfWork
from app.schemas.exceptions import BadRequestError, ConflictError


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


class MarketplaceSkillService:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], IUnitOfWork],
        package_service: SkillPackageService,
        package_storage: SkillPackageStorage,
    ) -> None:
        self._uow_factory = uow_factory
        self._package_service = package_service
        self._package_storage = package_storage

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
