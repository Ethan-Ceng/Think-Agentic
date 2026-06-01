from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.tools.builtin_tools.entities import Provider, ProviderEntity
from app.core.tools.builtin_tools.runtime import BuiltinRuntimeTool


class BuiltinProviderManager(BaseModel):
    provider_map: dict[str, Provider] = Field(default_factory=dict)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._get_provider_tool_map()

    def get_provider(self, provider_name: str) -> Provider | None:
        return self.provider_map.get(provider_name)

    def get_providers(self) -> list[Provider]:
        return list(self.provider_map.values())

    def get_provider_entities(self) -> list[ProviderEntity]:
        return [provider.provider_entity for provider in self.provider_map.values()]

    def get_tool(self, provider_name: str, tool_name: str) -> BuiltinRuntimeTool | None:
        provider = self.get_provider(provider_name)
        if provider is None:
            return None
        return provider.get_tool(tool_name)

    def _get_provider_tool_map(self) -> None:
        if self.provider_map:
            return

        providers_path = Path(__file__).resolve().parent
        with (providers_path / "providers.yaml").open(encoding="utf-8") as f:
            providers_yaml_data = yaml.safe_load(f) or []

        for idx, provider_data in enumerate(providers_yaml_data):
            provider_entity = ProviderEntity(**provider_data)
            self.provider_map[provider_entity.name] = Provider(
                name=provider_entity.name,
                position=idx + 1,
                provider_entity=provider_entity,
                provider_path=providers_path / provider_entity.name,
            )
