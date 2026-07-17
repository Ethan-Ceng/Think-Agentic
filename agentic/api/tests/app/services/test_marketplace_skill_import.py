import hashlib
from pathlib import Path

import pytest

from app.core.entities.skill import Skill, SkillScope, SkillVersion
from app.core.skills.package import SkillPackageError, SkillPackageService
from app.extensions.skill_package_storage import StoredSkillPackage
from app.schemas.exceptions import ConflictError
from app.services.marketplace_skill_service import MarketplaceSkillService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Repository:
    def __init__(self) -> None:
        self.skills: list[Skill] = []
        self.versions: list[SkillVersion] = []
        self.fail_update = False

    async def list_marketplace(self):
        return list(self.skills)

    async def list_marketplace_versions(self, skill_id: str):
        return [version for version in self.versions if version.skill_id == skill_id]

    async def save_skill(self, skill: Skill):
        self.skills.append(skill)

    async def save_version(self, version: SkillVersion):
        self.versions.append(version)

    async def update_marketplace(self, skill_id: str, **changes):
        if self.fail_update:
            raise RuntimeError("database unavailable")
        for index, skill in enumerate(self.skills):
            if skill.id == skill_id:
                self.skills[index] = skill.model_copy(
                    update={key: value for key, value in changes.items() if value is not None}
                )
                return True
        return False


class Uow:
    def __init__(self, repository: Repository) -> None:
        self.skill = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class Storage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_upload = False

    async def upload_marketplace(
        self, *, skill_id: str, version: int, body, expected_sha256: str
    ):
        if self.fail_upload:
            raise RuntimeError("deployment storage unavailable")
        data = body.read()
        assert hashlib.sha256(data).hexdigest() == expected_sha256
        key = f"marketplace/{skill_id}/{version}.skill"
        if key in self.objects:
            raise RuntimeError("immutable object already exists")
        self.objects[key] = data
        return StoredSkillPackage(
            storage_provider="local",
            storage_key=key,
            storage_config={"provider": "local"},
            package_sha256=expected_sha256,
            package_size=len(data),
        )

    async def delete_marketplace(self, *, storage_key: str, **kwargs):
        self.deleted.append(storage_key)
        self.objects.pop(storage_key, None)


def write_skill(root: Path, body: str = "Follow version one.") -> Path:
    skill = root / "market-research"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: market-research\n"
        "description: Research a market using reliable sources.\n"
        "---\n\n"
        "# Market Research\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return skill


def service(repository: Repository, storage: Storage) -> MarketplaceSkillService:
    return MarketplaceSkillService(
        uow_factory=lambda: Uow(repository),
        package_service=SkillPackageService(),
        package_storage=storage,
    )


async def test_valid_import_is_immutable_and_returns_safe_structured_output(
    tmp_path: Path,
) -> None:
    repository = Repository()
    storage = Storage()
    imported = await service(repository, storage).import_package(
        write_skill(tmp_path), display_name="Market Research", changelog="Initial"
    )

    assert imported.skill.scope is SkillScope.MARKETPLACE
    assert imported.skill.owner_user_id is None
    assert imported.skill.current_version_id == imported.version.id
    assert imported.version.version == 1
    assert imported.version.created_by_user_id is None
    assert storage.objects[imported.version.storage_key]
    output = imported.structured_output()
    assert set(output) == {
        "skill_id",
        "version_id",
        "version",
        "hash",
        "storage_provider",
        "idempotent",
    }
    assert "config" not in output


async def test_idempotent_reimport_returns_existing_version(tmp_path: Path) -> None:
    repository = Repository()
    storage = Storage()
    market = service(repository, storage)
    source = write_skill(tmp_path)
    first = await market.import_package(source)
    second = await market.import_package(source)

    assert second.idempotent is True
    assert second.version.id == first.version.id
    assert len(repository.versions) == 1
    assert len(storage.objects) == 1


async def test_changed_bytes_create_next_version_but_cannot_replace_one(
    tmp_path: Path,
) -> None:
    repository = Repository()
    storage = Storage()
    market = service(repository, storage)
    source = write_skill(tmp_path)
    first = await market.import_package(source)
    (source / "SKILL.md").write_text(
        (source / "SKILL.md").read_text(encoding="utf-8").replace(
            "Follow version one.", "Follow version two."
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConflictError) as exc_info:
        await market.import_package(source, expected_version=1)
    assert "different package bytes" in exc_info.value.msg
    second = await market.import_package(source)
    assert second.version.version == 2
    assert second.version.package_sha256 != first.version.package_sha256
    assert repository.skills[0].current_version_id == second.version.id


async def test_rejects_invalid_package_and_global_market_name_conflict(
    tmp_path: Path,
) -> None:
    repository = Repository()
    storage = Storage()
    invalid = tmp_path / "invalid.skill"
    invalid.write_bytes(b"not a zip")
    with pytest.raises(SkillPackageError):
        await service(repository, storage).import_package(invalid)

    repository.skills.extend(
        [
            Skill(
                name="market-research",
                display_name=f"Duplicate {index}",
                description="Duplicate.",
                scope=SkillScope.MARKETPLACE,
            )
            for index in range(2)
        ]
    )
    with pytest.raises(ConflictError) as exc_info:
        await service(repository, storage).import_package(write_skill(tmp_path / "valid"))
    assert "Duplicate Marketplace Skill name" in exc_info.value.msg


async def test_storage_or_database_failure_never_commits_a_visible_version(
    tmp_path: Path,
) -> None:
    source = write_skill(tmp_path)
    repository = Repository()
    storage = Storage()
    storage.fail_upload = True
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await service(repository, storage).import_package(source)
    assert repository.skills == []
    assert repository.versions == []

    storage.fail_upload = False
    repository.fail_update = True
    with pytest.raises(RuntimeError, match="database unavailable"):
        await service(repository, storage).import_package(source)
    assert storage.objects == {}
    assert storage.deleted
