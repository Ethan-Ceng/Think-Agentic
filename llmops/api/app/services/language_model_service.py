import mimetypes
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundException
from app.core.language_model import LanguageModelManager
from app.core.language_model.entities import BaseLanguageModel


@dataclass
class LanguageModelService:
    language_model_manager: LanguageModelManager = field(default_factory=LanguageModelManager)
    settings: Settings = field(default_factory=get_settings)

    def get_language_models(self) -> list[dict[str, Any]]:
        language_models = []
        for provider in self.language_model_manager.get_providers():
            provider_entity = provider.provider_entity
            language_models.append(
                {
                    "name": provider_entity.name,
                    "position": provider.position,
                    "label": provider_entity.label,
                    "icon": provider_entity.icon,
                    "description": provider_entity.description,
                    "background": provider_entity.background,
                    "support_model_types": [model_type.value for model_type in provider_entity.supported_model_types],
                    "models": [model.to_legacy_dict() for model in provider.get_model_entities()],
                }
            )
        return language_models

    def get_language_model(self, provider_name: str, model_name: str) -> dict[str, Any]:
        provider = self.language_model_manager.get_provider(provider_name)
        return provider.get_model_entity(model_name).to_legacy_dict()

    def get_language_model_icon(self, provider_name: str) -> tuple[bytes, str]:
        provider = self.language_model_manager.get_provider(provider_name)
        icon_path = provider.provider_path / "_asset" / provider.provider_entity.icon
        if not icon_path.exists():
            raise NotFoundException("Language model provider icon does not exist")

        mimetype, _ = mimetypes.guess_type(icon_path)
        return icon_path.read_bytes(), mimetype or "application/octet-stream"

    def load_language_model(self, model_config: dict[str, Any]) -> BaseLanguageModel:
        provider_name = str(model_config.get("provider") or "openai")
        model_name = str(model_config.get("model") or "gpt-4o-mini")
        parameters = dict(model_config.get("parameters") or {})

        provider = self.language_model_manager.get_provider(provider_name)
        model_entity = provider.get_model_entity(model_name)
        return BaseLanguageModel(
            provider=provider_name,
            model=model_entity.model_name,
            parameters={**model_entity.attributes, **parameters},
            features=model_entity.features,
            metadata=model_entity.metadata,
        )

    def load_default_language_model(self) -> BaseLanguageModel:
        return self.load_language_model(self.settings.default_model_config)
