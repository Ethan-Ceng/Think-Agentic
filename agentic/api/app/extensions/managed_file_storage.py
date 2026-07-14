"""User-scoped managed file storage for local disk, Tencent COS and Aliyun OSS."""
import hashlib
import io
import ipaddress
import logging
import os
import socket
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable, Tuple
from urllib.parse import urlparse

import oss2
from fastapi import UploadFile
from qcloud_cos import CosConfig, CosS3Client
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.entities.file import File
from app.core.entities.storage_config import AliyunOssProviderConfig, QcloudCosProviderConfig, StorageConfig
from app.extensions.file_storage import FileStorage
from app.repositories.uow import IUnitOfWork
from app.schemas.exceptions import BadRequestError, NotFoundError
from app.services.user_config_service import UserConfigService

logger = logging.getLogger(__name__)


def _validate_public_https_endpoint(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise BadRequestError("OSS Endpoint 必须是有效的 HTTPS 地址")
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise BadRequestError("OSS Endpoint 不允许指向本机地址")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BadRequestError("OSS Endpoint 无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise BadRequestError("OSS Endpoint 不允许指向内网地址")


class LocalStorageDriver:
    provider = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise BadRequestError("非法的文件存储路径") from exc
        return target

    def put(self, key: str, body: BinaryIO) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while chunk := body.read(1024 * 1024):
                output.write(chunk)

    def get(self, key: str, legacy_filepath: str = "") -> BinaryIO:
        target = Path(legacy_filepath) if legacy_filepath and Path(legacy_filepath).is_file() else self._path(key)
        if not target.is_file():
            raise NotFoundError("文件内容不存在")
        return target.open("rb")

    def delete(self, key: str, legacy_filepath: str = "") -> None:
        target = Path(legacy_filepath) if legacy_filepath and Path(legacy_filepath).is_file() else self._path(key)
        if target.is_file():
            target.unlink()

    def test(self) -> None:
        key = f".storage-test/{uuid.uuid4()}.txt"
        self.put(key, io.BytesIO(b"agentic-storage-test"))
        self.delete(key)


class QcloudCosStorageDriver:
    provider = "qcloud_cos"

    def __init__(self, config: QcloudCosProviderConfig) -> None:
        if not all((config.bucket, config.region, config.secret_id, config.secret_key)):
            raise BadRequestError("腾讯 COS 配置不完整")
        self.bucket = config.bucket
        self.client = CosS3Client(CosConfig(Region=config.region, SecretId=config.secret_id, SecretKey=config.secret_key, Scheme=config.scheme))

    def put(self, key: str, body: BinaryIO) -> None:
        self.client.put_object(Bucket=self.bucket, Body=body, Key=key)

    def get(self, key: str, legacy_filepath: str = "") -> BinaryIO:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def delete(self, key: str, legacy_filepath: str = "") -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def test(self) -> None:
        key = f".storage-test/{uuid.uuid4()}.txt"
        self.put(key, io.BytesIO(b"agentic-storage-test"))
        self.delete(key)


class AliyunOssStorageDriver:
    provider = "aliyun_oss"

    def __init__(self, config: AliyunOssProviderConfig) -> None:
        if not all((config.bucket, config.endpoint, config.access_key_id, config.access_key_secret)):
            raise BadRequestError("阿里云 OSS 配置不完整")
        _validate_public_https_endpoint(config.endpoint)
        auth = oss2.Auth(config.access_key_id, config.access_key_secret)
        self.bucket = oss2.Bucket(auth, config.endpoint, config.bucket, region=config.region or None)

    def put(self, key: str, body: BinaryIO) -> None:
        self.bucket.put_object(key, body)

    def get(self, key: str, legacy_filepath: str = "") -> BinaryIO:
        return self.bucket.get_object(key)

    def delete(self, key: str, legacy_filepath: str = "") -> None:
        self.bucket.delete_object(key)

    def test(self) -> None:
        key = f".storage-test/{uuid.uuid4()}.txt"
        self.put(key, io.BytesIO(b"agentic-storage-test"))
        self.delete(key)


class ManagedFileStorage(FileStorage):
    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory
        self._config_service = UserConfigService(uow_factory)
        self._settings = get_settings()

    async def _read_upload(self, upload_file: UploadFile) -> tuple[io.BytesIO, int, str]:
        max_size = self._settings.max_upload_size_mb * 1024 * 1024
        buffer = io.BytesIO()
        digest = hashlib.sha256()
        size = 0
        while chunk := await upload_file.read(1024 * 1024):
            size += len(chunk)
            if size > max_size:
                raise BadRequestError(f"单个文件不能超过 {self._settings.max_upload_size_mb} MB")
            digest.update(chunk)
            buffer.write(chunk)
        buffer.seek(0)
        return buffer, size, digest.hexdigest()

    @staticmethod
    def _snapshot(config: StorageConfig, provider: str) -> dict:
        provider_config = getattr(config.providers, provider).model_dump(mode="json")
        for key in ("secret_id", "secret_key", "access_key_id", "access_key_secret", "enabled"):
            provider_config.pop(key, None)
        return provider_config

    def _driver(self, config: StorageConfig, provider: str, snapshot: dict | None = None):
        if provider == "local":
            return LocalStorageDriver(self._settings.local_storage_path)
        current = getattr(config.providers, provider).model_dump(mode="json")
        if snapshot:
            current.update({key: value for key, value in snapshot.items() if value not in (None, "")})
        if provider == "qcloud_cos":
            return QcloudCosStorageDriver(QcloudCosProviderConfig.model_validate(current))
        if provider == "aliyun_oss":
            return AliyunOssStorageDriver(AliyunOssProviderConfig.model_validate(current))
        raise BadRequestError("不支持的存储 Provider")

    def _legacy_filepath(self, file: File) -> str:
        """Resolve pre-migration local objects without weakening path validation for new keys."""
        if file.filepath and Path(file.filepath).is_file():
            return file.filepath
        if (
            file.storage_provider == "local"
            and not file.storage_config
            and not file.key.replace("\\", "/").startswith(f"{file.user_id}/")
        ):
            return str(Path(self._settings.local_storage_path) / file.user_id / file.key)
        return file.filepath

    async def upload_file(self, upload_file: UploadFile, user_id: str, *, source_type: str = "user_upload", parent_id: str | None = None, origin_session_id: str | None = None, origin_run_id: str | None = None, metadata: dict | None = None) -> File:
        config = await self._config_service.get_storage_config(user_id, redact=False)
        assert isinstance(config, StorageConfig)
        provider = config.default_provider
        if not getattr(config.providers, provider).enabled:
            raise BadRequestError("默认存储 Provider 未启用")
        content, size, sha256 = await self._read_upload(upload_file)
        file_id = str(uuid.uuid4())
        filename = os.path.basename(upload_file.filename or f"{file_id}.bin")
        extension = Path(filename).suffix.lstrip(".").lower()
        date_path = datetime.now().strftime("%Y/%m/%d")
        prefix = config.providers.aliyun_oss.path_prefix if provider == "aliyun_oss" else ""
        key = "/".join(part for part in (prefix, user_id, date_path, f"{file_id}{'.' + extension if extension else ''}") if part)
        driver = self._driver(config, provider)
        await run_in_threadpool(driver.put, key, content)
        file = File(id=file_id, user_id=user_id, filename=filename, key=key, extension=extension, mime_type=upload_file.content_type or "application/octet-stream", size=size, parent_id=parent_id, storage_provider=provider, storage_config=self._snapshot(config, provider), source_type=source_type, sha256=sha256, origin_session_id=origin_session_id, origin_run_id=origin_run_id, metadata=metadata or {})
        try:
            uow = self._uow_factory()
            async with uow:
                await uow.file.save(file)
        except Exception:
            try:
                await run_in_threadpool(driver.delete, key)
            except Exception:
                logger.exception("Failed to remove orphaned object %s", key)
            raise
        return file

    async def download_file(self, file_id: str, user_id: str | None = None) -> Tuple[BinaryIO, File]:
        uow = self._uow_factory()
        async with uow:
            file = await (uow.file.get_by_id_for_user(file_id, user_id) if user_id else uow.file.get_by_id(file_id))
        if not file or file.status != "available" or file.entry_type != "file":
            raise NotFoundError("文件不存在")
        config = await self._config_service.get_storage_config(file.user_id, redact=False)
        assert isinstance(config, StorageConfig)
        driver = self._driver(config, file.storage_provider, file.storage_config)
        return await run_in_threadpool(driver.get, file.key, self._legacy_filepath(file)), file

    async def delete_object(self, file: File) -> None:
        if file.entry_type != "file" or not file.key:
            return
        config = await self._config_service.get_storage_config(file.user_id, redact=False)
        assert isinstance(config, StorageConfig)
        driver = self._driver(config, file.storage_provider, file.storage_config)
        await run_in_threadpool(driver.delete, file.key, self._legacy_filepath(file))

    async def test_provider(self, user_id: str, provider: str, config: StorageConfig | None = None) -> None:
        runtime_config = config or await self._config_service.get_storage_config(user_id, redact=False)
        assert isinstance(runtime_config, StorageConfig)
        await run_in_threadpool(self._driver(runtime_config, provider).test)

    async def purge_expired(self, limit: int = 100) -> int:
        uow = self._uow_factory()
        async with uow:
            expired = await uow.file.list_expired(datetime.now(), limit)
        purged = 0
        for file in expired:
            try:
                await self.delete_object(file)
                uow = self._uow_factory()
                async with uow:
                    await uow.file.hard_delete(file.id)
                purged += 1
            except Exception:
                logger.exception("Failed to purge deleted file %s", file.id)
        return purged
