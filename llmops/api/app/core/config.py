from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEFAULT_REDIS_PASSWORD = "llmops123456"
_DEFAULT_REDIS_URL = f"redis://:{_DEFAULT_REDIS_PASSWORD}@localhost:6379/0"
_DEFAULT_CELERY_URL = f"redis://:{_DEFAULT_REDIS_PASSWORD}@localhost:6379/1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "LLMOps API"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = ""
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        validation_alias=AliasChoices("CORS_ALLOW_ORIGINS", "cors_allow_origins"),
    )
    service_api_prefix: str = ""
    service_ip: str = ""

    database_url: str = Field(
        default="postgresql+psycopg://postgres:llmops123456@127.0.0.1:5432/llmops?connect_timeout=5",
        validation_alias=AliasChoices("DATABASE_URL", "SQLALCHEMY_DATABASE_URI"),
    )
    database_echo: bool = Field(default=False, validation_alias=AliasChoices("DATABASE_ECHO", "SQLALCHEMY_ECHO"))
    database_pool_size: int = Field(
        default=20,
        validation_alias=AliasChoices("DATABASE_POOL_SIZE", "SQLALCHEMY_POOL_SIZE"),
    )
    database_max_overflow: int = 20
    database_pool_recycle: int = Field(
        default=3600,
        validation_alias=AliasChoices("DATABASE_POOL_RECYCLE", "SQLALCHEMY_POOL_RECYCLE"),
    )

    redis_url: str = _DEFAULT_REDIS_URL
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_username: str = ""
    redis_password: str = _DEFAULT_REDIS_PASSWORD
    redis_db: int = 0
    redis_use_ssl: bool = False

    celery_broker_url: str = _DEFAULT_CELERY_URL
    celery_result_backend: str = _DEFAULT_CELERY_URL
    celery_broker_db: int = 1
    celery_result_backend_db: int = 1
    celery_task_ignore_result: bool = False
    celery_result_expires: int = 3600
    celery_broker_connection_retry_on_startup: bool = True

    jwt_secret_key: str = "dev-jwt-secret-change-me-please-update"
    access_token_expire_minutes: int = 60 * 24 * 7
    default_tenant_id: str | None = None
    assistant_agent_id: str = "6774fcef-b594-8008-b30c-a05b8190afe6"

    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = ""

    file_storage_type: Literal["local", "cos"] = "local"
    local_storage_root: str = "storage/uploads"
    local_storage_base_url: str = "http://localhost:3000/upload-files"
    cos_domain: str = ""
    cos_bucket: str = ""
    cos_scheme: Literal["http", "https"] = "https"
    cos_region: str = ""
    cos_secret_id: str = ""
    cos_secret_key: str = ""

    weaviate_enabled: bool = True
    weaviate_http_scheme: Literal["http", "https"] = "http"
    weaviate_http_host: str = "localhost"
    weaviate_http_port: int = 8080
    weaviate_grpc_host: str = "localhost"
    weaviate_grpc_port: int = 50051
    weaviate_api_key: str = ""
    weaviate_collection_name: str = "Dataset"
    weaviate_timeout: float = 10.0

    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o-mini"
    default_llm_temperature: float = 0.5
    default_llm_top_p: float = 0.85
    default_llm_frequency_penalty: float = 0.2
    default_llm_presence_penalty: float = 0.2
    default_llm_max_tokens: int = 8192

    embedding_provider: Literal["hash", "openai"] = Field(
        default="hash",
        validation_alias=AliasChoices("EMBEDDING_PROVIDER", "VECTOR_EMBEDDING_PROVIDER"),
    )
    embedding_dimension: int = 256
    openai_api_key: str = ""
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "OPENAI_API_BASE"),
    )
    openai_embedding_model: str = "text-embedding-3-small"
    openai_audio_transcription_model: str = "whisper-1"
    openai_tts_model: str = "tts-1"
    deepseek_api_key: str = ""
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "DEEPSEEK_API_BASE"),
    )
    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ollama_base_url: str = "http://localhost:11434/v1"
    gaode_api_key: str = ""
    serper_api_key: str = ""

    @field_validator("database_url")
    @classmethod
    def normalize_postgres_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def build_legacy_redis_urls(self) -> "Settings":
        redis_url = self._redis_url(self.redis_db)
        if self.redis_url == _DEFAULT_REDIS_URL:
            self.redis_url = redis_url
        if self.celery_broker_url == _DEFAULT_CELERY_URL:
            self.celery_broker_url = self._redis_url(self.celery_broker_db)
        if self.celery_result_backend == _DEFAULT_CELERY_URL:
            self.celery_result_backend = self._redis_url(self.celery_result_backend_db)
        return self

    @property
    def default_model_config(self) -> dict[str, Any]:
        return {
            "provider": self.default_llm_provider,
            "model": self.default_llm_model,
            "parameters": {
                "temperature": self.default_llm_temperature,
                "top_p": self.default_llm_top_p,
                "frequency_penalty": self.default_llm_frequency_penalty,
                "presence_penalty": self.default_llm_presence_penalty,
                "max_tokens": self.default_llm_max_tokens,
            },
        }

    @property
    def default_app_config(self) -> dict[str, Any]:
        return {
            "model_config": self.default_model_config,
            "dialog_round": 3,
            "preset_prompt": "",
            "tools": [],
            "workflows": [],
            "datasets": [],
            "retrieval_config": {
                "retrieval_strategy": "semantic",
                "k": 10,
                "score": 0.5,
            },
            "long_term_memory": {"enable": False},
            "opening_statement": "",
            "opening_questions": [],
            "speech_to_text": {"enable": False},
            "text_to_speech": {
                "enable": False,
                "voice": "echo",
                "auto_play": False,
            },
            "suggested_after_answer": {"enable": True},
            "review_config": {
                "enable": False,
                "keywords": [],
                "inputs_config": {
                    "enable": False,
                    "preset_response": "",
                },
                "outputs_config": {"enable": False},
            },
        }

    def provider_api_key(self, env_name: str | None) -> str:
        if not env_name:
            return ""
        return str(
            {
                "OPENAI_API_KEY": self.openai_api_key,
                "DEEPSEEK_API_KEY": self.deepseek_api_key,
                "MOONSHOT_API_KEY": self.moonshot_api_key,
                "DASHSCOPE_API_KEY": self.dashscope_api_key,
                "GAODE_API_KEY": self.gaode_api_key,
                "SERPER_API_KEY": self.serper_api_key,
            }.get(env_name, "")
        )

    def provider_base_url(self, env_name: str, default: str) -> str:
        return str(
            {
                "OPENAI_BASE_URL": self.openai_base_url,
                "OPENAI_API_BASE": self.openai_base_url,
                "DEEPSEEK_BASE_URL": self.deepseek_base_url,
                "DEEPSEEK_API_BASE": self.deepseek_base_url,
                "MOONSHOT_BASE_URL": self.moonshot_base_url,
                "DASHSCOPE_BASE_URL": self.dashscope_base_url,
                "OLLAMA_BASE_URL": self.ollama_base_url,
            }.get(env_name, default)
        )

    def _redis_url(self, db: int) -> str:
        scheme = "rediss" if self.redis_use_ssl else "redis"
        auth = ""
        if self.redis_username and self.redis_password:
            auth = f"{self.redis_username}:{self.redis_password}@"
        elif self.redis_password:
            auth = f":{self.redis_password}@"
        elif self.redis_username:
            auth = f"{self.redis_username}@"
        return f"{scheme}://{auth}{self.redis_host}:{self.redis_port}/{int(db)}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
