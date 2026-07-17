import io
import os
import shutil
import stat
import zipfile
from pathlib import Path

import pytest

from app.core.skills.limits import SkillPackageLimits
from app.core.skills.package import SkillPackageError, SkillPackageService


FIXTURE_ROOT = (
    Path(__file__).parents[3] / "fixtures" / "skills" / "report-writer"
)
SKILL_MD = (FIXTURE_ROOT / "SKILL.md").read_bytes()


def archive_bytes(
    entries: list[tuple[str, bytes]],
    *,
    modes: dict[str, int] | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            mode = (modes or {}).get(name, stat.S_IFREG | 0o644)
            info.external_attr = mode << 16
            archive.writestr(info, content)
    return output.getvalue()


def valid_entries() -> list[tuple[str, bytes]]:
    return [
        ("report-writer/SKILL.md", SKILL_MD),
        ("report-writer/references/style.md", b"# Style\n\nBe concise.\n"),
    ]


def assert_error_code(
    service: SkillPackageService,
    archive: bytes,
    expected_code: str,
) -> None:
    with pytest.raises(SkillPackageError) as caught:
        service.inspect_archive(io.BytesIO(archive))
    assert caught.value.code == expected_code


def test_inspect_directory_uses_standard_manifest_and_file_inventory() -> None:
    inspected = SkillPackageService().inspect_directory(FIXTURE_ROOT)

    assert inspected.root_name == "report-writer"
    assert inspected.manifest.name == "report-writer"
    assert inspected.manifest.allowed_tools == "search_web read_file write_file"
    assert [entry.path for entry in inspected.files] == [
        "SKILL.md",
        "references/style.md",
    ]
    assert inspected.total_size == sum(entry.size for entry in inspected.files)
    assert len(inspected.content_sha256) == 64


def test_build_archive_is_reproducible_and_ignores_source_mtime(tmp_path: Path) -> None:
    source = tmp_path / "report-writer"
    shutil.copytree(FIXTURE_ROOT, source)
    service = SkillPackageService()
    first = io.BytesIO()
    first_result = service.build_archive(source, first)

    os.utime(source / "SKILL.md", (1_900_000_000, 1_900_000_000))
    second = io.BytesIO()
    second_result = service.build_archive(source, second)

    assert first.getvalue() == second.getvalue()
    assert first_result.archive_sha256 == second_result.archive_sha256
    assert first_result.archive_size == len(first.getvalue())
    with zipfile.ZipFile(io.BytesIO(first.getvalue())) as archive:
        assert archive.namelist() == [
            "report-writer/SKILL.md",
            "report-writer/references/style.md",
        ]
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())


def test_extract_archive_materializes_only_validated_skill(tmp_path: Path) -> None:
    service = SkillPackageService()
    archive = archive_bytes(valid_entries())
    destination = tmp_path / "skills"

    result = service.extract_archive(io.BytesIO(archive), destination)

    assert result.inspected.root_name == "report-writer"
    assert (destination / "report-writer" / "SKILL.md").read_bytes() == SKILL_MD
    assert (
        destination / "report-writer" / "references" / "style.md"
    ).read_text(encoding="utf-8").startswith("# Style")


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../report-writer/SKILL.md",
        "/report-writer/SKILL.md",
        "C:/report-writer/SKILL.md",
        "report-writer/../SKILL.md",
        "report-writer/./SKILL.md",
        "report-writer\\SKILL.md",
        "report-writer//SKILL.md",
    ],
)
def test_archive_rejects_unsafe_paths(unsafe_name: str) -> None:
    if "\\" in unsafe_name:
        archive = archive_bytes([("report-writer/SKILL.md", SKILL_MD)]).replace(
            b"report-writer/SKILL.md", b"report-writer\\SKILL.md"
        )
    else:
        archive = archive_bytes([(unsafe_name, SKILL_MD)])
    assert_error_code(
        SkillPackageService(),
        archive,
        "skill_unsafe_archive",
    )


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "report-writer/assets/CON",
        "report-writer/assets/com1.txt",
        "report-writer/assets/name\x00suffix",
    ],
)
def test_path_validator_rejects_windows_devices_and_null_bytes(
    unsafe_name: str,
) -> None:
    with pytest.raises(SkillPackageError) as caught:
        SkillPackageService()._validate_archive_path(unsafe_name)
    assert caught.value.code == "skill_unsafe_archive"


