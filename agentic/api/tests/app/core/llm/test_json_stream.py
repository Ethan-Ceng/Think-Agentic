from __future__ import annotations

import pytest

from app.core.llm.json_stream import (
    JSONProjectionError,
    TopLevelJSONStringProjector,
)


def project_by_chunks(payload: str, chunks: list[int]) -> tuple[str, bool]:
    projector = TopLevelJSONStringProjector("answer")
    emitted: list[str] = []
    offset = 0
    for size in chunks:
        emitted.append(projector.feed(payload[offset : offset + size]))
        offset += size
    emitted.append(projector.feed(payload[offset:]))
    return "".join(emitted), projector.complete


def test_projects_only_the_requested_top_level_string_one_character_at_a_time() -> None:
    payload = (
        '{"meta":{"answer":"secret"},'
        '"note":"mentions \\"answer\\": \\"fake\\"",'
        '"answer":"Hello\\n世界 \\\\ path \\"quoted\\" '
        '\\ud83d\\ude80","tail":true}'
    )

    projected, complete = project_by_chunks(payload, [1] * len(payload))

    assert projected == 'Hello\n世界 \\ path "quoted" 🚀'
    assert complete is True


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('{"before":[{"answer":"nested"}],"answer":"top"}', "top"),
        ('{"text":"\\\"answer\\\":\\\"fake\\\"","answer":"safe"}', "safe"),
        ('{"answer":"quote: \\\" and slash: \\\\"}', 'quote: " and slash: \\'),
        ('{"answer":"line\\nfeed\\tend"}', "line\nfeed\tend"),
    ],
)
def test_handles_nested_values_and_json_escape_boundaries(
    payload: str,
    expected: str,
) -> None:
    projected, complete = project_by_chunks(payload, [2, 1, 3, 1, 4, 1])

    assert projected == expected
    assert complete is True


def test_rejects_a_non_string_target_field() -> None:
    projector = TopLevelJSONStringProjector("answer")

    with pytest.raises(JSONProjectionError, match="字符串"):
        projector.feed('{"answer":{"text":"not visible"}}')


def test_incomplete_unicode_escape_waits_without_emitting_a_broken_character() -> None:
    projector = TopLevelJSONStringProjector("answer")

    assert projector.feed('{"answer":"go \\ud83d') == "go "
    assert projector.feed('\\ude80 now"}') == "🚀 now"
    assert projector.complete is True


def test_non_json_prefix_is_not_projected_or_treated_as_visible_content() -> None:
    projector = TopLevelJSONStringProjector("answer")

    assert projector.feed('```json\n{"answer":"hidden until final"}') == ""
    assert projector.started is False
    assert projector.complete is False


def test_reset_discards_prior_buffer_and_emitted_prefix() -> None:
    projector = TopLevelJSONStringProjector("answer")
    assert projector.feed('{"answer":"old') == "old"

    projector.reset()

    assert projector.feed('{"answer":"new"}') == "new"
    assert projector.complete is True

