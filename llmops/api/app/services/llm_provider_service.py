from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundException
from app.core.language_model import LanguageModelManager
from app.core.language_model.chat_runtime import PROVIDER_RUNTIMES
from app.core.language_model.entities import ModelEntity, Provider
from app.models.llm_provider import LLMModel, LLMProvider
from app.services.base_service import BaseService
from app.services.setting_crypto import MASKED_SECRET, SettingCrypto


@dataclass
class LLMProviderService(BaseService):
    crypto: SettingCrypto = field(default_factory=SettingCrypto)
    language_model_manager: LanguageModelManager = field(default_factory=LanguageModelManager)
    settings: Settings = field(default_factory=get_settings)

    def list_providers(self, session: Session, account_id: UUID) -> list[LLMProvider]:
        self.ensure_system_providers(session, account_id)
        return (
            session.query(LLMProvider)
            .filter(LLMProvider.account_id == account_id)
            .order_by(LLMProvider.is_default.desc(), LLMProvider.updated_at.desc())
            .all()
        )

    def ensure_system_providers(self, session: Session, account_id: UUID) -> None:
        providers = session.query(LLMProvider).filter(LLMProvider.account_id == account_id).all()
        if not providers:
            self.sync_system_providers(session, account_id, reset=True)
            return
        if not any((provider.config or {}).get("source") == "system_yaml" for provider in providers):
            self.sync_system_providers(session, account_id, reset=False)

    def sync_system_providers(self, session: Session, account_id: UUID, *, reset: bool = False) -> list[LLMProvider]:
        if reset:
            provider_ids = [
                provider_id
                for (provider_id,) in session.query(LLMProvider.id).filter(LLMProvider.account_id == account_id).all()
            ]
            if provider_ids:
                session.query(LLMModel).filter(LLMModel.provider_id.in_(provider_ids)).delete(synchronize_session=False)
                session.query(LLMProvider).filter(LLMProvider.id.in_(provider_ids)).delete(synchronize_session=False)
                session.flush()

        created_or_updated: list[LLMProvider] = []
        for spec in self.system_provider_specs():
            provider = self._upsert_system_provider(session, account_id, spec)
            for model_spec in spec["models"]:
                self._upsert_system_model(session, account_id, provider, model_spec)
            created_or_updated.append(provider)
        return created_or_updated

    def system_provider_specs(self) -> list[dict[str, Any]]:
        providers = self.language_model_manager.get_providers()
        default_provider_name = self._default_provider_name(providers)
        specs = []
        for provider in providers:
            models = provider.get_model_entities()
            default_model_name = self._default_model_name(provider, models, default_provider_name)
            runtime = PROVIDER_RUNTIMES.get(provider.name)
            api_key_env = runtime.api_key_env if runtime else None
            base_url = (
                self.settings.provider_base_url(runtime.base_url_env, runtime.default_base_url)
                if runtime
                else ""
            )
            specs.append(
                {
                    "provider": provider.name,
                    "name": provider.provider_entity.label or provider.name,
                    "base_url": base_url,
                    "api_key": self.settings.provider_api_key(api_key_env),
                    "enabled": True,
                    "is_default": provider.name == default_provider_name,
                    "config": {
                        "source": "system_yaml",
                        "description": provider.provider_entity.description,
                        "icon": provider.provider_entity.icon,
                        "background": provider.provider_entity.background,
                        "supported_model_types": [
                            model_type.value for model_type in provider.provider_entity.supported_model_types
                        ],
                        "api_key_env": api_key_env or "",
                        "base_url_env": runtime.base_url_env if runtime else "",
                        "requires_api_key": runtime.requires_api_key if runtime else True,
                    },
                    "models": [
                        self._system_model_spec(model_entity, is_default=model_entity.model_name == default_model_name)
                        for model_entity in models
                    ],
                }
            )
        return specs

    def list_models(self, session: Session, account_id: UUID, provider_id: UUID) -> list[LLMModel]:
        provider = self.get_provider(session, account_id, provider_id)
        return (
            session.query(LLMModel)
            .filter(LLMModel.account_id == account_id, LLMModel.provider_id == provider.id)
            .order_by(LLMModel.is_default.desc(), LLMModel.model.asc())
            .all()
        )

    def get_provider(self, session: Session, account_id: UUID, provider_id: UUID) -> LLMProvider:
        provider = self.get(session, LLMProvider, provider_id)
        if provider is None or not self._same_id(provider.account_id, account_id):
            raise NotFoundException("LLM provider does not exist")
        return provider

    def create_provider(
        self,
        session: Session,
        account_id: UUID,
        *,
        provider: str,
        name: str,
        base_url: str,
        api_key: str = "",
        enabled: bool = True,
        is_default: bool = False,
        config: dict | None = None,
    ) -> LLMProvider:
        if is_default:
            self._clear_default_provider(session, account_id)
        return self.create(
            session,
            LLMProvider,
            account_id=account_id,
            provider=provider.strip(),
            name=name.strip() or provider.strip(),
            base_url=base_url.strip(),
            api_key_encrypted=self.crypto.encrypt(api_key.strip()) if api_key else "",
            enabled=enabled,
            is_default=is_default,
            config=config or {},
        )

    def update_provider(
        self,
        session: Session,
        account_id: UUID,
        provider_id: UUID,
        *,
        provider: str | None = None,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        enabled: bool | None = None,
        is_default: bool | None = None,
        config: dict | None = None,
    ) -> LLMProvider:
        existing = self.get_provider(session, account_id, provider_id)
        updates = {}
        if provider is not None:
            updates["provider"] = provider.strip()
        if name is not None:
            updates["name"] = name.strip()
        if base_url is not None:
            updates["base_url"] = base_url.strip()
        if api_key is not None and api_key != MASKED_SECRET:
            updates["api_key_encrypted"] = self.crypto.encrypt(api_key.strip()) if api_key else ""
        if enabled is not None:
            updates["enabled"] = enabled
        if is_default is not None:
            updates["is_default"] = is_default
            if is_default:
                self._clear_default_provider(session, account_id, exclude_id=provider_id)
        if config is not None:
            updates["config"] = config
        return self.update(session, existing, **updates)

    def delete_provider(self, session: Session, account_id: UUID, provider_id: UUID) -> LLMProvider:
        provider = self.get_provider(session, account_id, provider_id)
        session.query(LLMModel).filter(LLMModel.provider_id == provider.id).delete(synchronize_session=False)
        return self.delete(session, provider)

    def create_model(
        self,
        session: Session,
        account_id: UUID,
        provider_id: UUID,
        *,
        model: str,
        display_name: str = "",
        model_type: str = "chat",
        features: list[str] | None = None,
        context_window: int = 0,
        max_output_tokens: int = 0,
        default_parameters: dict | None = None,
        enabled: bool = True,
        is_default: bool = False,
    ) -> LLMModel:
        provider = self.get_provider(session, account_id, provider_id)
        if is_default:
            self._clear_default_model(session, account_id, provider.id)
        llm_model = LLMModel(
            account_id=account_id,
            provider_id=provider.id,
            model=model.strip(),
            display_name=display_name.strip() or model.strip(),
            model_type=model_type,
            features=features or [],
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            default_parameters=default_parameters or {},
            enabled=enabled,
            is_default=is_default,
        )
        session.add(llm_model)
        session.flush()
        session.refresh(llm_model)
        return llm_model

    def update_model(
        self,
        session: Session,
        account_id: UUID,
        provider_id: UUID,
        model_id: UUID,
        **kwargs,
    ) -> LLMModel:
        provider = self.get_provider(session, account_id, provider_id)
        model = self.get(session, LLMModel, model_id)
        if (
            model is None
            or not self._same_id(model.account_id, account_id)
            or not self._same_id(model.provider_id, provider.id)
        ):
            raise NotFoundException("LLM model does not exist")
        if kwargs.get("is_default"):
            self._clear_default_model(session, account_id, provider.id, exclude_id=model.id)
        updates = {key: value for key, value in kwargs.items() if value is not None and hasattr(model, key)}
        return self.update(session, model, **updates)

    def delete_model(self, session: Session, account_id: UUID, provider_id: UUID, model_id: UUID) -> LLMModel:
        provider = self.get_provider(session, account_id, provider_id)
        model = self.get(session, LLMModel, model_id)
        if (
            model is None
            or not self._same_id(model.account_id, account_id)
            or not self._same_id(model.provider_id, provider.id)
        ):
            raise NotFoundException("LLM model does not exist")
        return self.delete(session, model)

    def serialize_provider(self, session: Session, provider: LLMProvider, include_models: bool = True) -> dict:
        data = {
            "id": provider.id,
            "account_id": provider.account_id,
            "provider": provider.provider,
            "name": provider.name,
            "base_url": provider.base_url,
            "api_key": self.crypto.mask(provider.api_key_encrypted),
            "enabled": provider.enabled,
            "is_default": provider.is_default,
            "config": provider.config,
            "created_at": self._ts(provider.created_at),
            "updated_at": self._ts(provider.updated_at),
        }
        if include_models:
            data["models"] = [
                self.serialize_model(model)
                for model in self.list_models(session, provider.account_id, provider.id)
            ]
        return data

    @staticmethod
    def serialize_model(model: LLMModel) -> dict:
        return {
            "id": model.id,
            "account_id": model.account_id,
            "provider_id": model.provider_id,
            "model": model.model,
            "display_name": model.display_name,
            "model_type": model.model_type,
            "features": model.features,
            "context_window": model.context_window,
            "max_output_tokens": model.max_output_tokens,
            "default_parameters": model.default_parameters,
            "enabled": model.enabled,
            "is_default": model.is_default,
            "created_at": LLMProviderService._ts(model.created_at),
            "updated_at": LLMProviderService._ts(model.updated_at),
        }

    def decrypt_api_key(self, provider: LLMProvider) -> str:
        return self.crypto.decrypt(provider.api_key_encrypted)

    def _upsert_system_provider(self, session: Session, account_id: UUID, spec: dict[str, Any]) -> LLMProvider:
        provider = (
            session.query(LLMProvider)
            .filter(
                LLMProvider.account_id == account_id,
                LLMProvider.provider == spec["provider"],
                LLMProvider.name == spec["name"],
            )
            .one_or_none()
        )
        if provider is None:
            return self.create_provider(
                session,
                account_id,
                provider=spec["provider"],
                name=spec["name"],
                base_url=spec["base_url"],
                api_key=spec["api_key"],
                enabled=spec["enabled"],
                is_default=spec["is_default"],
                config=spec["config"],
            )

        updates = {
            "base_url": provider.base_url or spec["base_url"],
            "enabled": provider.enabled,
            "is_default": spec["is_default"],
            "config": {**spec["config"], **(provider.config or {})},
        }
        if not provider.api_key_encrypted and spec["api_key"]:
            updates["api_key_encrypted"] = self.crypto.encrypt(spec["api_key"])
        if spec["is_default"]:
            self._clear_default_provider(session, account_id, exclude_id=provider.id)
        return self.update(session, provider, **updates)

    def _upsert_system_model(
        self,
        session: Session,
        account_id: UUID,
        provider: LLMProvider,
        spec: dict[str, Any],
    ) -> LLMModel:
        model = (
            session.query(LLMModel)
            .filter(
                LLMModel.account_id == account_id,
                LLMModel.provider_id == provider.id,
                LLMModel.model == spec["model"],
            )
            .one_or_none()
        )
        if model is None:
            return self.create_model(session, account_id, provider.id, **spec)

        if spec["is_default"]:
            self._clear_default_model(session, account_id, provider.id, exclude_id=model.id)
        updates = {
            "display_name": model.display_name or spec["display_name"],
            "model_type": model.model_type or spec["model_type"],
            "features": model.features or spec["features"],
            "context_window": model.context_window or spec["context_window"],
            "max_output_tokens": model.max_output_tokens or spec["max_output_tokens"],
            "default_parameters": model.default_parameters or spec["default_parameters"],
            "enabled": model.enabled,
            "is_default": spec["is_default"],
        }
        return self.update(session, model, **updates)

    def _clear_default_provider(self, session: Session, account_id: UUID, exclude_id: UUID | None = None) -> None:
        query = session.query(LLMProvider).filter(LLMProvider.account_id == account_id)
        if exclude_id:
            query = query.filter(LLMProvider.id != exclude_id)
        query.update({"is_default": False}, synchronize_session=False)

    def _clear_default_model(
        self,
        session: Session,
        account_id: UUID,
        provider_id: UUID,
        exclude_id: UUID | None = None,
    ) -> None:
        query = session.query(LLMModel).filter(LLMModel.account_id == account_id, LLMModel.provider_id == provider_id)
        if exclude_id:
            query = query.filter(LLMModel.id != exclude_id)
        query.update({"is_default": False}, synchronize_session=False)

    @staticmethod
    def _ts(value) -> int:
        return int(value.timestamp()) if value else 0

    @staticmethod
    def _same_id(left, right) -> bool:
        return str(left) == str(right)

    def _default_provider_name(self, providers: list[Provider]) -> str:
        configured = self.settings.default_llm_provider
        if any(provider.name == configured for provider in providers):
            return configured
        return providers[0].name if providers else ""

    def _default_model_name(
        self,
        provider: Provider,
        models: list[ModelEntity],
        default_provider_name: str,
    ) -> str:
        if not models:
            return ""
        if provider.name == default_provider_name and any(
            model.model_name == self.settings.default_llm_model for model in models
        ):
            return self.settings.default_llm_model
        return models[0].model_name

    @classmethod
    def _system_model_spec(cls, model_entity: ModelEntity, *, is_default: bool = False) -> dict[str, Any]:
        return {
            "model": model_entity.model_name,
            "display_name": model_entity.label or model_entity.model_name,
            "model_type": model_entity.model_type.value,
            "features": [feature.value for feature in model_entity.features],
            "context_window": model_entity.context_window,
            "max_output_tokens": model_entity.max_output_tokens,
            "default_parameters": cls._default_parameters(model_entity),
            "enabled": True,
            "is_default": is_default,
        }

    @staticmethod
    def _default_parameters(model_entity: ModelEntity) -> dict[str, Any]:
        defaults = dict(model_entity.attributes)
        for parameter in model_entity.parameters:
            if parameter.default is not None:
                defaults[parameter.name] = parameter.default
        return defaults