def test_archive_rejects_symbolic_links() -> None:
    entries = valid_entries() + [("report-writer/scripts/run.sh", b"target")]
    archive = archive_bytes(
        entries,
        modes={"report-writer/scripts/run.sh": stat.S_IFLNK | 0o777},
    )

    assert_error_code(SkillPackageService(), archive, "skill_unsafe_archive")


def test_archive_rejects_device_files() -> None:
    entries = valid_entries() + [("report-writer/assets/device", b"device")]
    archive = archive_bytes(
        entries,
        modes={"report-writer/assets/device": stat.S_IFCHR | 0o600},
    )

    assert_error_code(SkillPackageService(), archive, "skill_unsafe_archive")


def test_archive_rejects_casefold_duplicates() -> None:
    archive = archive_bytes(
        valid_entries() + [("report-writer/references/STYLE.md", b"duplicate")]
    )

    assert_error_code(SkillPackageService(), archive, "skill_unsafe_archive")


def test_archive_requires_one_root_and_exact_root_skill_md() -> None:
    multiple_roots = archive_bytes(
        valid_entries() + [("other-skill/SKILL.md", SKILL_MD)]
    )
    missing_manifest = archive_bytes(
        [("report-writer/references/style.md", b"# Style")]
    )

    assert_error_code(
        SkillPackageService(), multiple_roots, "skill_unsafe_archive"
    )
    assert_error_code(
        SkillPackageService(), missing_manifest, "skill_invalid_manifest"
    )


def test_archive_rejects_non_utf8_or_invalid_official_manifest() -> None:
    non_utf8 = archive_bytes(
        [("report-writer/SKILL.md", b"\xff\xfe\x00\x00")]
    )
    unexpected_field = SKILL_MD.replace(
        b"license: Apache-2.0",
        b"license: Apache-2.0\ndisplay_name: Report Writer",
    )
    invalid_manifest = archive_bytes(
        [("report-writer/SKILL.md", unexpected_field)]
    )

    assert_error_code(SkillPackageService(), non_utf8, "skill_invalid_manifest")
    assert_error_code(
        SkillPackageService(), invalid_manifest, "skill_invalid_manifest"
    )


def test_archive_reports_directory_and_manifest_name_mismatch() -> None:
    archive = archive_bytes([("wrong-name/SKILL.md", SKILL_MD)])

    assert_error_code(SkillPackageService(), archive, "skill_name_mismatch")


def test_archive_enforces_file_count_and_size_limits() -> None:
    file_count_service = SkillPackageService(
        SkillPackageLimits(file_count=1)
    )
    file_size_service = SkillPackageService(
        SkillPackageLimits(file_bytes=len(SKILL_MD) - 1)
    )
    extracted_size_service = SkillPackageService(
        SkillPackageLimits(extracted_bytes=len(SKILL_MD))
    )

    assert_error_code(
        file_count_service,
        archive_bytes(valid_entries()),
        "skill_package_too_large",
    )
    assert_error_code(
        file_size_service,
        archive_bytes([("report-writer/SKILL.md", SKILL_MD)]),
        "skill_package_too_large",
    )
    assert_error_code(
        extracted_size_service,
        archive_bytes(valid_entries()),
        "skill_package_too_large",
    )


def test_archive_enforces_skill_md_and_relative_path_limits() -> None:
    skill_md_service = SkillPackageService(
        SkillPackageLimits(skill_md_bytes=len(SKILL_MD) - 1)
    )
    path_service = SkillPackageService(SkillPackageLimits(relative_path_chars=8))

    assert_error_code(
        skill_md_service,
        archive_bytes([("report-writer/SKILL.md", SKILL_MD)]),
        "skill_package_too_large",
    )
    assert_error_code(
        path_service,
        archive_bytes(valid_entries()),
        "skill_unsafe_archive",
    )


def test_archive_enforces_compressed_upload_limit() -> None:
    archive = archive_bytes(valid_entries())
    service = SkillPackageService(
        SkillPackageLimits(archive_bytes=len(archive) - 1)
    )

    assert_error_code(service, archive, "skill_package_too_large")
