"""Authenticated-user-scoped workspaces for creating Skill drafts."""

import io
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from filelock import FileLock
from starlette.concurrency import run_in_threadpool

from app.core.entities.skill import SKILL_NAME_PATTERN
from app.core.skills.package import PackageBuildResult, SkillPackageService
from app.schemas.exceptions import BadRequestError, NotFoundError


@dataclass(frozen=True)
class SkillDraftWorkspace:
    draft_id: str
    skill_name: str


@dataclass(frozen=True)
class SkillWorkspaceEntry:
    path: str
    kind: Literal["file", "directory"]
    size: int | None = None


@dataclass(frozen=True)
class StagedSkillPackage:
    package_bytes: bytes
    build: PackageBuildResult
    revision: str


class SkillWorkspaceService:
    def __init__(
        self,
        *,
        root: str | Path,
        package_service: SkillPackageService,
        max_text_file_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._root = Path(root).resolve()
        self._users_root = self._root / "users"
        self._package_service = package_service
        self._max_text_file_bytes = max_text_file_bytes

    async def create_draft(
        self,
        user_id: str,
        draft_id: str,
        skill_name: str,
        skill_md: str,
    ) -> SkillDraftWorkspace:
        return await run_in_threadpool(
            self._create_draft, user_id, draft_id, skill_name, skill_md
        )

    async def list_tree(
        self, user_id: str, draft_id: str
    ) -> tuple[SkillWorkspaceEntry, ...]:
        return await run_in_threadpool(self._list_tree, user_id, draft_id)

    async def read_text(
        self, user_id: str, draft_id: str, relative_path: str
    ) -> str:
        return await run_in_threadpool(
            self._read_text, user_id, draft_id, relative_path
        )

    async def write_text(
        self,
        user_id: str,
        draft_id: str,
        relative_path: str,
        content: str,
    ) -> None:
        await run_in_threadpool(
            self._write_text, user_id, draft_id, relative_path, content
        )

    async def stage_publish(
        self, user_id: str, draft_id: str
    ) -> StagedSkillPackage:
        return await run_in_threadpool(self._stage_publish, user_id, draft_id)

    async def delete_draft(self, user_id: str, draft_id: str) -> None:
        await run_in_threadpool(self._delete_draft, user_id, draft_id)

    def _create_draft(
        self,
        user_id: str,
        draft_id: str,
        skill_name: str,
        skill_md: str,
    ) -> SkillDraftWorkspace:
        self._validate_identity(user_id, "user_id")
        self._validate_identity(draft_id, "draft_id")
        self._validate_skill_name(skill_name)
        self._validate_text_size(skill_md)
        draft_root = self._draft_root(user_id, draft_id)
        with self._lock(user_id, draft_id):
            if draft_root.exists():
                raise BadRequestError("Skill 草稿已存在")
            skill_root = draft_root / skill_name
            skill_root.mkdir(parents=True)
            for directory in ("scripts", "references", "assets"):
                (skill_root / directory).mkdir()
            self._atomic_write(skill_root / "SKILL.md", skill_md)
        return SkillDraftWorkspace(draft_id=draft_id, skill_name=skill_name)

    def _list_tree(
        self, user_id: str, draft_id: str
    ) -> tuple[SkillWorkspaceEntry, ...]:
        with self._lock(user_id, draft_id):
            skill_root = self._find_skill_root(user_id, draft_id)
            entries: list[SkillWorkspaceEntry] = []
            for path in skill_root.rglob("*"):
                if path.is_symlink():
                    raise BadRequestError("Skill 草稿中不允许符号链接")
                relative = path.relative_to(skill_root).as_posix()
                if path.is_dir():
                    entries.append(
                        SkillWorkspaceEntry(path=relative, kind="directory")
                    )
                elif path.is_file():
                    entries.append(
                        SkillWorkspaceEntry(
                            path=relative, kind="file", size=path.stat().st_size
                        )
                    )
            return tuple(
                sorted(entries, key=lambda entry: (entry.path.casefold(), entry.kind))
            )

    def _read_text(
        self, user_id: str, draft_id: str, relative_path: str
    ) -> str:
        with self._lock(user_id, draft_id):
            skill_root = self._find_skill_root(user_id, draft_id)
            target = self._resolve_file(skill_root, relative_path)
            if not target.is_file() or target.is_symlink():
                raise NotFoundError("Skill 草稿文件不存在")
            if target.stat().st_size > self._max_text_file_bytes:
                raise BadRequestError("Skill 草稿文件超过大小限制")
            try:
                return target.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise BadRequestError("Skill 草稿文件不是有效的 UTF-8 文本") from exc

    def _write_text(
        self,
        user_id: str,
        draft_id: str,
        relative_path: str,
        content: str,
    ) -> None:
        self._validate_text_size(content)
        with self._lock(user_id, draft_id):
            skill_root = self._find_skill_root(user_id, draft_id)
            target = self._resolve_file(skill_root, relative_path)
            self._assert_no_symlink_ancestors(skill_root, target.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or target.is_dir():
                raise BadRequestError("非法的 Skill 草稿文件路径")
            self._atomic_write(target, content)

    def _stage_publish(
        self, user_id: str, draft_id: str
    ) -> StagedSkillPackage:
        with self._lock(user_id, draft_id):
            skill_root = self._find_skill_root(user_id, draft_id)
            self._package_service.inspect_directory(skill_root)
            with tempfile.TemporaryDirectory(prefix="agentic-skill-stage-") as temp:
                snapshot_root = Path(temp) / skill_root.name
                shutil.copytree(skill_root, snapshot_root)
                output = io.BytesIO()
                build = self._package_service.build_archive(snapshot_root, output)
                package_bytes = output.getvalue()
        return StagedSkillPackage(
            package_bytes=package_bytes,
            build=build,
            revision=build.inspected.content_sha256,
        )

    def _delete_draft(self, user_id: str, draft_id: str) -> None:
        with self._lock(user_id, draft_id):
            draft_root = self._draft_root(user_id, draft_id)
            if not draft_root.is_dir() or draft_root.is_symlink():
                raise NotFoundError("Skill 草稿不存在")
            shutil.rmtree(draft_root)

    def _find_skill_root(self, user_id: str, draft_id: str) -> Path:
        draft_root = self._draft_root(user_id, draft_id)
        if not draft_root.is_dir() or draft_root.is_symlink():
            raise NotFoundError("Skill 草稿不存在")
        roots = [
            child
            for child in draft_root.iterdir()
            if child.is_dir() and not child.is_symlink()
        ]
        if len(roots) != 1:
            raise BadRequestError("Skill 草稿目录结构无效")
        return roots[0]

    def _draft_root(self, user_id: str, draft_id: str) -> Path:
        self._validate_identity(user_id, "user_id")
        self._validate_identity(draft_id, "draft_id")
        user_root = (self._users_root / user_id).resolve()
        draft_root = (user_root / draft_id).resolve()
        try:
            draft_root.relative_to(user_root)
            user_root.relative_to(self._users_root)
        except ValueError as exc:
            raise BadRequestError("非法的 Skill 草稿路径") from exc
        return draft_root

    def _resolve_file(self, skill_root: Path, relative_path: str) -> Path:
        if (
            not relative_path
            or "\\" in relative_path
            or relative_path.startswith("/")
            or ":" in relative_path
            or "\x00" in relative_path
        ):
            raise BadRequestError("非法的 Skill 草稿文件路径")
        pure_path = PurePosixPath(relative_path)
        if any(part in {"", ".", ".."} for part in relative_path.split("/")):
            raise BadRequestError("非法的 Skill 草稿文件路径")
        raw_target = skill_root.joinpath(*pure_path.parts)
        current = skill_root
        for part in pure_path.parts:
            current = current / part
            if current.is_symlink():
                raise BadRequestError("Skill 草稿路径中不允许符号链接")
        target = raw_target.resolve()
        try:
            target.relative_to(skill_root.resolve())
        except ValueError as exc:
            raise BadRequestError("Skill 草稿文件路径越界") from exc
        return target

    def _lock(self, user_id: str, draft_id: str) -> FileLock:
        draft_root = self._draft_root(user_id, draft_id)
        draft_root.parent.mkdir(parents=True, exist_ok=True)
        return FileLock(str(draft_root.with_suffix(".lock")), timeout=10)

    @staticmethod
    def _atomic_write(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8", newline="")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _assert_no_symlink_ancestors(root: Path, parent: Path) -> None:
        current = parent
        while current != root:
            if current.is_symlink():
                raise BadRequestError("Skill 草稿路径中不允许符号链接")
            current = current.parent

    def _validate_text_size(self, content: str) -> None:
        if len(content.encode("utf-8")) > self._max_text_file_bytes:
            raise BadRequestError("Skill 草稿文件超过大小限制")

    @staticmethod
    def _validate_identity(value: str, field: str) -> None:
        if (
            not value
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or ":" in value
            or "\x00" in value
        ):
            raise BadRequestError(f"非法的 {field}")

    @staticmethod
    def _validate_skill_name(skill_name: str) -> None:
        if not re.fullmatch(SKILL_NAME_PATTERN, skill_name):
            raise BadRequestError("Skill 名称格式错误")
