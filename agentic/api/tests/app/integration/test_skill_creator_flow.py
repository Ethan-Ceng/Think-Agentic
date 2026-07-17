from pathlib import Path

import pytest

from app.core.skills.package import SkillPackageService
from app.core.tools.skill_draft import SkillDraftTool
from app.services.skill_workspace_service import SkillWorkspaceService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_creator_can_revise_diagnostics_and_handoff_without_publish(
    tmp_path: Path,
) -> None:
    tool = SkillDraftTool(
        user_id="user-creator",
        workspace=SkillWorkspaceService(
            root=tmp_path / "workspaces",
            package_service=SkillPackageService(),
        ),
    )
    created = await tool.invoke(
        "skill_draft_create",
        name="release-notes",
        description="Create concise release notes from a set of merged changes.",
    )
    draft_id = created.data["draft_id"]

    invalid_markdown = """---
name: release-notes
description: Create release notes.
unsupported: true
---

# Release Notes
"""
    assert (
        await tool.invoke(
            "skill_draft_write",
            draft_id=draft_id,
            path="SKILL.md",
            content=invalid_markdown,
        )
    ).success
    invalid = await tool.invoke("skill_draft_validate", draft_id=draft_id)
    assert invalid.success is False
    assert invalid.data["valid"] is False
    assert invalid.data["diagnostics"]

    revised_markdown = """---
name: release-notes
description: Create concise release notes from merged changes when a user asks for a release summary.
---

# Release Notes

1. Group changes by user impact.
2. State breaking changes first.
3. Link details from references when needed.
"""
    await tool.invoke(
        "skill_draft_write",
        draft_id=draft_id,
        path="SKILL.md",
        content=revised_markdown,
    )
    await tool.invoke(
        "skill_draft_write",
        draft_id=draft_id,
        path="references/style.md",
        content="# Style\n\nPrefer short, user-facing bullets.\n",
    )
    valid = await tool.invoke("skill_draft_validate", draft_id=draft_id)
    tree = await tool.invoke("skill_draft_tree", draft_id=draft_id)

    assert valid.success is True
    assert valid.data["valid"] is True
    assert valid.data["revision"]
    assert {entry["path"] for entry in tree.data["tree"]} >= {
        "SKILL.md",
        "references/style.md",
    }
    assert all(
        "publish" not in schema["function"]["name"] for schema in tool.get_tools()
    )
