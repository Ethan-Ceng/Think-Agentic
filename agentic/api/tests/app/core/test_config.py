from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _overlaps(left: str, right: str) -> bool:
    left_path = Path(left).resolve(strict=False)
    right_path = Path(right).resolve(strict=False)
    return (
        left_path == right_path
        or left_path in right_path.parents
        or right_path in left_path.parents
    )


def test_default_local_skill_storage_is_separate_from_managed_files() -> None:
    settings = Settings(_env_file=None)

    assert settings.local_storage_path == "/app/storage/files"
    assert settings.skill_package_storage_path == "/app/storage/skills/packages"
    assert settings.skill_workspace_storage_path == "/app/storage/skill-workspaces"
    assert not _overlaps(
        settings.local_storage_path, settings.skill_package_storage_path
    )
    assert not _overlaps(
        settings.local_storage_path, settings.skill_workspace_storage_path
    )
    assert not _overlaps(
        settings.skill_package_storage_path,
        settings.skill_workspace_storage_path,
    )


@pytest.mark.parametrize(
    ("ordinary_root", "package_root", "workspace_root"),
    [
        ("/data/shared", "/data/shared/skills", "/data/skill-workspaces"),
        ("/data/files", "/data/skills", "/data/files/drafts"),
        ("/data/files", "/data/skills", "/data/skills/packages"),
    ],
)
def test_settings_reject_overlapping_file_and_skill_storage_roots(
    ordinary_root: str,
    package_root: str,
    workspace_root: str,
) -> None:
    with pytest.raises(ValidationError, match="storage roots must not overlap"):
        Settings(
            _env_file=None,
            local_storage_path=ordinary_root,
            skill_package_storage_path=package_root,
            skill_workspace_storage_path=workspace_root,
        )
