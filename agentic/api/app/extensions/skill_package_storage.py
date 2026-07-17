"""Immutable Skill package objects backed by configured storage providers."""

import hashlib
import io
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.entities.storage_config import (
    StorageConfig,
    StorageProvider,
)
from app.core.skills.package import SkillPackageError
from app.extensions.storage_drivers import (
    create_storage_driver,
    provider_snapshot,
)
from app.schemas.exceptions import BadRequestError


class StorageConfigReader(Protocol):
    async def get_storage_config(
        self, user_id: str, *, redact: bool = True
    ) -> StorageConfig | dict: ...


@dataclass(frozen=True)
class StoredSkillPackage:
    storage_provider: StorageProvider
    storage_key: str
    storage_config: dict
    package_sha256: str
    package_size: int


class SkillPackageStorage:
    def __init__(
        self,
        config_service: StorageConfigReader,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._config_service = config_service
        self._settings = settings or get_settings()

    async def upload_personal(
        self,
        *,
        user_id: str,
        skill_id: str,
        version: int,
        body: BinaryIO,
        expected_sha256: str,
    ) -> StoredSkillPackage:
        self._validate_segment(user_id, "user_id")
        self._validate_segment(skill_id, "skill_id")
        self._validate_version(version)
        config = await self._personal_config(user_id)
        provider = config.default_provider
        logical_key = f"personal/{user_id}/{skill_id}/{version}.skill"
        key = self._provider_key(config, provider, logical_key)
        return await self._upload(config, provider, key, body, expected_sha256)

    async def download_personal(
        self,
        *,
        user_id: str,
        storage_provider: StorageProvider,
        storage_key: str,
        storage_config: dict,
        expected_sha256: str,
    ) -> BinaryIO:
        self._validate_segment(user_id, "user_id")
        self._assert_scoped_key(storage_key, f"personal/{user_id}/")
        config = await self._personal_config(user_id)
        return await self._download(
            config,
            storage_provider,
            storage_key,
            storage_config,
            expected_sha256,
        )

    async def delete_personal(
        self,
        *,
        user_id: str,
        storage_provider: StorageProvider,
        storage_key: str,
        storage_config: dict,
    ) -> None:
        self._validate_segment(user_id, "user_id")
        self._assert_scoped_key(storage_key, f"personal/{user_id}/")
        config = await self._personal_config(user_id)
        await self._delete(
            config, storage_provider, storage_key, storage_config
        )

    async def upload_marketplace(
        self,
        *,
        skill_id: str,
        version: int,
        body: BinaryIO,
        expected_sha256: str,
    ) -> StoredSkillPackage:
        self._validate_segment(skill_id, "skill_id")
        self._validate_version(version)
        config = self._marketplace_config()
        provider = config.default_provider
        logical_key = f"marketplace/{skill_id}/{version}.skill"
        key = self._provider_key(config, provider, logical_key)
        return await self._upload(config, provider, key, body, expected_sha256)

    async def download_marketplace(
        self,
        *,
        storage_provider: StorageProvider,
        storage_key: str,
        storage_config: dict,
        expected_sha256: str,
    ) -> BinaryIO:
        self._assert_scoped_key(storage_key, "marketplace/")
        return await self._download(
            self._marketplace_config(),
            storage_provider,
            storage_key,
            storage_config,
            expected_sha256,
        )

    async def delete_marketplace(
        self,
        *,
        storage_provider: StorageProvider,
        storage_key: str,
        storage_config: dict,
    ) -> None:
        self._assert_scoped_key(storage_key, "marketplace/")
        await self._delete(
            self._marketplace_config(),
            storage_provider,
            storage_key,
            storage_config,
        )

    async def _upload(
        self,
        config: StorageConfig,
        provider: StorageProvider,
        key: str,
        body: BinaryIO,
        expected_sha256: str,
    ) -> StoredSkillPackage:
        data, digest = self._read_and_hash(body)
        if digest != expected_sha256:
            self._integrity_error("Skill package SHA-256 does not match")
        driver = create_storage_driver(
            config,
            provider,
            local_root=self._settings.skill_package_storage_path,
        )
        if await run_in_threadpool(driver.exists, key):
            raise BadRequestError("Skill 版本包已存在，不能覆盖不可变版本")
        await run_in_threadpool(driver.put, key, io.BytesIO(data))
        return StoredSkillPackage(
            storage_provider=provider,
            storage_key=key,
            storage_config=provider_snapshot(config, provider),
            package_sha256=digest,
            package_size=len(data),
        )

    async def _download(
        self,
        config: StorageConfig,
        provider: StorageProvider,
        key: str,
        snapshot: dict,
        expected_sha256: str,
    ) -> BinaryIO:
        driver = create_storage_driver(
            config,
            provider,
            local_root=self._settings.skill_package_storage_path,
            snapshot=snapshot,
        )
        source = await run_in_threadpool(driver.get, key)
        try:
            data, digest = await run_in_threadpool(self._read_and_hash, source)
        finally:
            close = getattr(source, "close", None)
            if close:
                await run_in_threadpool(close)
        if digest != expected_sha256:
            self._integrity_error("Stored Skill package failed SHA-256 verification")
        return io.BytesIO(data)

    async def _delete(
        self,
        config: StorageConfig,
        provider: StorageProvider,
        key: str,
        snapshot: dict,
    ) -> None:
        driver = create_storage_driver(
            config,
            provider,
            local_root=self._settings.skill_package_storage_path,
            snapshot=snapshot,
        )
        await run_in_threadpool(driver.delete, key)

    async def _personal_config(self, user_id: str) -> StorageConfig:
        config = await self._config_service.get_storage_config(
            user_id, redact=False
        )
        if not isinstance(config, StorageConfig):
            raise RuntimeError("Unredacted storage configuration is required")
        provider = getattr(config.providers, config.default_provider)
        if not provider.enabled:
            raise BadRequestError("默认存储 Provider 未启用")
        return config

    def _marketplace_config(self) -> StorageConfig:
        settings = self._settings
        provider = settings.marketplace_skill_storage_provider
        return StorageConfig.model_validate(
            {
                "default_provider": provider,
                "providers": {
                    "local": {"enabled": provider == "local"},
                    "qcloud_cos": {
                        "enabled": provider == "qcloud_cos",
                        "bucket": settings.marketplace_skill_cos_bucket,
                        "region": settings.marketplace_skill_cos_region,
                        "domain": settings.marketplace_skill_cos_domain,
                        "scheme": settings.marketplace_skill_cos_scheme,
                        "secret_id": settings.marketplace_skill_cos_secret_id,
                        "secret_key": settings.marketplace_skill_cos_secret_key,
                    },
                    "aliyun_oss": {
                        "enabled": provider == "aliyun_oss",
                        "bucket": settings.marketplace_skill_oss_bucket,
                        "endpoint": settings.marketplace_skill_oss_endpoint,
                        "region": settings.marketplace_skill_oss_region,
                        "domain": settings.marketplace_skill_oss_domain,
                        "path_prefix": settings.marketplace_skill_oss_path_prefix,
                        "access_key_id": settings.marketplace_skill_oss_access_key_id,
                        "access_key_secret": settings.marketplace_skill_oss_access_key_secret,
                    },
                },
            }
        )

    def _read_and_hash(self, body: BinaryIO) -> tuple[bytes, str]:
        try:
            body.seek(0)
        except (AttributeError, OSError):
            pass
        maximum = self._settings.skill_package_archive_max_bytes
        output = io.BytesIO()
        digest = hashlib.sha256()
        size = 0
        while chunk := body.read(min(1024 * 1024, maximum + 1 - size)):
            size += len(chunk)
            if size > maximum:
                raise SkillPackageError(
                    "skill_package_too_large",
                    "Skill package exceeds the configured archive limit",
                )
            output.write(chunk)
            digest.update(chunk)
        return output.getvalue(), digest.hexdigest()

    @staticmethod
    def _provider_key(
        config: StorageConfig, provider: StorageProvider, logical_key: str
    ) -> str:
        if provider == "aliyun_oss":
            prefix = config.providers.aliyun_oss.path_prefix
            if prefix:
                return f"{prefix}/skills/packages/{logical_key}"
        return logical_key

    @staticmethod
    def _assert_scoped_key(storage_key: str, expected_prefix: str) -> None:
        normalized = storage_key.strip("/")
        if "\\" in normalized or ".." in normalized.split("/"):
            raise BadRequestError("非法的 Skill 包存储路径")
        if not (
            normalized.startswith(expected_prefix)
            or f"/skills/packages/{expected_prefix}" in f"/{normalized}"
        ):
            raise BadRequestError("Skill 包不属于当前存储范围")

    @staticmethod
    def _validate_segment(value: str, field: str) -> None:
        if (
            not value
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or "\x00" in value
            or ":" in value
        ):
            raise BadRequestError(f"非法的 {field}")

    @staticmethod
    def _validate_version(version: int) -> None:
        if version < 1:
            raise BadRequestError("Skill 版本号必须大于 0")

    @staticmethod
    def _integrity_error(message: str) -> None:
        raise SkillPackageError("skill_package_integrity_error", message)
