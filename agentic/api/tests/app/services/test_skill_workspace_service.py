import asyncio
import io
from pathlib import Path

import pytest

from app.core.skills.package import SkillPackageService
from app.schemas.exceptions import BadRequestError, NotFoundError
from app.services.skill_workspace_service import SkillWorkspaceService


FIXTURE_ROOT = (
    Path(__file__).parents[2] / "fixtures" / "skills" / "report-writer"
)
SKILL_MD = (FIXTURE_ROOT / "SKILL.md").read_text(encoding="utf-8")


def service(tmp_path: Path) -> SkillWorkspaceService:
    return SkillWorkspaceService(
        root=tmp_path / "skill-workspaces",
        package_service=SkillPackageService(),
    )


def test_create_tree_and_utf8_file_round_trip(tmp_path: Path) -> None:
    workspaces = service(tmp_path)

    async def run() -> None:
        created = await workspaces.create_draft(
            user_id="user-1",
            draft_id="draft-1",
            skill_name="report-writer",
            skill_md=SKILL_MD,
        )
        assert created.skill_name == "report-writer"

        await workspaces.write_text(
            "user-1", "draft-1", "references/中文.md", "# 规范\n\n保持简洁。\n"
        )
        assert (
            await workspaces.read_text(
                "user-1", "draft-1", "references/中文.md"
            )
            == "# 规范\n\n保持简洁。\n"
        )

        tree = await workspaces.list_tree("user-1", "draft-1")
        paths = {entry.path: entry.kind for entry in tree}
        assert paths["SKILL.md"] == "file"
        assert paths["references"] == "directory"
        assert paths["references/中文.md"] == "file"
        assert paths["scripts"] == "directory"
        assert paths["assets"] == "directory"

    asyncio.run(run())


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../other/SKILL.md",
        "/absolute.md",
        "references/../../secret.md",
        "references\\escape.md",
        "references//empty.md",
        "C:/escape.md",
        "",
    ],
)
def test_workspace_rejects_path_traversal(
    tmp_path: Path, unsafe_path: str
) -> None:
    workspaces = service(tmp_path)

    async def run() -> None:
        await workspaces.create_draft(
            "user-1", "draft-1", "report-writer", SKILL_MD
        )
        with pytest.raises(BadRequestError):
            await workspaces.write_text(
                "user-1", "draft-1", unsafe_path, "unsafe"
            )

    asyncio.run(run())


def test_workspace_is_scoped_to_authenticated_user(tmp_path: Path) -> None:
    workspaces = service(tmp_path)

    async def run() -> None:
        await workspaces.create_draft(
            "user-1", "draft-1", "report-writer", SKILL_MD
        )
        with pytest.raises(NotFoundError):
            await workspaces.read_text("user-2", "draft-1", "SKILL.md")
        with pytest.raises(NotFoundError):
            await workspaces.list_tree("user-2", "draft-1")

    asyncio.run(run())


def test_publish_staging_is_an_immutable_validated_snapshot(
    tmp_path: Path,
) -> None:
    workspaces = service(tmp_path)

    async def run() -> None:
        await workspaces.create_draft(
            "user-1", "draft-1", "report-writer", SKILL_MD
        )
        await workspaces.write_text(
            "user-1", "draft-1", "references/style.md", "first revision"
        )

        staged = await workspaces.stage_publish("user-1", "draft-1")
        await workspaces.write_text(
            "user-1", "draft-1", "references/style.md", "second revision"
        )

        inspected = SkillPackageService().inspect_archive(
            io.BytesIO(staged.package_bytes)
        )
        style = next(
            item for item in inspected.files if item.path == "references/style.md"
        )
        current_style = next(
            item
            for item in SkillPackageService()
            .inspect_directory(
                tmp_path
                / "skill-workspaces/users/user-1/draft-1/report-writer"
            )
            .files
            if item.path == "references/style.md"
        )
        assert style.sha256 != current_style.sha256
        assert staged.build.archive_sha256
        assert staged.revision == staged.build.inspected.content_sha256
        assert not list((tmp_path / "skill-workspaces").rglob("*.tmp"))

    asyncio.run(run())


def test_workspace_rejects_unsafe_identity_segments(tmp_path: Path) -> None:
    workspaces = service(tmp_path)

    async def run() -> None:
        with pytest.raises(BadRequestError):
            await workspaces.create_draft(
                "../user-2", "draft-1", "report-writer", SKILL_MD
            )
        with pytest.raises(BadRequestError):
            await workspaces.create_draft(
                "user-1", "../draft-2", "report-writer", SKILL_MD
            )

    asyncio.run(run())
