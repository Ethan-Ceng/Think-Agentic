from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundException
from app.core.language_model.entities import Provider, ProviderEntity


class LanguageModelManager(BaseModel):
    provider_map: dict[str, Provider] = Field(default_factory=dict)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_providers()

    def get_provider(self, provider_name: str) -> Provider:
        provider = self.provider_map.get(provider_name)
        if provider is None:
            raise NotFoundException("Language model provider does not exist")
        return provider

    def get_providers(self) -> list[Provider]:
        return list(self.provider_map.values())

    def _load_providers(self) -> None:
        if self.provider_map:
            return

        providers_path = Path(__file__).resolve().parent / "providers"
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
