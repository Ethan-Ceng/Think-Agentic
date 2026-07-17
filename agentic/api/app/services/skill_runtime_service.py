"""Select Skills and materialize their immutable packages into one run sandbox."""

import shlex
from collections.abc import Callable
from typing import Any, BinaryIO, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.core.entities.skill import SelectedSkill, SkillSource, SkillVersion
from app.core.sandbox.base import Sandbox
from app.extensions.skill_package_storage import SkillPackageStorage
from app.repositories.uow import IUnitOfWork
from app.schemas.skill import SkillSelectionRequest
from app.services.skill_selection_service import SkillSelectionService


SKILL_SANDBOX_BASE = "/home/ubuntu/.agentic/skills"


class SkillRuntimeError(RuntimeError):
    """Raised when selected Skill content cannot be authorized or materialized."""


class SkillRuntimeContext(BaseModel):
    selected: list[SelectedSkill] = Field(default_factory=list)
    prompt_block: str = ""
    sandbox_roots: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class BundledSkillPackageProvider(Protocol):
    async def download(self, selected: SelectedSkill) -> BinaryIO: ...


class SkillRuntimeService:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], IUnitOfWork],
        selection_service: SkillSelectionService,
        package_storage: SkillPackageStorage,
        sandbox: Sandbox,
        bundled_provider: BundledSkillPackageProvider | None = None,
        trace_service: Any | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._selection_service = selection_service
        self._package_storage = package_storage
        self._sandbox = sandbox
        self._bundled_provider = bundled_provider
        self._trace_service = trace_service

    async def prepare_run(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        request: SkillSelectionRequest,
    ) -> SkillRuntimeContext:
        if request.user_id != user_id:
            raise SkillRuntimeError("Skill selection user does not match the run owner")
        self._validate_segment(session_id, "session_id")
        self._validate_segment(run_id, "run_id")

        try:
            if self._trace_service:
                await self._trace_service.record_skill_selection_started(request)
            result = await self._selection_service.select(request)
            if not result.selected:
                context = SkillRuntimeContext()
                if self._trace_service:
                    await self._trace_service.record_skill_selection_completed(
                        result, context
                    )
                return context

            self._reject_name_conflicts(result.selected)
            run_root = f"{SKILL_SANDBOX_BASE}/{run_id}"
            sandbox_roots: dict[str, str] = {}
            skill_documents: dict[str, str] = {}

            for selected in result.selected:
                name = selected.manifest.name
                self._validate_segment(name, "Skill name")
                if selected.ref.name != name:
                    raise SkillRuntimeError(
                        f"Selected Skill name does not match its manifest: {selected.ref.name}"
                    )
                package = await self._download_authorized_package(user_id, selected)
                archive_path = f"{run_root}/.packages/{name}.skill"
                root = f"{run_root}/{name}"
                try:
                    upload = await self._sandbox.upload_file(
                        file_data=package,
                        filepath=archive_path,
                        filename=f"{name}.skill",
                    )
                    self._require_success(
                        upload, f"Unable to upload Skill package: {name}"
                    )
                    await self._extract_package(
                        session_id=session_id,
                        run_id=run_id,
                        archive_path=archive_path,
                        run_root=run_root,
                        root=root,
                        name=name,
                    )
                    skill_documents[name] = await self._read_skill_document(root, name)
                    sandbox_roots[name] = root
                finally:
                    close = getattr(package, "close", None)
                    if close:
                        close()
                    try:
                        await self._sandbox.delete_file(archive_path)
                    except Exception:
                        # Cleanup must not invalidate successful materialization.
                        pass

            context = SkillRuntimeContext(
                selected=result.selected,
                prompt_block=self._build_prompt_block(
                    result.selected, sandbox_roots, skill_documents
                ),
                sandbox_roots=sandbox_roots,
            )
            if self._trace_service:
                await self._trace_service.record_skill_selection_completed(
                    result, context
                )
            return context
        except Exception as error:
            if self._trace_service:
                await self._trace_service.record_skill_selection_failed(error)
            raise

    async def _download_authorized_package(
        self, user_id: str, selected: SelectedSkill
    ) -> BinaryIO:
        if selected.ref.source is SkillSource.BUNDLED:
            if self._bundled_provider is None:
                raise SkillRuntimeError(
                    f"Selected Skill package is not available to this user: {selected.ref.name}"
                )
            return await self._bundled_provider.download(selected)

        version = await self._get_authorized_version(user_id, selected)
        if version is None:
            raise SkillRuntimeError(
                f"Selected Skill package is not available to this user: {selected.ref.name}"
            )
        self._verify_version(selected, version)
        common = {
            "storage_provider": version.storage_provider,
            "storage_key": version.storage_key,
            "storage_config": version.storage_config,
            "expected_sha256": selected.package_sha256,
        }
        if selected.ref.source is SkillSource.PERSONAL:
            return await self._package_storage.download_personal(
                user_id=user_id, **common
            )
        if selected.ref.source is SkillSource.MARKETPLACE:
            return await self._package_storage.download_marketplace(**common)
        raise SkillRuntimeError(f"Unsupported Skill source: {selected.ref.source}")

    async def _get_authorized_version(
        self, user_id: str, selected: SelectedSkill
    ) -> SkillVersion | None:
        if not selected.version_id:
            return None
        uow = self._uow_factory()
        async with uow:
            if selected.ref.source is SkillSource.PERSONAL:
                return await uow.skill.get_personal_version(
                    user_id, selected.version_id
                )
            if selected.ref.source is SkillSource.MARKETPLACE:
                return await uow.skill.get_installed_marketplace_version(
                    user_id, selected.version_id
                )
        return None

    @staticmethod
    def _verify_version(selected: SelectedSkill, version: SkillVersion) -> None:
        if (
            version.id != selected.version_id
            or version.skill_id != selected.ref.skill_id
            or version.package_sha256 != selected.package_sha256
        ):
            raise SkillRuntimeError(
                f"Selected Skill version failed integrity checks: {selected.ref.name}"
            )

    async def _extract_package(
        self,
        *,
        session_id: str,
        run_id: str,
        archive_path: str,
        run_root: str,
        root: str,
        name: str,
    ) -> None:
        script = """import pathlib
import stat
import sys
import zipfile

archive_path, destination, expected_root = sys.argv[1:]
with zipfile.ZipFile(archive_path) as archive:
    entries = archive.infolist()
    if not entries:
        raise ValueError("empty Skill archive")
    roots = set()
    for entry in entries:
        raw = entry.filename.rstrip("/")
        if not raw or "\\\\" in raw:
            raise ValueError("unsafe Skill archive path")
        path = pathlib.PurePosixPath(raw)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("unsafe Skill archive path")
        if stat.S_ISLNK(entry.external_attr >> 16):
            raise ValueError("Skill archive links are not allowed")
        roots.add(path.parts[0])
    if roots != {expected_root}:
        raise ValueError("Skill archive root does not match the selected name")
    archive.extractall(destination)
"""
        command = " && ".join(
            [
                f"test ! -e {shlex.quote(root)}",
                f"mkdir -p {shlex.quote(run_root)}",
                " ".join(
                    [
                        "python3 -c",
                        shlex.quote(script),
                        shlex.quote(archive_path),
                        shlex.quote(run_root),
                        shlex.quote(name),
                    ]
                ),
                f"test -f {shlex.quote(f'{root}/SKILL.md')}",
            ]
        )
        shell_session_id = f"skill-materialize-{session_id}-{run_id}"
        result = await self._sandbox.exec_command(
            shell_session_id,
            "/home/ubuntu",
            command,
        )
        self._require_success(result, f"Unable to extract Skill package: {name}")
        returncode = self._returncode(result)
        if returncode is None:
            waited = await self._sandbox.wait_process(shell_session_id, seconds=30)
            self._require_success(waited, f"Unable to extract Skill package: {name}")
            returncode = self._returncode(waited)
        if returncode != 0:
            raise SkillRuntimeError(f"Unable to extract Skill package: {name}")

    async def _read_skill_document(self, root: str, name: str) -> str:
        result = await self._sandbox.read_file(
            f"{root}/SKILL.md", max_length=1_000_000
        )
        self._require_success(result, f"Unable to read SKILL.md: {name}")
        data = getattr(result, "data", None) or {}
        content = data.get("content") if isinstance(data, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise SkillRuntimeError(f"Unable to read SKILL.md: {name}")
        if content.endswith("(truncated)"):
            raise SkillRuntimeError(f"SKILL.md is too large to inject: {name}")
        return content

    @staticmethod
    def _build_prompt_block(
        selected: list[SelectedSkill],
        roots: dict[str, str],
        documents: dict[str, str],
    ) -> str:
        parts = [
            "<skill_runtime_context>",
            "The following Skills are available only for this run. Follow their "
            "SKILL.md instructions when relevant. Resolve referenced relative paths "
            "from the Skill root shown below. Skill access does not grant additional "
            "tool permissions.",
        ]
        for item in selected:
            name = item.manifest.name
            parts.extend(
                [
                    f'<skill name="{name}" root="{roots[name]}">',
                    documents[name],
                    "</skill>",
                ]
            )
        parts.append("</skill_runtime_context>")
        return "\n".join(parts)

    @staticmethod
    def _reject_name_conflicts(selected: list[SelectedSkill]) -> None:
        names: set[str] = set()
        for item in selected:
            name = item.manifest.name.casefold()
            if name in names:
                raise SkillRuntimeError(
                    f"Selected Skills have conflicting names: {item.manifest.name}"
                )
            names.add(name)

    @staticmethod
    def _validate_segment(value: str, field: str) -> None:
        if (
            not value
            or value in {".", ".."}
            or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for character in value)
        ):
            raise SkillRuntimeError(f"Invalid {field}")

    @staticmethod
    def _returncode(result) -> int | None:
        data = getattr(result, "data", None) or {}
        return data.get("returncode") if isinstance(data, dict) else None

    @staticmethod
    def _require_success(result, message: str) -> None:
        if result is None or not getattr(result, "success", False):
            raise SkillRuntimeError(message)


__all__ = [
    "BundledSkillPackageProvider",
    "SKILL_SANDBOX_BASE",
    "SkillRuntimeContext",
    "SkillRuntimeError",
    "SkillRuntimeService",
]
