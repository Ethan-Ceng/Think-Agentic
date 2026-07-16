import zipfile
from pathlib import Path

import pytest

from app.core.entities.skill import (
    SelectedSkill,
    SkillRef,
    SkillSelectionMode,
    SkillSource,
)
from app.core.skills.package import SkillPackageService
from app.services.bundled_skill_service import BundledSkillService
from app.services.skill_catalog_service import SkillCatalogService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def write_skill(root: Path, name: str, body: str = "Follow the workflow.") -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: Create {name} outputs.\n"
        "---\n\n"
        f"# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return directory


async def test_discovers_valid_skills_with_deterministic_hash_and_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundled"
    write_skill(root, "report-writer")

    first = BundledSkillService(roots=[root])
    second = BundledSkillService(roots=[root])
    first_item = (await first.list_skills())[0]
    second_item = (await second.list_skills())[0]

    assert first_item.ref == SkillRef(
        source=SkillSource.BUNDLED, name="report-writer"
    )
    assert first_item.package_sha256 == second_item.package_sha256
    selected = SelectedSkill(
        ref=first_item.ref,
        manifest=first_item.manifest,
        selection_mode=SkillSelectionMode.MANUAL,
        reason="Selected manually by the user.",
        package_sha256=first_item.package_sha256,
    )
    package = await first.download(selected)
    inspected = SkillPackageService().inspect_archive(package)
    assert inspected.manifest.name == "report-writer"


async def test_snapshot_is_read_only_after_discovery(tmp_path: Path) -> None:
    root = tmp_path / "bundled"
    directory = write_skill(root, "report-writer", "Original instructions.")
    service = BundledSkillService(roots=[root])
    item = (await service.list_skills())[0]
    original_hash = item.package_sha256

    (directory / "SKILL.md").write_text("changed", encoding="utf-8")
    listed_again = (await service.list_skills())[0]
    selected = SelectedSkill(
        ref=item.ref,
        manifest=item.manifest,
        selection_mode=SkillSelectionMode.MANUAL,
        reason="Selected manually by the user.",
        package_sha256=item.package_sha256,
    )
    package = await service.download(selected)

    assert listed_again.package_sha256 == original_hash
    with zipfile.ZipFile(package) as archive:
        assert b"Original instructions." in archive.read(
            "report-writer/SKILL.md"
        )


async def test_rejects_invalid_and_duplicate_layered_skills(tmp_path: Path) -> None:
    invalid_root = tmp_path / "invalid"
    invalid = invalid_root / "broken"
    invalid.mkdir(parents=True)
    (invalid / "SKILL.md").write_text("not frontmatter", encoding="utf-8")
    with pytest.raises(ValueError):
        BundledSkillService(roots=[invalid_root])

    first = tmp_path / "first"
    second = tmp_path / "second"
    write_skill(first, "same-name")
    write_skill(second, "same-name")
    with pytest.raises(ValueError, match="Duplicate bundled Skill name"):
        BundledSkillService(roots=[first, second])


async def test_application_bundle_contains_manual_only_skill_creator() -> None:
    service = BundledSkillService()
    items = await service.list_skills()
    creator = next(item for item in items if item.ref.name == "skill-creator")

    assert creator.ref.source is SkillSource.BUNDLED
    assert creator.ref.skill_id is None
    assert creator.auto_invoke is False
    assert creator.version_id is None


async def test_bundled_skills_are_visible_in_the_user_catalog(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bundled"
    write_skill(root, "report-writer")
    bundled = BundledSkillService(roots=[root])

    class EmptySkills:
        async def list_personal(self, user_id: str):
            return []

        async def list_marketplace(self):
            return []

        async def list_installed_marketplace(self, user_id: str):
            return []

    class Uow:
        skill = EmptySkills()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    catalog = await SkillCatalogService(
        uow_factory=Uow,
        bundled_provider=bundled,
    ).get_catalog("user-1")

    assert [item.selector_key for item in catalog.items] == [
        "bundled:report-writer"
    ]
    assert catalog.automatic_candidates == ()
