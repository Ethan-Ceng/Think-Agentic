"""Validated, immutable application-bundled Skills."""

import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import API_ROOT
from app.core.entities.skill import SelectedSkill, SkillRef, SkillSource
from app.core.skills.package import SkillPackageService
from app.schemas.skill import SkillCatalogItem


DEFAULT_BUNDLED_SKILL_ROOT = API_ROOT / "app" / "skills" / "bundled"


@dataclass(frozen=True)
class _BundledSkill:
    item: SkillCatalogItem
    package: bytes


class BundledSkillService:
    """Discover bundled packages once and serve an immutable in-memory snapshot."""

    def __init__(
        self,
        *,
        package_service: SkillPackageService | None = None,
        roots: Sequence[Path] | None = None,
    ) -> None:
        self._package_service = package_service or SkillPackageService()
        self._roots = tuple(Path(root) for root in (roots or [DEFAULT_BUNDLED_SKILL_ROOT]))
        self._skills = self._discover()

    async def list_skills(self) -> list[SkillCatalogItem]:
        return [entry.item.model_copy(deep=True) for entry in self._skills.values()]

    async def download(self, selected: SelectedSkill) -> BinaryIO:
        entry = self._skills.get(selected.ref.name)
        if (
            entry is None
            or selected.ref.source is not SkillSource.BUNDLED
            or selected.ref.skill_id is not None
            or selected.package_sha256 != entry.item.package_sha256
            or selected.manifest != entry.item.manifest
        ):
            raise ValueError(f"Bundled Skill failed integrity checks: {selected.ref.name}")
        return io.BytesIO(entry.package)

    def _discover(self) -> dict[str, _BundledSkill]:
        discovered: dict[str, _BundledSkill] = {}
        for root in self._roots:
            if not root.exists():
                continue
            if not root.is_dir() or root.is_symlink():
                raise ValueError(f"Bundled Skill root is not a directory: {root}")
            for directory in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
                if not directory.is_dir() or directory.is_symlink():
                    continue
                output = io.BytesIO()
                build = self._package_service.build_archive(directory, output)
                manifest = build.inspected.manifest
                if manifest.name in discovered:
                    raise ValueError(f"Duplicate bundled Skill name: {manifest.name}")
                item = SkillCatalogItem(
                    ref=SkillRef(
                        source=SkillSource.BUNDLED,
                        name=manifest.name,
                    ),
                    display_name=self._display_name(manifest.name),
                    manifest=manifest,
                    package_sha256=build.archive_sha256,
                    auto_invoke=False,
                )
                discovered[manifest.name] = _BundledSkill(
                    item=item,
                    package=output.getvalue(),
                )
        return discovered

    @staticmethod
    def _display_name(name: str) -> str:
        return " ".join(part.capitalize() for part in name.split("-"))
