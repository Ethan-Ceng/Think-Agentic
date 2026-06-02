import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import FailException, NotFoundException
from app.services.setting_service import ALLOWED_STORAGE_PROVIDERS, SettingService


@dataclass(frozen=True)
class StoredObject:
    storage_provider: str
    file_path: str


class StorageDriver:
    provider = ""

    def save(self, file_path: str, content: bytes) -> StoredObject:
        raise NotImplementedError

    def read(self, file_path: str) -> bytes:
        raise NotImplementedError

    def absolute_url(self, file_path: str) -> str:
        raise NotImplementedError


@dataclass
class LocalStorageDriver(StorageDriver):
    root: str
    base_url: str
    provider: str = "local"

    def save(self, file_path: str, content: bytes) -> StoredObject:
        target_path = Path(self.local_path(file_path))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return StoredObject(storage_provider=self.provider, file_path=file_path)

    def read(self, file_path: str) -> bytes:
        target_path = Path(self.local_path(file_path))
        if not target_path.is_file():
            raise NotFoundException("File does not exist")
        return target_path.read_bytes()

    def absolute_url(self, file_path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{file_path.lstrip('/')}"

    def local_path(self, file_path: str) -> str:
        root = Path(self.root)
        if not root.is_absolute():
            root = Path.cwd() / root
        root = root.resolve()
        target = (root / file_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise NotFoundException("File does not exist") from exc
        return str(target)


@dataclass
class ConfiguredRemoteStorageDriver(StorageDriver):
    domain: str
    provider: str = ""

    def save(self, file_path: str, content: bytes) -> StoredObject:
        raise FailException(f"{self.provider} upload driver is not installed")

    def read(self, file_path: str) -> bytes:
        raise FailException(f"{self.provider} read driver is not installed")

    def absolute_url(self, file_path: str) -> str:
        return f"{self.domain.rstrip('/')}/{file_path.lstrip('/')}" if self.domain else file_path


@dataclass
class StorageService:
    setting_service: SettingService = field(default_factory=SettingService)
    settings: Settings = field(default_factory=get_settings)

    def default_provider(self, session: Session, account_id: UUID) -> str:
        value = self.setting_service.get_runtime_value(session, account_id, "storage", "default")
        provider = str(value.get("provider") or "local")
        return provider if provider in ALLOWED_STORAGE_PROVIDERS else "local"

    def get_driver(self, session: Session, account_id: UUID, provider: str | None = None) -> StorageDriver:
        provider = provider or self.default_provider(session, account_id)
        if provider == "local":
            config = self.setting_service.get_runtime_value(session, account_id, "storage", "local")
            return LocalStorageDriver(
                root=str(config.get("root") or self.settings.local_storage_root),
                base_url=str(config.get("base_url") or self.settings.local_storage_base_url),
            )
        if provider in {"qcloud_cos", "aliyun_oss"}:
            config = self.setting_service.get_runtime_value(session, account_id, "storage", provider)
            return ConfiguredRemoteStorageDriver(provider=provider, domain=str(config.get("domain") or ""))
        raise FailException("Storage provider is invalid")

    def save(self, session: Session, account_id: UUID, file_path: str, content: bytes) -> StoredObject:
        return self.get_driver(session, account_id).save(file_path, content)

    def read(self, session: Session, account_id: UUID, storage_provider: str, file_path: str) -> bytes:
        return self.get_driver(session, account_id, storage_provider).read(file_path)

    def absolute_url(self, session: Session, account_id: UUID, storage_provider: str, file_path: str) -> str:
        return self.get_driver(session, account_id, storage_provider).absolute_url(file_path)

    def local_path(self, session: Session, account_id: UUID, storage_provider: str, file_path: str) -> str:
        driver = self.get_driver(session, account_id, storage_provider)
        if not isinstance(driver, LocalStorageDriver):
            raise FailException("Only local storage has a filesystem path")
        return driver.local_path(file_path)

    @staticmethod
    def normalize_file_path(file_path: str) -> str:
        return file_path.replace("\\", "/").lstrip("/")

    @staticmethod
    def legacy_local_root(settings: Settings | None = None) -> str:
        settings = settings or get_settings()
        root = settings.local_storage_root
        return root if os.path.isabs(root) else os.path.join(os.getcwd(), root)
