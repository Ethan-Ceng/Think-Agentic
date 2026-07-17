"""Authenticated-user-bound tools for preparing, but never publishing, Skill drafts."""

import json
import uuid
from dataclasses import asdict

from app.core.entities.skill import SkillManifest
from app.core.entities.tool_result import ToolResult
from app.core.skills.package import SkillPackageError
from app.services.skill_workspace_service import SkillWorkspaceService

from .base import BaseTool, tool


class SkillDraftTool(BaseTool):
    name = "skill_draft"

    def __init__(self, *, user_id: str, workspace: SkillWorkspaceService) -> None:
        super().__init__()
        self._user_id = user_id
        self._workspace = workspace

    @tool(
        name="skill_draft_create",
        description="Create an isolated Skill draft for the current user.",
        parameters={
            "name": {
                "type": "string",
                "description": "Lowercase kebab-case Skill name.",
            },
            "description": {
                "type": "string",
                "description": "What the Skill does and when it should be used.",
            },
        },
        required=["name", "description"],
    )
    async def create(self, name: str, description: str) -> ToolResult[dict]:
        try:
            manifest = SkillManifest(name=name, description=description)
            draft_id = str(uuid.uuid4())
            markdown = (
                "---\n"
                f"name: {json.dumps(manifest.name, ensure_ascii=False)}\n"
                f"description: {json.dumps(manifest.description, ensure_ascii=False)}\n"
                "---\n\n"
                f"# {self._display_name(manifest.name)}\n\n"
                "Describe the reusable workflow here.\n"
            )
            created = await self._workspace.create_draft(
                self._user_id,
                draft_id,
                manifest.name,
                markdown,
            )
            return ToolResult(data=asdict(created))
        except Exception as exc:
            return self._failure(exc)

    @tool(
        name="skill_draft_tree",
        description="List files and directories in one current-user Skill draft.",
        parameters={
            "draft_id": {"type": "string", "description": "Draft identifier."},
        },
        required=["draft_id"],
    )
    async def tree(self, draft_id: str) -> ToolResult[dict]:
        try:
            entries = await self._workspace.list_tree(self._user_id, draft_id)
            return ToolResult(
                data={"draft_id": draft_id, "tree": [asdict(item) for item in entries]}
            )
        except Exception as exc:
            return self._failure(exc)

    @tool(
        name="skill_draft_read",
        description="Read a UTF-8 text file from one current-user Skill draft.",
        parameters={
            "draft_id": {"type": "string", "description": "Draft identifier."},
            "path": {"type": "string", "description": "Path relative to the Skill root."},
        },
        required=["draft_id", "path"],
    )
    async def read(self, draft_id: str, path: str) -> ToolResult[dict]:
        try:
            content = await self._workspace.read_text(self._user_id, draft_id, path)
            return ToolResult(data={"draft_id": draft_id, "path": path, "content": content})
        except Exception as exc:
            return self._failure(exc)

    @tool(
        name="skill_draft_write",
        description="Create or replace a UTF-8 text file in one current-user Skill draft.",
        parameters={
            "draft_id": {"type": "string", "description": "Draft identifier."},
            "path": {"type": "string", "description": "Path relative to the Skill root."},
            "content": {"type": "string", "description": "Complete UTF-8 file content."},
        },
        required=["draft_id", "path", "content"],
    )
    async def write(self, draft_id: str, path: str, content: str) -> ToolResult[dict]:
        try:
            await self._workspace.write_text(self._user_id, draft_id, path, content)
            return ToolResult(data={"draft_id": draft_id, "path": path})
        except Exception as exc:
            return self._failure(exc)

    @tool(
        name="skill_draft_validate",
        description="Validate a current-user Skill draft and return its revision or diagnostics.",
        parameters={
            "draft_id": {"type": "string", "description": "Draft identifier."},
        },
        required=["draft_id"],
    )
    async def validate(self, draft_id: str) -> ToolResult[dict]:
        try:
            staged = await self._workspace.stage_publish(self._user_id, draft_id)
            return ToolResult(
                data={
                    "draft_id": draft_id,
                    "valid": True,
                    "revision": staged.revision,
                    "manifest": staged.build.inspected.manifest.model_dump(
                        mode="json", by_alias=True
                    ),
                    "diagnostics": [],
                }
            )
        except SkillPackageError as exc:
            return ToolResult(
                success=False,
                message="Skill draft validation failed.",
                data={
                    "draft_id": draft_id,
                    "valid": False,
                    "revision": "",
                    "manifest": None,
                    "diagnostics": [
                        {
                            "file": "SKILL.md",
                            "line": None,
                            "column": None,
                            "code": exc.code,
                            "message": exc.message,
                        }
                    ],
                },
            )
        except Exception as exc:
            return self._failure(exc)

    @staticmethod
    def _display_name(name: str) -> str:
        return " ".join(part.capitalize() for part in name.split("-"))

    @staticmethod
    def _failure(error: Exception) -> ToolResult:
        return ToolResult(success=False, message=str(error))
