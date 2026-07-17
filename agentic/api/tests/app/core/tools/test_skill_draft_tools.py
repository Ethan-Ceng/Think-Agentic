from pathlib import Path

import pytest

from app.core.entities.skill import (
    SelectedSkill,
    SkillManifest,
    SkillRef,
    SkillSelectionMode,
    SkillSource,
)
from app.core.skills.package import SkillPackageService
from app.core.tools.factory import ToolFactory
from app.core.tools.skill_draft import SkillDraftTool
from app.core.flows.planner_react import PlannerReActFlow
from app.services.skill_runtime_service import SkillRuntimeContext
from app.services.skill_workspace_service import SkillWorkspaceService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def workspace(tmp_path: Path) -> SkillWorkspaceService:
    return SkillWorkspaceService(
        root=tmp_path / "workspaces",
        package_service=SkillPackageService(),
    )


def creator_context(source: SkillSource = SkillSource.BUNDLED) -> SkillRuntimeContext:
    return SkillRuntimeContext(
        selected=[
            SelectedSkill(
                ref=SkillRef(
                    source=source,
                    skill_id=None if source is SkillSource.BUNDLED else "skill-1",
                    name="skill-creator",
                ),
                manifest=SkillManifest(
                    name="skill-creator",
                    description="Create standard Skills.",
                ),
                selection_mode=SkillSelectionMode.MANUAL,
                reason="Selected manually by the user.",
                package_sha256="a" * 64,
            )
        ]
    )


async def test_tool_contract_is_user_bound_and_has_no_publish_operation(
    tmp_path: Path,
) -> None:
    draft_tool = SkillDraftTool(user_id="user-a", workspace=workspace(tmp_path))
    schemas = draft_tool.get_tools()

    assert {schema["function"]["name"] for schema in schemas} == {
        "skill_draft_create",
        "skill_draft_tree",
        "skill_draft_read",
        "skill_draft_write",
        "skill_draft_validate",
    }
    for schema in schemas:
        properties = schema["function"]["parameters"]["properties"]
        assert "user_id" not in properties
        assert "owner_user_id" not in properties
        assert "publish" not in schema["function"]["name"]


async def test_draft_operations_reject_traversal_and_cross_user_access(
    tmp_path: Path,
) -> None:
    shared = workspace(tmp_path)
    owner = SkillDraftTool(user_id="user-a", workspace=shared)
    stranger = SkillDraftTool(user_id="user-b", workspace=shared)

    created = await owner.invoke(
        "skill_draft_create",
        name="report-writer",
        description="Create evidence-based reports.",
    )
    assert created.success
    draft_id = created.data["draft_id"]

    # An injected owner argument is discarded by BaseTool; the bound identity wins.
    owner_tree = await owner.invoke(
        "skill_draft_tree", draft_id=draft_id, user_id="user-b"
    )
    assert owner_tree.success
    assert not (await stranger.invoke("skill_draft_tree", draft_id=draft_id)).success
    assert not (
        await owner.invoke(
            "skill_draft_read", draft_id=draft_id, path="../SKILL.md"
        )
    ).success
    assert not (
        await owner.invoke(
            "skill_draft_write",
            draft_id=draft_id,
            path="references/../../outside.md",
            content="unsafe",
        )
    ).success

    written = await owner.invoke(
        "skill_draft_write",
        draft_id=draft_id,
        path="references/style.md",
        content="# Style\n\nUse concise evidence.\n",
    )
    assert written.success
    validated = await owner.invoke("skill_draft_validate", draft_id=draft_id)
    assert validated.success
    assert validated.data["valid"] is True
    assert validated.data["revision"]


async def test_flow_exposes_draft_tools_only_for_bundled_skill_creator(
    tmp_path: Path,
) -> None:
    class Agent:
        def __init__(self) -> None:
            self.contexts = []

        def set_skill_runtime_context(self, context):
            self.contexts.append(context)

    flow = object.__new__(PlannerReActFlow)
    flow._tools = []
    flow._tool_factory = ToolFactory()
    flow._skill_draft_tool = SkillDraftTool(
        user_id="user-a", workspace=workspace(tmp_path)
    )
    flow._filtered_skill_draft_tool = None
    flow.planner = Agent()
    flow.react = Agent()

    flow.set_skill_runtime_context(SkillRuntimeContext())
    assert flow._tools == []
    flow.set_skill_runtime_context(creator_context(SkillSource.PERSONAL))
    assert flow._tools == []

    flow.set_skill_runtime_context(creator_context())
    assert [tool.name for tool in flow._tools] == ["skill_draft"]
    names = {
        schema["function"]["name"]
        for schema in flow._tools[0].get_tools()
    }
    assert "skill_draft_write" in names
    assert not any("publish" in name for name in names)

    flow.set_skill_runtime_context(SkillRuntimeContext())
    assert flow._tools == []
