import mimetypes
from dataclasses import dataclass

from app.core.exceptions import NotFoundException
from app.core.tools.builtin_tools.categories import BuiltinCategoryManager
from app.core.tools.builtin_tools.entities import ToolEntity
from app.core.tools.builtin_tools.providers import BuiltinProviderManager
from app.core.tools.builtin_tools.runtime import get_tool_params


@dataclass
class BuiltinToolService:
    builtin_provider_manager: BuiltinProviderManager
    builtin_category_manager: BuiltinCategoryManager

    def get_builtin_tools(self) -> list:
        builtin_tools = []
        for provider in self.builtin_provider_manager.get_providers():
            provider_entity = provider.provider_entity
            builtin_tool = {
                **provider_entity.model_dump(exclude={"icon"}),
                "tools": [],
            }
            for tool_entity in provider.get_tool_entities():
                tool_dict = {
                    **tool_entity.model_dump(),
                    "inputs": self.get_tool_inputs(tool_entity),
                }
                builtin_tool["tools"].append(tool_dict)
            builtin_tools.append(builtin_tool)
        return builtin_tools

    def get_provider_tool(self, provider_name: str, tool_name: str) -> dict:
        provider = self.builtin_provider_manager.get_provider(provider_name)
        if provider is None:
            raise NotFoundException(f"Builtin provider does not exist: {provider_name}")

        tool_entity = provider.get_tool_entity(tool_name)
        if tool_entity is None:
            raise NotFoundException(f"Builtin tool does not exist: {tool_name}")

        return {
            "provider": provider.provider_entity.model_dump(exclude={"icon", "created_at"}),
            **tool_entity.model_dump(),
            "created_at": provider.provider_entity.created_at,
            "inputs": self.get_tool_inputs(tool_entity),
        }

    def get_provider_icon(self, provider_name: str) -> tuple[bytes, str]:
        provider = self.builtin_provider_manager.get_provider(provider_name)
        if provider is None:
            raise NotFoundException(f"Builtin provider does not exist: {provider_name}")

        icon_path = provider.provider_path / "_asset" / provider.provider_entity.icon
        if not icon_path.exists():
            raise NotFoundException("Provider icon does not exist")

        mimetype, _ = mimetypes.guess_type(icon_path)
        return icon_path.read_bytes(), mimetype or "application/octet-stream"

    def get_categories(self) -> list:
        category_map = self.builtin_category_manager.get_category_map()
        return [
            {
                "name": category["entity"].name,
                "category": category["entity"].category,
                "icon": category["icon"],
            }
            for category in category_map.values()
        ]

    @classmethod
    def get_tool_inputs(cls, tool: ToolEntity) -> list:
        return [
            {
                "name": param.name,
                "description": param.label,
                "required": param.required,
                "type": param.type.value,
            }
            for param in get_tool_params(tool)
        ]
