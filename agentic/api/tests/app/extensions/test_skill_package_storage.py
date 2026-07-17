import asyncio
import hashlib
import io
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.entities.storage_config import StorageConfig
from app.core.skills.package import SkillPackageError
from app.extensions.skill_package_storage import SkillPackageStorage
from app.extensions.storage_drivers import provider_snapshot
from app.schemas.exceptions import BadRequestError, NotFoundError


class StaticStorageConfigService:
    def __init__(self, config: StorageConfig) -> None:
        self.config = config
        self.requested_users: list[str] = []

    async def get_storage_config(
        self, user_id: str, *, redact: bool = True
    ) -> StorageConfig:
        assert redact is False
        self.requested_users.append(user_id)
        return self.config


def local_config() -> StorageConfig:
    return StorageConfig.model_validate(
        {
            "default_provider": "local",
            "providers": {"local": {"enabled": True}},
        }
    )


def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        skill_package_storage_path=str(tmp_path / "packages"),
        skill_workspace_storage_path=str(tmp_path / "workspaces"),
        marketplace_skill_storage_provider="local",
    )


def test_personal_package_round_trip_uses_user_provider_and_stable_key(
    tmp_path: Path,
) -> None:
    config_service = StaticStorageConfigService(local_config())
    storage = SkillPackageStorage(config_service, settings=settings(tmp_path))
    content = b"deterministic skill package"
    digest = hashlib.sha256(content).hexdigest()

    async def run() -> None:
        stored = await storage.upload_personal(
            user_id="user-1",
            skill_id="skill-1",
            version=2,
            body=io.BytesIO(content),
            expected_sha256=digest,
        )

        assert stored.storage_provider == "local"
        assert stored.storage_key == "personal/user-1/skill-1/2.skill"
        assert stored.storage_config == {}
        assert stored.package_sha256 == digest
        assert stored.package_size == len(content)
        assert config_service.requested_users == ["user-1"]
        assert (
            tmp_path / "packages/personal/user-1/skill-1/2.skill"
        ).read_bytes() == content

        stream = await storage.download_personal(
            user_id="user-1",
            storage_provider=stored.storage_provider,
            storage_key=stored.storage_key,
            storage_config=stored.storage_config,
            expected_sha256=stored.package_sha256,
        )
        assert stream.read() == content

    asyncio.run(run())


def test_delete_removes_package_and_missing_download_is_not_found(
    tmp_path: Path,
) -> None:
    storage = SkillPackageStorage(
        StaticStorageConfigService(local_config()), settings=settings(tmp_path)
    )
    content = b"package"
    digest = hashlib.sha256(content).hexdigest()

    async def run() -> None:
        stored = await storage.upload_personal(
            user_id="user-1",
            skill_id="skill-1",
            version=1,
            body=io.BytesIO(content),
            expected_sha256=digest,
        )
        await storage.delete_personal(
            user_id="user-1",
            storage_provider=stored.storage_provider,
            storage_key=stored.storage_key,
            storage_config=stored.storage_config,
        )

        with pytest.raises(NotFoundError):
            await storage.download_personal(
                user_id="user-1",
                storage_provider=stored.storage_provider,
                storage_key=stored.storage_key,
                storage_config=stored.storage_config,
                expected_sha256=stored.package_sha256,
            )

    asyncio.run(run())


def test_sha_mismatch_rejects_upload_and_tampered_download(tmp_path: Path) -> None:
    storage = SkillPackageStorage(
        StaticStorageConfigService(local_config()), settings=settings(tmp_path)
    )
    content = b"package"
    digest = hashlib.sha256(content).hexdigest()

    async def run() -> None:
        with pytest.raises(SkillPackageError) as upload_error:
            await storage.upload_personal(
                user_id="user-1",
                skill_id="skill-1",
                version=1,
                body=io.BytesIO(content),
                expected_sha256="0" * 64,
            )
        assert upload_error.value.code == "skill_package_integrity_error"
        assert not (tmp_path / "packages/personal/user-1/skill-1/1.skill").exists()

        stored = await storage.upload_personal(
            user_id="user-1",
            skill_id="skill-1",
            version=1,
            body=io.BytesIO(content),
            expected_sha256=digest,
        )
        (tmp_path / "packages" / stored.storage_key).write_bytes(b"tampered")
        with pytest.raises(SkillPackageError) as download_error:
            await storage.download_personal(
                user_id="user-1",
                storage_provider=stored.storage_provider,
                storage_key=stored.storage_key,
                storage_config=stored.storage_config,
                expected_sha256=digest,
            )
        assert download_error.value.code == "skill_package_integrity_error"

    asyncio.run(run())


def test_immutable_package_key_cannot_be_overwritten(tmp_path: Path) -> None:
    storage = SkillPackageStorage(
        StaticStorageConfigService(local_config()), settings=settings(tmp_path)
    )
    original = b"original package"
    replacement = b"replacement package"

    async def run() -> None:
        await storage.upload_personal(
            user_id="user-1",
            skill_id="skill-1",
            version=1,
            body=io.BytesIO(original),
            expected_sha256=hashlib.sha256(original).hexdigest(),
        )
        with pytest.raises(BadRequestError):
            await storage.upload_personal(
                user_id="user-1",
                skill_id="skill-1",
                version=1,
                body=io.BytesIO(replacement),
                expected_sha256=hashlib.sha256(replacement).hexdigest(),
            )
        assert (
            tmp_path / "packages/personal/user-1/skill-1/1.skill"
        ).read_bytes() == original

    asyncio.run(run())


def test_marketplace_package_uses_deployment_storage_without_user_lookup(
    tmp_path: Path,
) -> None:
    config_service = StaticStorageConfigService(local_config())
    storage = SkillPackageStorage(config_service, settings=settings(tmp_path))
    content = b"marketplace package"
    digest = hashlib.sha256(content).hexdigest()

    async def run() -> None:
        stored = await storage.upload_marketplace(
            skill_id="market-skill",
            version=3,
            body=io.BytesIO(content),
            expected_sha256=digest,
        )
        assert stored.storage_key == "marketplace/market-skill/3.skill"
        assert config_service.requested_users == []

        stream = await storage.download_marketplace(
            storage_provider=stored.storage_provider,
            storage_key=stored.storage_key,
            storage_config=stored.storage_config,
            expected_sha256=digest,
        )
        assert stream.read() == content

    asyncio.run(run())


def test_provider_snapshot_never_contains_secrets() -> None:
    config = StorageConfig.model_validate(
        {
            "default_provider": "qcloud_cos",
            "providers": {
                "qcloud_cos": {
                    "enabled": True,
                    "bucket": "skills",
                    "region": "ap-shanghai",
                    "domain": "https://cdn.example.com",
                    "secret_id": "secret-id",
                    "secret_key": "secret-key",
                }
            },
        }
    )

    snapshot = provider_snapshot(config, "qcloud_cos")

    assert snapshot == {
        "bucket": "skills",
        "region": "ap-shanghai",
        "domain": "https://cdn.example.com",
        "scheme": "https",
    }
    assert "secret" not in str(snapshot).lower()
