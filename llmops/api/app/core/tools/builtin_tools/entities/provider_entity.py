from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.tools.builtin_tools.runtime import BuiltinRuntimeTool, build_builtin_runtime_tool

from .tool_entity import ToolEntity


class ProviderEntity(BaseModel):
    name: str
    label: str
    description: str
    icon: str
    background: str
    category: str
    created_at: int = 0


class Provider(BaseModel):
    name: str
    position: int
    provider_entity: ProviderEntity
    provider_path: Path
    tool_entity_map: dict[str, ToolEntity] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._provider_init()

    def get_tool_entity(self, tool_name: str) -> ToolEntity | None:
        return self.tool_entity_map.get(tool_name)

    def get_tool(self, tool_name: str) -> BuiltinRuntimeTool | None:
        tool_entity = self.get_tool_entity(tool_name)
        if tool_entity is None:
            return None
        return build_builtin_runtime_tool(tool_entity)

    def get_tool_entities(self) -> list[ToolEntity]:
        return list(self.tool_entity_map.values())

    def _provider_init(self) -> None:
        if self.tool_entity_map:
            return

        positions_yaml_path = self.provider_path / "positions.yaml"
        with positions_yaml_path.open(encoding="utf-8") as f:
            positions_yaml_data = yaml.safe_load(f) or []

        for tool_name in positions_yaml_data:
            tool_yaml_path = self.provider_path / f"{tool_name}.yaml"
            with tool_yaml_path.open(encoding="utf-8") as f:
                tool_yaml_data = yaml.safe_load(f)
            self.tool_entity_map[tool_name] = ToolEntity(**tool_yaml_data)
