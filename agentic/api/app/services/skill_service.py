"""Application orchestration for personal Skill drafts and immutable versions."""

import io
import json
import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable

from app.core.entities.skill import (
    Skill,
    SkillManifest,
    SkillScope,
    SkillVersion,
)
from app.core.skills.package import (
    PackageBuildResult,
    SkillPackageError,
    SkillPackageService,
)
from app.extensions.skill_package_storage import (
    SkillPackageStorage,
    StoredSkillPackage,
)
from app.repositories.uow import IUnitOfWork
from app.schemas.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.services.skill_workspace_service import (
    SkillWorkspaceEntry,
    SkillWorkspaceService,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillDraft:
    draft_id: str
    skill_name: str
    revision: str


@dataclass(frozen=True)
class SkillValidationDiagnostic:
    file: str
    line: int | None
    column: int | None
    code: str
    message: str


@dataclass(frozen=True)
class SkillValidationResult:
    valid: bool
    revision: str
    manifest: SkillManifest | None
    diagnostics: tuple[SkillValidationDiagnostic, ...]


@dataclass(frozen=True)
class PublishedSkill:
    skill: Skill
    version: SkillVersion


@dataclass(frozen=True)
class SkillDetail:
    skill: Skill
    version: SkillVersion | None


class SkillService:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], IUnitOfWork],
        package_service: SkillPackageService,
        package_storage: SkillPackageStorage,
        workspace_service: SkillWorkspaceService,
    ) -> None:
        self._uow_factory = uow_factory
        self._package_service = package_service
        self._package_storage = package_storage
        self._workspace_service = workspace_service

    async def create_draft(
        self,
        user_id: str,
        *,
        name: str,
        display_name: str,
        description: str,
    ) -> SkillDraft:
        manifest = SkillManifest(name=name, description=description)
        draft_id = str(uuid.uuid4())
        markdown = self._initial_skill_md(manifest, display_name)
        created = await self._workspace_service.create_draft(
            user_id, draft_id, manifest.name, markdown
        )
        staged = await self._workspace_service.stage_publish(user_id, draft_id)
        return SkillDraft(
            draft_id=created.draft_id,
            skill_name=created.skill_name,
            revision=staged.revision,
        )

    async def list_draft_tree(
        self, user_id: str, draft_id: str
    ) -> tuple[SkillWorkspaceEntry, ...]:
        return await self._workspace_service.list_tree(user_id, draft_id)

    async def read_draft_file(
        self, user_id: str, draft_id: str, path: str
    ) -> str:
        return await self._workspace_service.read_text(user_id, draft_id, path)

    async def write_draft_file(
        self, user_id: str, draft_id: str, path: str, content: str
    ) -> None:
        await self._workspace_service.write_text(
            user_id, draft_id, path, content
        )

    async def validate_draft(
        self, user_id: str, draft_id: str
    ) -> SkillValidationResult:
        try:
            staged = await self._workspace_service.stage_publish(user_id, draft_id)
        except SkillPackageError as exc:
            return SkillValidationResult(
                valid=False,
                revision="",
                manifest=None,
                diagnostics=(self._diagnostic(exc),),
            )
        return SkillValidationResult(
            valid=True,
            revision=staged.revision,
            manifest=staged.build.inspected.manifest,
            diagnostics=(),
        )

    async def publish_draft(
        self,
        user_id: str,
        draft_id: str,
        *,
        expected_revision: str,
        changelog: str = "",
    ) -> PublishedSkill:
        try:
            staged = await self._workspace_service.stage_publish(user_id, draft_id)
        except SkillPackageError as exc:
            self._raise_validation(exc)
        if staged.revision != expected_revision:
            raise ConflictError("Skill 草稿已变化，请重新校验后再发布")
        return await self._publish(
            user_id=user_id,
            package_bytes=staged.package_bytes,
            build=staged.build,
            display_name=None,
            changelog=changelog,
            draft_id=draft_id,
        )

    async def import_archive(
        self,
        user_id: str,
        archive: BinaryIO,
        *,
        display_name: str | None = None,
        changelog: str = "",
    ) -> PublishedSkill:
        try:
            normalized, build = self._normalize_archive(archive)
        except SkillPackageError as exc:
            self._raise_validation(exc)
        return await self._publish(
            user_id=user_id,
            package_bytes=normalized,
            build=build,
            display_name=display_name,
            changelog=changelog,
            draft_id=None,
        )

    async def list_skills(self, user_id: str) -> list[Skill]:
        uow = self._uow_factory()
        async with uow:
            return await uow.skill.list_personal(user_id)

    async def get_skill(self, user_id: str, skill_id: str) -> SkillDetail:
        uow = self._uow_factory()
        async with uow:
            skill = await uow.skill.get_personal_by_id(user_id, skill_id)
            if not skill:
                raise NotFoundError("Skill 不存在")
            version = (
                await uow.skill.get_personal_version(
                    user_id, skill.current_version_id
                )
                if skill.current_version_id
                else None
            )
        return SkillDetail(skill=skill, version=version)

    async def update_skill(
        self,
        user_id: str,
        skill_id: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
    ) -> SkillDetail:
        if display_name is not None and not display_name.strip():
            raise BadRequestError("Skill 显示名称不能为空")
        if description is not None and not description.strip():
            raise BadRequestError("Skill 描述不能为空")
        uow = self._uow_factory()
        async with uow:
            updated = await uow.skill.update_personal(
                user_id,
                skill_id,
                display_name=display_name.strip() if display_name else None,
                description=description.strip() if description else None,
            )
            if not updated:
                raise NotFoundError("Skill 不存在")
        return await self.get_skill(user_id, skill_id)

    async def archive_skill(self, user_id: str, skill_id: str) -> None:
        uow = self._uow_factory()
        async with uow:
            if not await uow.skill.archive_personal(user_id, skill_id):
                raise NotFoundError("Skill 不存在")

    async def set_enabled(
        self, user_id: str, skill_id: str, enabled: bool
    ) -> SkillDetail:
        return await self._set_flag(user_id, skill_id, enabled=enabled)

    async def set_auto_invoke(
        self, user_id: str, skill_id: str, enabled: bool
    ) -> SkillDetail:
        return await self._set_flag(user_id, skill_id, auto_invoke=enabled)

    async def _set_flag(
        self,
        user_id: str,
        skill_id: str,
        *,
        enabled: bool | None = None,
        auto_invoke: bool | None = None,
    ) -> SkillDetail:
        uow = self._uow_factory()
        async with uow:
            updated = await uow.skill.update_personal(
                user_id,
                skill_id,
                enabled=enabled,
                auto_invoke=auto_invoke,
            )
            if not updated:
                raise NotFoundError("Skill 不存在")
        return await self.get_skill(user_id, skill_id)

    async def _publish(
        self,
        *,
        user_id: str,
        package_bytes: bytes,
        build: PackageBuildResult,
        display_name: str | None,
        changelog: str,
        draft_id: str | None,
    ) -> PublishedSkill:
        manifest = build.inspected.manifest
        existing, latest = await self._find_by_name(user_id, manifest.name)
        skill = existing or Skill(
            owner_user_id=user_id,
            name=manifest.name,
            display_name=(display_name or self._display_name(manifest.name)).strip(),
            description=manifest.description,
            scope=SkillScope.PERSONAL,
        )
        version_number = latest.version + 1 if latest else 1
        stored = await self._package_storage.upload_personal(
            user_id=user_id,
            skill_id=skill.id,
            version=version_number,
            body=io.BytesIO(package_bytes),
            expected_sha256=build.archive_sha256,
        )
        version = self._version(
            skill, version_number, manifest, build, stored, user_id, changelog
        )
        try:
            uow = self._uow_factory()
            async with uow:
                if existing is None:
                    await uow.skill.save_skill(skill)
                await uow.skill.save_version(version)
                updated = await uow.skill.update_personal(
                    user_id,
                    skill.id,
                    display_name=display_name.strip() if display_name else None,
                    description=manifest.description,
                    current_version_id=version.id,
                )
                if not updated:
                    raise RuntimeError("Unable to update the published Skill pointer")
        except Exception:
            await self._delete_uploaded(user_id, stored)
            raise

        published_skill = skill.model_copy(
            update={
                "display_name": display_name.strip()
                if display_name
                else skill.display_name,
                "description": manifest.description,
                "current_version_id": version.id,
            }
        )
        if draft_id:
            try:
                await self._workspace_service.delete_draft(user_id, draft_id)
            except Exception:
                logger.exception("Failed to clean published Skill draft %s", draft_id)
        return PublishedSkill(skill=published_skill, version=version)

    async def _find_by_name(
        self, user_id: str, name: str
    ) -> tuple[Skill | None, SkillVersion | None]:
        uow = self._uow_factory()
        async with uow:
            skills = await uow.skill.list_personal(user_id)
            skill = next((item for item in skills if item.name == name), None)
            latest = (
                await uow.skill.get_personal_version(
                    user_id, skill.current_version_id
                )
                if skill and skill.current_version_id
                else None
            )
        return skill, latest

    async def _delete_uploaded(
        self, user_id: str, stored: StoredSkillPackage
    ) -> None:
        try:
            await self._package_storage.delete_personal(
                user_id=user_id,
                storage_provider=stored.storage_provider,
                storage_key=stored.storage_key,
                storage_config=stored.storage_config,
            )
        except Exception:
            logger.exception("Failed to remove orphaned Skill package %s", stored.storage_key)

    def _normalize_archive(
        self, archive: BinaryIO
    ) -> tuple[bytes, PackageBuildResult]:
        with tempfile.TemporaryDirectory(prefix="agentic-skill-import-") as temp:
            destination = Path(temp) / "extracted"
            extracted = self._package_service.extract_archive(archive, destination)
            output = io.BytesIO()
            build = self._package_service.build_archive(
                destination / extracted.inspected.root_name, output
            )
            return output.getvalue(), build

    @staticmethod
    def _version(
        skill: Skill,
        version_number: int,
        manifest: SkillManifest,
        build: PackageBuildResult,
        stored: StoredSkillPackage,
        user_id: str,
        changelog: str,
    ) -> SkillVersion:
        return SkillVersion(
            skill_id=skill.id,
            version=version_number,
            manifest=manifest.model_dump(mode="json", by_alias=True),
            storage_provider=stored.storage_provider,
            storage_key=stored.storage_key,
            storage_config=stored.storage_config,
            package_sha256=stored.package_sha256,
            package_size=stored.package_size,
            file_count=len(build.inspected.files),
            changelog=changelog.strip(),
            created_by_user_id=user_id,
        )

    @staticmethod
    def _initial_skill_md(manifest: SkillManifest, display_name: str) -> str:
        title = display_name.strip() or SkillService._display_name(manifest.name)
        return (
            "---\n"
            f"name: {json.dumps(manifest.name, ensure_ascii=False)}\n"
            f"description: {json.dumps(manifest.description, ensure_ascii=False)}\n"
            "---\n\n"
            f"# {title}\n\n"
            "Describe the reusable workflow and execution guidance here.\n"
        )

    @staticmethod
    def _display_name(name: str) -> str:
        return " ".join(part.capitalize() for part in name.split("-"))

    @staticmethod
    def _diagnostic(error: SkillPackageError) -> SkillValidationDiagnostic:
        return SkillValidationDiagnostic(
            file="SKILL.md",
            line=None,
            column=None,
            code=error.code,
            message=error.message,
        )

    @classmethod
    def _raise_validation(cls, error: SkillPackageError) -> None:
        diagnostic = cls._diagnostic(error)
        raise ValidationError(
            "Skill 包校验失败",
            data={"diagnostics": [diagnostic.__dict__]},
        ) from error
