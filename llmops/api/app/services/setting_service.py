from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import FailException, NotFoundException
from app.models.account_setting import AccountSetting
from app.services.base_service import BaseService
from app.services.setting_crypto import MASKED_SECRET, SettingCrypto

SECRET_FIELDS: dict[tuple[str, str], set[str]] = {
    ("storage", "qcloud_cos"): {"secret_id", "secret_key"},
    ("storage", "aliyun_oss"): {"access_key", "secret_key"},
}

ALLOWED_STORAGE_PROVIDERS = {"local", "qcloud_cos", "aliyun_oss"}


@dataclass
class SettingService(BaseService):
    crypto: SettingCrypto = field(default_factory=SettingCrypto)
    settings: Settings = field(default_factory=get_settings)

    def list_settings(self, session: Session, account_id: UUID, category: str | None = None) -> list[AccountSetting]:
        query = session.query(AccountSetting).filter(AccountSetting.account_id == account_id)
        if category:
            query = query.filter(AccountSetting.category == category)
        return list(query.order_by(AccountSetting.category.asc(), AccountSetting.key.asc()).all())

    def get_setting(self, session: Session, account_id: UUID, category: str, key: str) -> AccountSetting:
        setting = self._find_setting(session, account_id, category, key)
        if setting is None:
            raise NotFoundException("Setting does not exist")
        return setting

    def upsert_setting(
        self,
        session: Session,
        account_id: UUID,
        category: str,
        key: str,
        value: dict[str, Any],
        enabled: bool = True,
    ) -> AccountSetting:
        self._validate_setting(category, key, value)
        existing = self._find_setting(session, account_id, category, key)
        stored_value = self._encrypt_value(category, key, value, existing.value if existing else {})
        if existing is not None:
            return self.update(session, existing, value=stored_value, enabled=enabled)
        return self.create(
            session,
            AccountSetting,
            account_id=account_id,
            category=category,
            key=key,
            value=stored_value,
            enabled=enabled,
        )

    def get_runtime_value(self, session: Session, account_id: UUID, category: str, key: str) -> dict[str, Any]:
        setting = self._find_setting(session, account_id, category, key)
        if setting is None or not setting.enabled:
            return self._fallback_value(category, key)
        return self._decrypt_value(category, key, setting.value)

    def serialize_setting(self, setting: AccountSetting) -> dict[str, Any]:
        return {
            "id": setting.id,
            "account_id": setting.account_id,
            "category": setting.category,
            "key": setting.key,
            "value": self._mask_value(setting.category, setting.key, setting.value),
            "enabled": setting.enabled,
            "created_at": self._ts(setting.created_at),
            "updated_at": self._ts(setting.updated_at),
        }

    def _encrypt_value(
        self,
        category: str,
        key: str,
        value: dict[str, Any],
        existing_value: dict[str, Any],
    ) -> dict[str, Any]:
        encrypted = deepcopy(value)
        for field_name in SECRET_FIELDS.get((category, key), set()):
            raw_value = encrypted.get(field_name)
            if raw_value == MASKED_SECRET and existing_value.get(field_name):
                encrypted[field_name] = existing_value[field_name]
            elif raw_value:
                encrypted[field_name] = self.crypto.encrypt(str(raw_value))
            else:
                encrypted[field_name] = ""
        return encrypted

    def _decrypt_value(self, category: str, key: str, value: dict[str, Any]) -> dict[str, Any]:
        decrypted = deepcopy(value)
        for field_name in SECRET_FIELDS.get((category, key), set()):
            if decrypted.get(field_name):
                decrypted[field_name] = self.crypto.decrypt(str(decrypted[field_name]))
        return decrypted

    def _mask_value(self, category: str, key: str, value: dict[str, Any]) -> dict[str, Any]:
        masked = deepcopy(value)
        for field_name in SECRET_FIELDS.get((category, key), set()):
            if masked.get(field_name):
                masked[field_name] = self.crypto.mask(str(masked[field_name]))
        return masked

    def _fallback_value(self, category: str, key: str) -> dict[str, Any]:
        if category != "storage":
            return {}
        if key == "default":
            return {"provider": self._legacy_storage_provider()}
        if key == "local":
            return {
                "root": self.settings.local_storage_root,
                "base_url": self.settings.local_storage_base_url,
            }
        if key == "qcloud_cos":
            return {
                "bucket": self.settings.cos_bucket,
                "region": self.settings.cos_region,
                "domain": self.settings.cos_domain,
                "secret_id": self.settings.cos_secret_id,
                "secret_key": self.settings.cos_secret_key,
            }
        return {}

    def _legacy_storage_provider(self) -> str:
        if self.settings.file_storage_type == "cos":
            return "qcloud_cos"
        return "local"

    def _validate_setting(self, category: str, key: str, value: dict[str, Any]) -> None:
        if not isinstance(value, dict):
            raise FailException("Setting value must be an object")
        if category != "storage":
            return
        if key == "default":
            provider = str(value.get("provider") or "")
            if provider not in ALLOWED_STORAGE_PROVIDERS:
                raise FailException("Storage default provider is invalid")
            return
        if key not in ALLOWED_STORAGE_PROVIDERS:
            raise FailException("Storage provider is invalid")

    @staticmethod
    def _find_setting(session: Session, account_id: UUID, category: str, key: str) -> AccountSetting | None:
        return (
            session.query(AccountSetting)
            .filter(
                AccountSetting.account_id == account_id,
                AccountSetting.category == category,
                AccountSetting.key == key,
            )
            .one_or_none()
        )

    @staticmethod
    def _ts(value) -> int:
        return int(value.timestamp()) if value else 0
