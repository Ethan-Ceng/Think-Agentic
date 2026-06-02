import mimetypes
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundException
from app.core.language_model import LanguageModelManager
from app.core.language_model.entities import BaseLanguageModel
from app.core.language_model.entities.default_model_parameter_template import DEFAULT_MODEL_PARAMETER_TEMPLATE
from app.models.account import Account
from app.models.llm_provider import LLMModel, LLMProvider
from app.services.llm_provider_service import LLMProviderService


@dataclass
class LanguageModelService:
    language_model_manager: LanguageModelManager = field(default_factory=LanguageModelManager)
    settings: Settings = field(default_factory=get_settings)
    llm_provider_service: LLMProviderService = field(default_factory=LLMProviderService)

    def get_language_models(
        self,
        session: Session | None = None,
        account: Account | None = None,
    ) -> list[dict[str, Any]]:
        if session is not None and account is not None:
            db_models = self._get_db_language_models(session, account.id)
            if db_models:
                return db_models
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

    def get_language_model(
        self,
        provider_name: str,
        model_name: str,
        session: Session | None = None,
        account: Account | None = None,
    ) -> dict[str, Any]:
        if session is not None and account is not None:
            db_provider, db_model = self._find_db_model(session, account.id, provider_name, model_name)
            if db_provider is not None and db_model is not None:
                return self._db_model_to_legacy_detail(db_provider, db_model)
        provider = self.language_model_manager.get_provider(provider_name)
        return provider.get_model_entity(model_name).to_legacy_dict()

    def get_language_model_icon(self, provider_name: str) -> tuple[bytes, str]:
        provider = self.language_model_manager.get_provider(provider_name)
        icon_path = provider.provider_path / "_asset" / provider.provider_entity.icon
        if not icon_path.exists():
            raise NotFoundException("Language model provider icon does not exist")

        mimetype, _ = mimetypes.guess_type(icon_path)
        return icon_path.read_bytes(), mimetype or "application/octet-stream"

    def load_language_model(
        self,
        model_config: dict[str, Any],
        session: Session | None = None,
        account: Account | None = None,
    ) -> BaseLanguageModel:
        provider_name = str(model_config.get("provider") or "openai")
        model_name = str(model_config.get("model") or "gpt-4o-mini")
        parameters = dict(model_config.get("parameters") or {})

        if session is not None and account is not None:
            db_provider, db_model = self._find_db_model(session, account.id, provider_name, model_name)
            if db_provider is not None and db_model is not None:
                return BaseLanguageModel(
                    provider=db_provider.provider,
                    model=db_model.model,
                    parameters={**db_model.default_parameters, **parameters},
                    features=db_model.features,
                    metadata={
                        "runtime": {
                            "base_url": db_provider.base_url,
                            "api_key": self.llm_provider_service.decrypt_api_key(db_provider),
                            "requires_api_key": db_provider.provider != "ollama",
                        },
                        "provider_id": str(db_provider.id),
                        "model_id": str(db_model.id),
                    },
                )

        provider = self.language_model_manager.get_provider(provider_name)
        model_entity = provider.get_model_entity(model_name)
        return BaseLanguageModel(
            provider=provider_name,
            model=model_entity.model_name,
            parameters={**model_entity.attributes, **parameters},
            features=model_entity.features,
            metadata=model_entity.metadata,
        )

    def load_default_language_model(
        self,
        session: Session | None = None,
        account: Account | None = None,
    ) -> BaseLanguageModel:
        return self.load_language_model(self.settings.default_model_config, session=session, account=account)

    def _get_db_language_models(self, session: Session, account_id: UUID) -> list[dict[str, Any]]:
        providers = (
            session.query(LLMProvider)
            .filter(LLMProvider.account_id == account_id, LLMProvider.enabled.is_(True))
            .order_by(LLMProvider.is_default.desc(), LLMProvider.updated_at.desc())
            .all()
        )
        if not providers:
            return []

        result = []
        for position, provider in enumerate(providers, start=1):
            models = (
                session.query(LLMModel)
                .filter(
                    LLMModel.account_id == account_id,
                    LLMModel.provider_id == provider.id,
                    LLMModel.enabled.is_(True),
                )
                .order_by(LLMModel.is_default.desc(), LLMModel.model.asc())
                .all()
            )
            if not models:
                continue
            template = self.language_model_manager.provider_map.get(provider.provider)
            provider_entity = template.provider_entity if template else None
            result.append(
                {
                    "name": provider.provider,
                    "position": position,
                    "label": provider.name or provider.provider,
                    "icon": provider_entity.icon if provider_entity else "",
                    "description": provider_entity.description if provider_entity else "",
                    "background": provider_entity.background if provider_entity else "",
                    "support_model_types": sorted({model.model_type for model in models}),
                    "models": [self._db_model_to_legacy_detail(provider, model) for model in models],
                }
            )
        return result

    @staticmethod
    def _db_model_to_legacy_detail(provider: LLMProvider, model: LLMModel) -> dict[str, Any]:
        parameters = []
        for name in ("temperature", "top_p", "presence_penalty", "frequency_penalty", "max_tokens"):
            parameter = dict(DEFAULT_MODEL_PARAMETER_TEMPLATE[name])
            parameter["name"] = name
            if name in model.default_parameters:
                parameter["default"] = model.default_parameters[name]
            parameters.append(parameter)
        return {
            "model_name": model.model,
            "model": model.model,
            "label": model.display_name or model.model,
            "model_type": model.model_type,
            "features": model.features,
            "context_window": model.context_window,
            "context_windows": model.context_window,
            "max_output_tokens": model.max_output_tokens,
            "attributes": model.default_parameters,
            "parameters": parameters,
            "metadata": {"provider_id": str(provider.id), "model_id": str(model.id)},
        }

    @staticmethod
    def _find_db_model(
        session: Session,
        account_id: UUID,
        provider_name: str,
        model_name: str,
    ) -> tuple[LLMProvider | None, LLMModel | None]:
        provider = (
            session.query(LLMProvider)
            .filter(
                LLMProvider.account_id == account_id,
                LLMProvider.provider == provider_name,
                LLMProvider.enabled.is_(True),
            )
            .order_by(LLMProvider.is_default.desc(), LLMProvider.updated_at.desc())
            .first()
        )
        if provider is None:
            return None, None
        model = (
            session.query(LLMModel)
            .filter(
                LLMModel.account_id == account_id,
                LLMModel.provider_id == provider.id,
                LLMModel.model == model_name,
                LLMModel.enabled.is_(True),
            )
            .one_or_none()
        )
        return provider, model
