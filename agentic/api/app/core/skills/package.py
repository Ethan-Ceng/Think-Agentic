import hashlib
import io
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

import skills_ref
from pydantic import ValidationError as PydanticValidationError

from app.core.entities.skill import SkillManifest

from .limits import SkillPackageLimits


class SkillPackageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SkillFileEntry:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class InspectedSkillPackage:
    root_name: str
    manifest: SkillManifest
    files: tuple[SkillFileEntry, ...]
    total_size: int
    content_sha256: str


@dataclass(frozen=True)
class PackageBuildResult:
    inspected: InspectedSkillPackage
    archive_sha256: str
    archive_size: int


class SkillPackageService:
    _WINDOWS_RESERVED_NAMES = {
        "AUX",
        "CON",
        "NUL",
        "PRN",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }

    def __init__(self, limits: SkillPackageLimits | None = None) -> None:
        self.limits = limits or SkillPackageLimits()

    def inspect_directory(self, root: Path) -> InspectedSkillPackage:
        root = Path(root)
        if not root.is_dir() or root.is_symlink():
            raise SkillPackageError(
                "skill_unsafe_archive", "Skill root must be a regular directory"
            )
        skill_md = root / "SKILL.md"
        if not skill_md.is_file() or skill_md.is_symlink():
            raise SkillPackageError(
                "skill_invalid_manifest", "Missing required root file: SKILL.md"
            )

        paths: list[tuple[str, Path, int]] = []
        seen: set[str] = set()
        total_size = 0
        for path in root.rglob("*"):
            if path.is_symlink():
                raise SkillPackageError(
                    "skill_unsafe_archive", f"Symbolic links are not allowed: {path}"
                )
            if path.is_dir():
                continue
            file_stat = path.stat()
            if not stat.S_ISREG(file_stat.st_mode):
                raise SkillPackageError(
                    "skill_unsafe_archive", f"Non-regular files are not allowed: {path}"
                )
            relative = path.relative_to(root).as_posix()
            self._validate_relative_path(relative)
            folded = relative.casefold()
            if folded in seen:
                raise SkillPackageError(
                    "skill_unsafe_archive", f"Duplicate path after case folding: {relative}"
                )
            seen.add(folded)
            self._validate_file_size(relative, file_stat.st_size)
            total_size += file_stat.st_size
            if total_size > self.limits.extracted_bytes:
                self._too_large("Extracted Skill content exceeds the size limit")
            paths.append((relative, path, file_stat.st_size))

        if len(paths) > self.limits.file_count:
            self._too_large("Skill contains too many files")

        manifest = self._read_manifest(root)
        entries: list[SkillFileEntry] = []
        content_digest = hashlib.sha256()
        for relative, path, size in sorted(
            paths,
            key=lambda item: (item[0] != "SKILL.md", item[0].casefold()),
        ):
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            entries.append(SkillFileEntry(path=relative, size=size, sha256=digest))
            encoded_path = relative.encode("utf-8")
            content_digest.update(len(encoded_path).to_bytes(4, "big"))
            content_digest.update(encoded_path)
            content_digest.update(len(content).to_bytes(8, "big"))
            content_digest.update(content)

        return InspectedSkillPackage(
            root_name=root.name,
            manifest=manifest,
            files=tuple(entries),
            total_size=total_size,
            content_sha256=content_digest.hexdigest(),
        )

    def inspect_archive(self, archive: BinaryIO) -> InspectedSkillPackage:
        data = self._read_archive(archive)
        with self._validated_temp_directory(data) as (_, inspected):
            return inspected

    def build_archive(self, root: Path, output: BinaryIO) -> PackageBuildResult:
        inspected = self.inspect_directory(root)
        root = Path(root)
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for entry in inspected.files:
                info = zipfile.ZipInfo(f"{inspected.root_name}/{entry.path}")
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(
                    info,
                    (root / Path(entry.path)).read_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
        data = buffer.getvalue()
        if len(data) > self.limits.archive_bytes:
            self._too_large("Published Skill archive exceeds the upload size limit")
        output.write(data)
        return PackageBuildResult(
            inspected=inspected,
            archive_sha256=hashlib.sha256(data).hexdigest(),
            archive_size=len(data),
        )

    def extract_archive(
        self, archive: BinaryIO, destination: Path
    ) -> PackageBuildResult:
        data = self._read_archive(archive)
        destination = Path(destination)
        if destination.is_symlink():
            raise SkillPackageError(
                "skill_unsafe_archive", "Extraction destination cannot be a symlink"
            )
        with self._validated_temp_directory(data) as (temporary_root, inspected):
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / inspected.root_name
            if target.exists() or target.is_symlink():
                raise SkillPackageError(
                    "skill_unsafe_archive", "Skill extraction target already exists"
                )
            shutil.copytree(temporary_root, target)
        return PackageBuildResult(
            inspected=inspected,
            archive_sha256=hashlib.sha256(data).hexdigest(),
            archive_size=len(data),
        )

    def _read_manifest(self, root: Path) -> SkillManifest:
        skill_md = root / "SKILL.md"
        try:
            content = skill_md.read_bytes()
            if len(content) > self.limits.skill_md_bytes:
                self._too_large("SKILL.md exceeds its size limit")
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SkillPackageError(
                "skill_invalid_manifest", "SKILL.md must be valid UTF-8"
            ) from error

        errors = skills_ref.validate(root)
        if errors:
            code = (
                "skill_name_mismatch"
                if any("must match skill name" in error for error in errors)
                else "skill_invalid_manifest"
            )
            raise SkillPackageError(code, "; ".join(errors))
        try:
            properties = skills_ref.read_properties(root)
            return SkillManifest.model_validate(properties.to_dict())
        except (skills_ref.SkillError, PydanticValidationError) as error:
            raise SkillPackageError(
                "skill_invalid_manifest", f"Invalid SKILL.md frontmatter: {error}"
            ) from error

    def _read_archive(self, archive: BinaryIO) -> bytes:
        try:
            archive.seek(0)
        except (AttributeError, OSError):
            pass
        data = archive.read(self.limits.archive_bytes + 1)
        if len(data) > self.limits.archive_bytes:
            self._too_large("Skill archive exceeds the upload size limit")
        return data

    @contextmanager
    def _validated_temp_directory(
        self, data: bytes
    ) -> Iterator[tuple[Path, InspectedSkillPackage]]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, OSError) as error:
            raise SkillPackageError(
                "skill_unsafe_archive", "Skill package is not a valid ZIP archive"
            ) from error

        with archive, tempfile.TemporaryDirectory(prefix="agentic-skill-") as temp:
            entries, root_name = self._validate_archive_entries(archive)
            temp_path = Path(temp)
            try:
                for info, relative_parts in entries:
                    target = temp_path.joinpath(*relative_parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                root = temp_path / root_name
                inspected = self.inspect_directory(root)
            except (zipfile.BadZipFile, RuntimeError, OSError) as error:
                raise SkillPackageError(
                    "skill_unsafe_archive", f"Unable to read Skill archive: {error}"
                ) from error
            yield root, inspected

    def _validate_archive_entries(
        self, archive: zipfile.ZipFile
    ) -> tuple[list[tuple[zipfile.ZipInfo, tuple[str, ...]]], str]:
        roots: set[str] = set()
        seen: set[str] = set()
        files: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
        total_size = 0
        relative_files: set[str] = set()

        for info in archive.infolist():
            raw_name = info.orig_filename
            is_directory = info.is_dir()
            normalized_name = raw_name[:-1] if is_directory else raw_name
            parts = self._validate_archive_path(normalized_name)
            roots.add(parts[0])
            if len(roots) > 1:
                raise SkillPackageError(
                    "skill_unsafe_archive", "Skill archive must contain exactly one root"
                )
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (
                mode and not is_directory and not stat.S_ISREG(mode)
            ):
                raise SkillPackageError(
                    "skill_unsafe_archive", f"Unsafe archive entry type: {raw_name}"
                )
            if info.flag_bits & 0x1:
                raise SkillPackageError(
                    "skill_unsafe_archive", "Encrypted Skill archives are not supported"
                )
            if is_directory:
                continue
            if len(parts) < 2:
                raise SkillPackageError(
                    "skill_unsafe_archive", "Files must be inside the Skill root directory"
                )
            relative = "/".join(parts[1:])
            self._validate_relative_path(relative)
            folded = relative.casefold()
            if folded in seen:
                raise SkillPackageError(
                    "skill_unsafe_archive", f"Duplicate path after case folding: {relative}"
                )
            seen.add(folded)
            relative_files.add(relative)
            self._validate_file_size(relative, info.file_size)
            total_size += info.file_size
            if total_size > self.limits.extracted_bytes:
                self._too_large("Extracted Skill content exceeds the size limit")
            files.append((info, parts))

        if not roots:
            raise SkillPackageError("skill_unsafe_archive", "Skill archive is empty")
        if len(files) > self.limits.file_count:
            self._too_large("Skill contains too many files")
        if "SKILL.md" not in relative_files:
            raise SkillPackageError(
                "skill_invalid_manifest", "Missing required root file: SKILL.md"
            )
        return files, next(iter(roots))

    def _validate_archive_path(self, raw_name: str) -> tuple[str, ...]:
        if not raw_name or "\\" in raw_name or raw_name.startswith("/"):
            raise SkillPackageError(
                "skill_unsafe_archive", f"Unsafe archive path: {raw_name}"
            )
        raw_parts = raw_name.split("/")
        if any(not part for part in raw_parts):
            raise SkillPackageError(
                "skill_unsafe_archive", f"Unsafe archive path: {raw_name}"
            )
        self._validate_path_parts(raw_parts, raw_name)
        path = PurePosixPath(raw_name)
        parts = path.parts
        if (
            path.is_absolute()
        ):
            raise SkillPackageError(
                "skill_unsafe_archive", f"Unsafe archive path: {raw_name}"
            )
        return parts

    def _validate_relative_path(self, relative: str) -> None:
        if (
            not relative
            or "\\" in relative
            or relative.startswith("/")
            or len(relative) > self.limits.relative_path_chars
        ):
            raise SkillPackageError(
                "skill_unsafe_archive", f"Unsafe or overlong Skill path: {relative}"
            )
        parts = PurePosixPath(relative).parts
        if any(part in {"", ".", ".."} for part in parts):
            raise SkillPackageError(
                "skill_unsafe_archive", f"Unsafe Skill path: {relative}"
            )
        self._validate_path_parts(list(parts), relative)

    def _validate_path_parts(self, parts: list[str], raw_path: str) -> None:
        for part in parts:
            device_name = part.split(".", 1)[0].upper()
            if (
                part in {".", ".."}
                or "\x00" in part
                or ":" in part
                or part.endswith((" ", "."))
                or any(ord(character) < 32 for character in part)
                or device_name in self._WINDOWS_RESERVED_NAMES
            ):
                raise SkillPackageError(
                    "skill_unsafe_archive", f"Unsafe Skill path: {raw_path}"
                )

    def _validate_file_size(self, relative: str, size: int) -> None:
        if size > self.limits.file_bytes:
            self._too_large(f"Skill file exceeds its size limit: {relative}")
        if relative == "SKILL.md" and size > self.limits.skill_md_bytes:
            self._too_large("SKILL.md exceeds its size limit")

    @staticmethod
    def _too_large(message: str) -> None:
        raise SkillPackageError("skill_package_too_large", message)
