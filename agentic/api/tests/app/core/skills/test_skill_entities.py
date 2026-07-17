import pytest
from pydantic import ValidationError

from app.core.entities.skill import (
    SelectedSkill,
    SkillManifest,
    SkillRef,
    SkillSelectionMode,
    SkillSource,
)


def valid_manifest_data() -> dict[str, object]:
    return {
        "name": "report-writer",
        "description": (
            "Create evidence-based reports when the user requests structured research."
        ),
        "license": "Apache-2.0",
        "compatibility": "Requires Python 3.12 and optional network access.",
        "metadata": {"author": "agentic", "version": "1.0"},
        "allowed-tools": "search_web read_file write_file",
    }


def test_skill_enums_serialize_to_protocol_values() -> None:
    assert SkillSource.BUNDLED.value == "bundled"
    assert SkillSource.PERSONAL.value == "personal"
    assert SkillSource.MARKETPLACE.value == "marketplace"
    assert SkillSelectionMode.MANUAL.value == "manual"
    assert SkillSelectionMode.AUTOMATIC.value == "automatic"


def test_manifest_accepts_official_fields_and_uses_frontmatter_aliases() -> None:
    manifest = SkillManifest.model_validate(valid_manifest_data())

    assert manifest.name == "report-writer"
    assert manifest.allowed_tools == "search_web read_file write_file"
    assert (
        manifest.model_dump(by_alias=True)["allowed-tools"]
        == "search_web read_file write_file"
    )


@pytest.mark.parametrize(
    "name",
    ["Report-Writer", "-report-writer", "report-writer-", "report_writer", ""],
)
def test_manifest_rejects_invalid_standard_names(name: str) -> None:
    data = valid_manifest_data()
    data["name"] = name

    with pytest.raises(ValidationError):
        SkillManifest.model_validate(data)


def test_manifest_rejects_unknown_top_level_fields() -> None:
    data = valid_manifest_data()
    data["display_name"] = "Report Writer"

    with pytest.raises(ValidationError, match="display_name"):
        SkillManifest.model_validate(data)


def test_manifest_requires_string_metadata_values() -> None:
    data = valid_manifest_data()
    data["metadata"] = {"version": 1}

    with pytest.raises(ValidationError, match="metadata.version"):
        SkillManifest.model_validate(data)


def test_personal_and_marketplace_refs_require_skill_id() -> None:
    for source in (SkillSource.PERSONAL, SkillSource.MARKETPLACE):
        with pytest.raises(ValidationError, match="skill_id"):
            SkillRef(source=source, name="report-writer")


def test_bundled_ref_uses_name_identity_and_rejects_skill_id() -> None:
    ref = SkillRef(source=SkillSource.BUNDLED, name="skill-creator")

    assert ref.model_dump(mode="json") == {
        "source": "bundled",
        "skill_id": None,
        "name": "skill-creator",
    }

    with pytest.raises(ValidationError, match="skill_id"):
        SkillRef(
            source=SkillSource.BUNDLED,
            skill_id="bundled-id",
            name="skill-creator",
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_selected_skill_rejects_confidence_outside_unit_interval(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        SelectedSkill(
            ref=SkillRef(
                source=SkillSource.PERSONAL,
                skill_id="skill-1",
                name="report-writer",
            ),
            version_id="version-1",
            version=1,
            manifest=SkillManifest.model_validate(valid_manifest_data()),
            selection_mode=SkillSelectionMode.AUTOMATIC,
            confidence=confidence,
            reason="The request asks for a structured research report.",
            package_sha256="a" * 64,
        )
