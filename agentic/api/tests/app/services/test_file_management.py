import asyncio
import io

from fastapi import UploadFile

from app.core.entities.config import Config
from app.core.entities.file import File
from app.extensions.managed_file_storage import ManagedFileStorage
from app.services.user_config_service import UserConfigService


class FakeConfigRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], Config] = {}

    async def get_by_user_and_type(self, user_id: str, config_type: str):
        return self.items.get((user_id, config_type))

    async def save(self, config: Config) -> None:
        self.items[(config.user_id, config.config_type)] = config


class FakeFileRepository:
    def __init__(self) -> None:
        self.items: dict[str, File] = {}

    async def save(self, file: File) -> None:
        self.items[file.id] = file.model_copy(deep=True)

    async def get_by_id(self, file_id: str):
        return self.items.get(file_id)

    async def get_by_id_for_user(self, file_id: str, user_id: str):
        file = self.items.get(file_id)
        return file if file and file.user_id == user_id else None


class FakeUow:
    def __init__(self, config: FakeConfigRepository, file: FakeFileRepository) -> None:
        self.config = config
        self.file = file

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def test_storage_config_encrypts_and_masks_credentials() -> None:
    configs = FakeConfigRepository()
    files = FakeFileRepository()
    service = UserConfigService(lambda: FakeUow(configs, files))

    async def run() -> None:
        updated = await service.update_storage_config(
            "user-1",
            {
                "default_provider": "local",
                "providers": {
                    "local": {"enabled": True},
                    "qcloud_cos": {"enabled": False},
                    "aliyun_oss": {
                        "enabled": True,
                        "bucket": "agentic-test",
                        "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
                        "access_key_id": "access-id",
                        "access_key_secret": "access-secret",
                    },
                },
            },
        )
        stored = configs.items[("user-1", "storage")].config
        assert stored["providers"]["aliyun_oss"]["access_key_id"].startswith("enc:")
        assert stored["providers"]["aliyun_oss"]["access_key_secret"].startswith("enc:")
        assert "access-secret" not in str(stored)
        assert updated["providers"]["aliyun_oss"]["access_key_id"] == "******"

        runtime = await service.get_storage_config("user-1", redact=False)
        assert runtime.providers.aliyun_oss.access_key_secret == "access-secret"

    asyncio.run(run())


def test_agent_generated_file_uses_default_provider_and_tracks_origin(tmp_path) -> None:
    configs = FakeConfigRepository()
    files = FakeFileRepository()
    storage = ManagedFileStorage(lambda: FakeUow(configs, files))
    storage._settings.local_storage_path = str(tmp_path)

    async def run() -> None:
        file = await storage.upload_file(
            UploadFile(filename="report.txt", file=io.BytesIO(b"final report")),
            "user-1",
            source_type="agent_generated",
            origin_session_id="session-1",
            origin_run_id="run-1",
        )
        assert file.source_type == "agent_generated"
        assert file.storage_provider == "local"
        assert file.origin_session_id == "session-1"
        assert file.origin_run_id == "run-1"
        assert file.sha256

        stream, downloaded = await storage.download_file(file.id, "user-1")
        assert stream.read() == b"final report"
        assert downloaded.id == file.id

    asyncio.run(run())


def test_pre_migration_local_file_resolves_user_directory(tmp_path) -> None:
    configs = FakeConfigRepository()
    files = FakeFileRepository()
    storage = ManagedFileStorage(lambda: FakeUow(configs, files))
    storage._settings.local_storage_path = str(tmp_path)
    legacy_path = tmp_path / "user-1" / "legacy-key.txt"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_bytes(b"legacy content")
    files.items["legacy-file"] = File(
        id="legacy-file",
        user_id="user-1",
        filename="legacy.txt",
        key="legacy-key.txt",
        extension="txt",
        storage_provider="local",
        storage_config={},
    )

    async def run() -> None:
        stream, _ = await storage.download_file("legacy-file", "user-1")
        assert stream.read() == b"legacy content"

    asyncio.run(run())
