from app.core.config import Settings


def test_settings_maps_legacy_database_and_redis_env(monkeypatch) -> None:
    for key in [
        "DATABASE_URL",
        "REDIS_URL",
        "REDIS_USERNAME",
        "REDIS_USE_SSL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "postgresql://user:pass@db:5432/llmops")
    monkeypatch.setenv("SQLALCHEMY_POOL_SIZE", "33")
    monkeypatch.setenv("SQLALCHEMY_POOL_RECYCLE", "120")
    monkeypatch.setenv("REDIS_HOST", "redis")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_PASSWORD", "secret")
    monkeypatch.setenv("REDIS_DB", "2")
    monkeypatch.setenv("CELERY_BROKER_DB", "3")
    monkeypatch.setenv("CELERY_RESULT_BACKEND_DB", "4")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/llmops"
    assert settings.database_pool_size == 33
    assert settings.database_pool_recycle == 120
    assert settings.redis_url == "redis://:secret@redis:6380/2"
    assert settings.celery_broker_url == "redis://:secret@redis:6380/3"
    assert settings.celery_result_backend == "redis://:secret@redis:6380/4"


def test_settings_maps_legacy_service_provider_and_default_model_env(monkeypatch) -> None:
    for key in ["OPENAI_BASE_URL", "DEEPSEEK_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:3000, http://localhost:5173")
    monkeypatch.setenv("ASSISTANT_AGENT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("SERVICE_API_PREFIX", "https://api.example.test")
    monkeypatch.setenv("SERVICE_IP", "127.0.0.1")
    monkeypatch.setenv("LOCAL_STORAGE_BASE_URL", "https://static.example.test/files")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://openai-compatible.example.test/v1")
    monkeypatch.setenv("DEEPSEEK_API_BASE", "https://deepseek-compatible.example.test")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEFAULT_LLM_TEMPERATURE", "0.7")

    settings = Settings(_env_file=None)

    assert settings.cors_allow_origins == ["http://localhost:3000", "http://localhost:5173"]
    assert settings.assistant_agent_id == "11111111-1111-1111-1111-111111111111"
    assert settings.service_api_prefix == "https://api.example.test"
    assert settings.service_ip == "127.0.0.1"
    assert settings.local_storage_base_url == "https://static.example.test/files"
    assert settings.provider_api_key("OPENAI_API_KEY") == "openai-key"
    assert settings.provider_base_url("OPENAI_BASE_URL", "") == "https://openai-compatible.example.test/v1"
    assert settings.provider_base_url("DEEPSEEK_BASE_URL", "") == "https://deepseek-compatible.example.test"
    assert settings.default_model_config["provider"] == "deepseek"
    assert settings.default_model_config["model"] == "deepseek-chat"
    assert settings.default_model_config["parameters"]["temperature"] == 0.7
