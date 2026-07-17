import pytest

from app.core.entities.skill import (
    SkillManifest,
    SkillRef,
    SkillSelectionMode,
    SkillSource,
)
from app.schemas.skill import SkillCatalogItem, SkillSelectionRequest
from app.services.skill_catalog_service import SkillCatalog
from app.services.skill_selection_service import SkillSelectionService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def item(
    name: str,
    *,
    source: SkillSource = SkillSource.BUNDLED,
    skill_id: str | None = None,
    auto_invoke: bool = True,
    allowed_tools: str | None = None,
) -> SkillCatalogItem:
    return SkillCatalogItem(
        ref=SkillRef(source=source, skill_id=skill_id, name=name),
        display_name=name.replace("-", " ").title(),
        manifest=SkillManifest(
            name=name,
            description=f"Use {name} for specialist work.",
            allowed_tools=allowed_tools,
        ),
        version_id=f"version-{skill_id}" if skill_id else None,
        version=1 if skill_id else None,
        package_sha256="b" * 64,
        auto_invoke=auto_invoke,
    )


class StaticCatalogService:
    def __init__(self, items: list[SkillCatalogItem]) -> None:
        self.catalog = SkillCatalog(
            items=tuple(items),
            automatic_candidates=tuple(entry for entry in items if entry.auto_invoke),
        )

    async def get_catalog(self, user_id: str) -> SkillCatalog:
        return self.catalog


class RecordingLlm:
    model_name = "selector-test"
    temperature = 0
    max_tokens = 256

    def __init__(self, content: str = '{"skills": []}', error: Exception | None = None):
        self.content = content
        self.error = error
        self.calls: list[dict] = []

    async def invoke(self, messages, tools=None, response_format=None, tool_choice=None):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "response_format": response_format,
                "tool_choice": tool_choice,
            }
        )
        if self.error:
            raise self.error
        return {"role": "assistant", "content": self.content}


class RecordingTrace:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.finished: list[tuple] = []

    async def record_model_call_started(self, **kwargs):
        self.started.append(kwargs)
        return "selector-call-1"

    async def record_model_call_finished(self, model_call_id, **kwargs):
        self.finished.append((model_call_id, kwargs))


def request(
    *,
    manual_refs: list[SkillRef] | None = None,
    tools: set[str] | None = None,
) -> SkillSelectionRequest:
    return SkillSelectionRequest(
        user_id="user-1",
        message="Please complete the requested work.",
        attachment_media_types=[],
        manual_refs=manual_refs or [],
        available_tool_names=tools or set(),
    )


def service_for(
    items: list[SkillCatalogItem],
    llm: RecordingLlm,
    trace: RecordingTrace | None = None,
) -> SkillSelectionService:
    async def llm_provider(user_id: str):
        assert user_id == "user-1"
        return llm

    return SkillSelectionService(
        catalog_service=StaticCatalogService(items),
        llm_provider=llm_provider,
        trace_service=trace,
    )


async def test_manual_selection_has_priority_and_is_limited_to_five() -> None:
    items = [item(f"skill-{index}") for index in range(6)]
    llm = RecordingLlm()
    service = service_for(items, llm)

    result = await service.select(
        request(manual_refs=[entry.ref for entry in items])
    )

    assert len(result.selected) == 5
    assert all(
        selected.selection_mode is SkillSelectionMode.MANUAL
        for selected in result.selected
    )
    assert result.skipped[-1].code == "manual_limit"
    assert llm.calls == []


async def test_automatic_selection_is_limited_to_three_and_five_combined() -> None:
    manual = [item("manual-one"), item("manual-two")]
    automatic = [item(f"auto-{index}") for index in range(4)]
    llm = RecordingLlm(
        '{"skills": ['
        + ",".join(
            f'{{"key":"{entry.selector_key}","confidence":0.9,"reason":"matched"}}'
            for entry in automatic
        )
        + "]}"
    )
    service = service_for(manual + automatic, llm)

    result = await service.select(
        request(manual_refs=[entry.ref for entry in manual])
    )

    assert len(result.selected) == 5
    assert [selected.selection_mode for selected in result.selected] == [
        SkillSelectionMode.MANUAL,
        SkillSelectionMode.MANUAL,
        SkillSelectionMode.AUTOMATIC,
        SkillSelectionMode.AUTOMATIC,
        SkillSelectionMode.AUTOMATIC,
    ]
    assert result.skipped[-1].code == "automatic_limit"
    assert llm.calls[0]["tools"] == []
    assert llm.calls[0]["response_format"] == {"type": "json_object"}


async def test_missing_tools_and_unavailable_manual_skill_are_skipped() -> None:
    shell_skill = item("shell-helper", allowed_tools="shell browser")
    missing = SkillRef(source=SkillSource.BUNDLED, name="disabled-skill")
    llm = RecordingLlm()
    service = service_for([shell_skill], llm)

    result = await service.select(
        request(manual_refs=[shell_skill.ref, missing], tools={"shell"})
    )

    assert result.selected == []
    assert [skip.code for skip in result.skipped] == [
        "missing_tools",
        "unavailable",
    ]
    assert llm.calls == []


async def test_hallucinated_selector_key_is_ignored_and_traced() -> None:
    candidate = item("report-writer")
    llm = RecordingLlm(
        '{"skills":[{"key":"bundled:not-real","confidence":0.7,"reason":"guess"}]}'
    )
    trace = RecordingTrace()
    service = service_for([candidate], llm, trace)

    result = await service.select(request())

    assert result.selected == []
    assert result.skipped[0].code == "unknown_selector_key"
    assert result.selector_model_call_id == "selector-call-1"
    assert trace.started[0]["agent_name"] == "skill_selector"
    assert trace.finished[0][1]["message"]["content"].startswith("{")


async def test_malformed_json_returns_warning_without_failing_the_run() -> None:
    candidate = item("report-writer")
    service = service_for([candidate], RecordingLlm("not-json"))

    result = await service.select(request())

    assert result.selected == []
    assert result.skipped[0].code == "selector_invalid_response"


async def test_blank_selector_reason_is_an_invalid_response_not_a_run_failure() -> None:
    candidate = item("report-writer")
    llm = RecordingLlm(
        '{"skills":[{"key":"bundled:report-writer",'
        '"confidence":0.9,"reason":"   "}]}'
    )
    service = service_for([candidate], llm)

    result = await service.select(request())

    assert result.selected == []
    assert result.skipped[0].code == "selector_invalid_response"


async def test_model_failure_keeps_manual_selection_and_records_warning() -> None:
    manual = item("manual-report")
    automatic = item("auto-report")
    trace = RecordingTrace()
    service = service_for(
        [manual, automatic],
        RecordingLlm(error=RuntimeError("provider unavailable")),
        trace,
    )

    result = await service.select(request(manual_refs=[manual.ref]))

    assert [selected.ref for selected in result.selected] == [manual.ref]
    assert result.skipped[-1].code == "selector_failed"
    assert result.selector_model_call_id == "selector-call-1"
    assert trace.finished[0][1]["error"] == "provider unavailable"


async def test_no_automatic_candidate_means_no_model_call() -> None:
    manual_only = item("manual-only", auto_invoke=False)
    llm = RecordingLlm()
    service = service_for([manual_only], llm)

    result = await service.select(request())

    assert result.selected == []
    assert result.selector_model_call_id is None
    assert llm.calls == []
