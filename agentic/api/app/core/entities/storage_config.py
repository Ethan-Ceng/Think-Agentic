from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


StorageProvider = Literal["local", "qcloud_cos", "aliyun_oss"]


class LocalStorageProviderConfig(BaseModel):
    enabled: bool = True


class QcloudCosProviderConfig(BaseModel):
    enabled: bool = False
    bucket: str = ""
    region: str = ""
    domain: str = ""
    scheme: Literal["http", "https"] = "https"
    secret_id: str = ""
    secret_key: str = ""


class AliyunOssProviderConfig(BaseModel):
    enabled: bool = False
    bucket: str = ""
    endpoint: str = ""
    region: str = ""
    domain: str = ""
    path_prefix: str = ""
    access_key_id: str = ""
    access_key_secret: str = ""

    @field_validator("endpoint", "domain")
    @classmethod
    def require_https_when_set(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and not value.lower().startswith("https://"):
            raise ValueError("OSS Endpoint 和 Domain 必须使用 HTTPS")
        return value

    @field_validator("path_prefix")
    @classmethod
    def normalize_path_prefix(cls, value: str) -> str:
        return value.strip().strip("/")


class StorageProvidersConfig(BaseModel):
    local: LocalStorageProviderConfig = Field(default_factory=LocalStorageProviderConfig)
    qcloud_cos: QcloudCosProviderConfig = Field(default_factory=QcloudCosProviderConfig)
    aliyun_oss: AliyunOssProviderConfig = Field(default_factory=AliyunOssProviderConfig)


class StorageConfig(BaseModel):
    default_provider: StorageProvider = "local"
    providers: StorageProvidersConfig = Field(default_factory=StorageProvidersConfig)

    @model_validator(mode="after")
    def validate_default_provider(self) -> "StorageConfig":
        provider = getattr(self.providers, self.default_provider)
        if not provider.enabled:
            raise ValueError("默认存储 Provider 必须处于启用状态")
        return self

