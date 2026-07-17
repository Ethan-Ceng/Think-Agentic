"""Reusable byte-object storage drivers for local disk, COS and OSS."""

import io
import ipaddress
import socket
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.parse import urlparse

import oss2
from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosServiceError

from app.core.entities.storage_config import (
    AliyunOssProviderConfig,
    QcloudCosProviderConfig,
    StorageConfig,
    StorageProvider,
)
from app.schemas.exceptions import BadRequestError, NotFoundError


class StorageDriver(Protocol):
    provider: StorageProvider

    def put(self, key: str, body: BinaryIO) -> None: ...

    def get(self, key: str, legacy_filepath: str = "") -> BinaryIO: ...

    def delete(self, key: str, legacy_filepath: str = "") -> None: ...

    def exists(self, key: str) -> bool: ...

    def test(self) -> None: ...


def validate_public_https_endpoint(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise BadRequestError("OSS Endpoint 必须是有效的 HTTPS 地址")
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise BadRequestError("OSS Endpoint 不允许指向本机地址")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise BadRequestError("OSS Endpoint 无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise BadRequestError("OSS Endpoint 不允许指向内网地址")


class LocalStorageDriver:
    provider: StorageProvider = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        if not key or "\\" in key:
            raise BadRequestError("非法的文件存储路径")
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
        target = (
            Path(legacy_filepath)
            if legacy_filepath and Path(legacy_filepath).is_file()
            else self._path(key)
        )
        if not target.is_file():
            raise NotFoundError("文件内容不存在")
        return target.open("rb")

    def delete(self, key: str, legacy_filepath: str = "") -> None:
        target = (
            Path(legacy_filepath)
            if legacy_filepath and Path(legacy_filepath).is_file()
            else self._path(key)
        )
        if target.is_file():
            target.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def test(self) -> None:
        key = f".storage-test/{uuid.uuid4()}.txt"
        self.put(key, io.BytesIO(b"agentic-storage-test"))
        self.delete(key)


class QcloudCosStorageDriver:
    provider: StorageProvider = "qcloud_cos"

    def __init__(self, config: QcloudCosProviderConfig) -> None:
        if not all(
            (config.bucket, config.region, config.secret_id, config.secret_key)
        ):
            raise BadRequestError("腾讯 COS 配置不完整")
        self.bucket = config.bucket
        self.client = CosS3Client(
            CosConfig(
                Region=config.region,
                SecretId=config.secret_id,
                SecretKey=config.secret_key,
                Scheme=config.scheme,
            )
        )

    def put(self, key: str, body: BinaryIO) -> None:
        self.client.put_object(Bucket=self.bucket, Body=body, Key=key)

    def get(self, key: str, legacy_filepath: str = "") -> BinaryIO:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def delete(self, key: str, legacy_filepath: str = "") -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except CosServiceError as exc:
            if exc.get_status_code() == 404:
                return False
            raise

    def test(self) -> None:
        key = f".storage-test/{uuid.uuid4()}.txt"
        self.put(key, io.BytesIO(b"agentic-storage-test"))
        self.delete(key)


class AliyunOssStorageDriver:
    provider: StorageProvider = "aliyun_oss"

    def __init__(self, config: AliyunOssProviderConfig) -> None:
        if not all(
            (
                config.bucket,
                config.endpoint,
                config.access_key_id,
                config.access_key_secret,
            )
        ):
            raise BadRequestError("阿里云 OSS 配置不完整")
        validate_public_https_endpoint(config.endpoint)
        auth = oss2.Auth(config.access_key_id, config.access_key_secret)
        self.bucket = oss2.Bucket(
            auth,
            config.endpoint,
            config.bucket,
            region=config.region or None,
        )

    def put(self, key: str, body: BinaryIO) -> None:
        self.bucket.put_object(key, body)

    def get(self, key: str, legacy_filepath: str = "") -> BinaryIO:
        return self.bucket.get_object(key)

    def delete(self, key: str, legacy_filepath: str = "") -> None:
        self.bucket.delete_object(key)

    def exists(self, key: str) -> bool:
        return self.bucket.object_exists(key)

    def test(self) -> None:
        key = f".storage-test/{uuid.uuid4()}.txt"
        self.put(key, io.BytesIO(b"agentic-storage-test"))
        self.delete(key)


def provider_snapshot(config: StorageConfig, provider: StorageProvider) -> dict:
    provider_config = getattr(config.providers, provider).model_dump(mode="json")
    for key in (
        "secret_id",
        "secret_key",
        "access_key_id",
        "access_key_secret",
        "enabled",
    ):
        provider_config.pop(key, None)
    return provider_config


def create_storage_driver(
    config: StorageConfig,
    provider: StorageProvider,
    *,
    local_root: str | Path,
    snapshot: dict | None = None,
) -> StorageDriver:
    if provider == "local":
        return LocalStorageDriver(local_root)
    current = getattr(config.providers, provider).model_dump(mode="json")
    if snapshot:
        current.update(
            {key: value for key, value in snapshot.items() if value not in (None, "")}
        )
    if provider == "qcloud_cos":
        return QcloudCosStorageDriver(
            QcloudCosProviderConfig.model_validate(current)
        )
    if provider == "aliyun_oss":
        return AliyunOssStorageDriver(
            AliyunOssProviderConfig.model_validate(current)
        )
    raise BadRequestError("不支持的存储 Provider")
