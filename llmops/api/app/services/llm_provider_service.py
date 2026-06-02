from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.llm_provider import LLMModel, LLMProvider
from app.services.base_service import BaseService
from app.services.setting_crypto import MASKED_SECRET, SettingCrypto


@dataclass
class LLMProviderService(BaseService):
    crypto: SettingCrypto = field(default_factory=SettingCrypto)

    def list_providers(self, session: Session, account_id: UUID) -> list[LLMProvider]:
        return (
            session.query(LLMProvider)
            .filter(LLMProvider.account_id == account_id)
            .order_by(LLMProvider.is_default.desc(), LLMProvider.updated_at.desc())
            .all()
        )

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
