from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import pytest

from app.core.agent.base import BaseAgent
from app.core.agent.planner import PlannerAgent
from app.core.agent.react import ReActAgent
from app.core.entities.app_config import AgentConfig
from app.core.entities.event import BaseEvent, MessageEvent, PlanEvent
from app.core.entities.memory import Memory
from app.core.entities.message import Message
from app.core.entities.plan import Plan, Step
from app.core.prompts.catalog import (
    PromptLocale,
    get_planner_prompts,
    get_react_prompts,
    infer_prompt_locale,
    resolve_prompt_locale,
)
from app.core.prompts.lead import LEAD_DECISION_PROMPT


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MemoryRepository:
    def __init__(self) -> None:
        self.memories: dict[tuple[str, str], Memory] = {}

    async def get_memory(self, session_id: str, agent_name: str) -> Memory:
        return self.memories.setdefault((session_id, agent_name), Memory())

    async def save_memory(
        self,
        session_id: str,
        agent_name: str,
        memory: Memory,
    ) -> None:
        self.memories[(session_id, agent_name)] = memory.model_copy(deep=True)

    async def get_branch_context_seed(self, session_id: str) -> list:
        return []


class FakeUow:
    def __init__(self, session: MemoryRepository) -> None:
        self.session = session

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class JsonParser:
    async def invoke(self, value: str):
        return json.loads(value)


class QueueLlm:
    model_name = "prompt-locale-test"
    temperature = 0
    max_tokens = 512

    def __init__(self, *contents: dict) -> None:
        self.contents = list(contents)
        self.calls: list[dict] = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents.pop(0) if self.contents else {}
        return {
            "role": "assistant",
            "content": json.dumps(content, ensure_ascii=False),
        }


class ProbeAgent(BaseAgent):
    name = "probe"
    _system_prompt = "persisted default system"
    _format = "json_object"


async def collect(stream: AsyncGenerator[BaseEvent, None]) -> list[BaseEvent]:
    return [event async for event in stream]


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("zh", PromptLocale.ZH),
        ("zh-CN", PromptLocale.ZH),
        ("Chinese", PromptLocale.ZH),
        ("中文", PromptLocale.ZH),
        ("en", PromptLocale.EN),
        ("en-US", PromptLocale.EN),
        ("English", PromptLocale.EN),
        ("英语", PromptLocale.EN),
        ("fr", PromptLocale.EN),
        ("日语", PromptLocale.EN),
        ("日本語", PromptLocale.EN),
    ],
)
def test_resolve_prompt_locale_from_lead_language(
    language: str,
    expected: PromptLocale,
) -> None:
    assert resolve_prompt_locale(language) is expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("请帮我规划一份报告", PromptLocale.ZH),
        ("Please plan a report", PromptLocale.EN),
        ("请 summarize this report", PromptLocale.ZH),
        ("Please summarize 这份 report", PromptLocale.EN),
    ],
)
def test_infer_prompt_locale_for_legacy_first_turn(
    message: str,
    expected: PromptLocale,
) -> None:
    assert infer_prompt_locale(message) is expected


def test_prompt_catalog_returns_localized_complete_packs() -> None:
    zh_planner = get_planner_prompts("zh-CN")
    en_planner = get_planner_prompts("en-US")
    zh_react = get_react_prompts("Chinese")
    en_react = get_react_prompts("English")

    assert "任务规划智能体" in zh_planner.system
    assert "task planner agent" in en_planner.system
    assert "Capability Catalog" in zh_planner.create
    assert "Capability Catalog" in en_planner.create
    assert "直接完成一个单一目标" in zh_react.goal_execution
    assert "directly completing one goal" in en_react.goal_execution
    assert "needs_replan" in zh_react.execution
    assert "needs_replan" in en_react.execution
    assert "多个 MCP Provider" in zh_planner.create
    assert "multiple MCP Providers" in en_planner.create
    assert "search_tools" in zh_planner.create
    assert "search_tools" in en_planner.create
    assert "多个 MCP Provider" in LEAD_DECISION_PROMPT
    assert "multiple MCP Providers" in LEAD_DECISION_PROMPT
    assert "untrusted metadata" in LEAD_DECISION_PROMPT
    assert "不可信元数据" in zh_planner.create
    assert "untrusted metadata" in en_planner.create


async def test_runtime_system_prompt_changes_llm_view_without_mutating_memory() -> None:
    repository = MemoryRepository()
    llm = QueueLlm({}, {})
    agent = ProbeAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=JsonParser(),
        tools=[],
    )

    agent.set_runtime_system_prompt("English runtime system")
    await agent._invoke_llm([{"role": "user", "content": "first"}])
    agent.set_runtime_system_prompt("中文运行时系统提示")
    await agent._invoke_llm([{"role": "user", "content": "second"}])

    assert llm.calls[0]["messages"][0]["content"] == "English runtime system"
    assert llm.calls[1]["messages"][0]["content"] == "中文运行时系统提示"
    persisted = repository.memories[("session-1", "probe")]
    assert persisted.messages[0]["content"] == "persisted default system"


async def test_planner_selects_prompt_pack_per_message_and_plan_language() -> None:
    repository = MemoryRepository()
    llm = QueueLlm(
        {
            "title": "Report",
            "goal": "Prepare a report",
            "language": "en",
            "message": "I will prepare it.",
            "steps": [
                {
                    "id": "1",
                    "description": "Draft the report",
                    "capabilities": [],
                }
            ],
        },
        {
            "title": "报告",
            "goal": "准备报告",
            "language": "zh-CN",
            "message": "我会准备报告。",
            "steps": [
                {
                    "id": "1",
                    "description": "撰写报告",
                    "capabilities": [],
                }
            ],
        },
    )
    planner = PlannerAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=JsonParser(),
        tools=[],
    )

    english_events = await collect(
        planner.create_plan(Message(message="Please plan a report"))
    )
    chinese_events = await collect(
        planner.create_plan(Message(message="请规划一份报告"))
    )

    assert any(isinstance(event, PlanEvent) for event in english_events)
    assert any(isinstance(event, PlanEvent) for event in chinese_events)
    assert "You are LingShu" in llm.calls[0]["messages"][0]["content"]
    assert "你是 灵枢" in llm.calls[1]["messages"][0]["content"]
    english_query = llm.calls[0]["messages"][-1]["content"]
    chinese_query = llm.calls[1]["messages"][-1]["content"]
    assert "You are now creating a plan" in english_query
    assert "provider_ids" in english_query
    assert "tool_ids" in english_query
    assert "provider_ids" in chinese_query
    assert "tool_ids" in chinese_query
    assert "你现在正在根据用户的消息创建一个计划" in chinese_query
    assert english_query.count("Please plan a report") == 1
    assert chinese_query.count("请规划一份报告") == 1


async def test_planner_update_uses_persisted_plan_language() -> None:
    repository = MemoryRepository()
    llm = QueueLlm({"steps": []})
    planner = PlannerAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=JsonParser(),
        tools=[],
    )
    plan = Plan(
        title="Report",
        goal="Prepare a report",
        language="en-US",
        steps=[Step(id="1", description="Recover the failed source")],
    )

    await collect(planner.update_plan(plan, plan.steps[0]))

    assert "You are LingShu" in llm.calls[0]["messages"][0]["content"]
    update_query = llm.calls[0]["messages"][-1]["content"]
    assert "You are updating the plan" in update_query
    assert "Capability Catalog" in update_query


async def test_react_selects_prompt_pack_from_lead_language_on_same_memory() -> None:
    repository = MemoryRepository()
    llm = QueueLlm(
        {"message": "Done", "attachments": []},
        {"message": "完成", "attachments": []},
    )
    react = ReActAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=JsonParser(),
        tools=[],
    )

    english_events = await collect(
        react.execute_goal(
            "Finish the report",
            "en-US",
            [],
            Message(message="Please finish the report"),
        )
    )
    chinese_events = await collect(
        react.execute_goal(
            "完成报告",
            "zh-CN",
            [],
            Message(message="请完成报告"),
        )
    )

    assert any(
        isinstance(event, MessageEvent) and event.message == "Done"
        for event in english_events
    )
    assert any(
        isinstance(event, MessageEvent) and event.message == "完成"
        for event in chinese_events
    )
    assert "You are LingShu" in llm.calls[0]["messages"][0]["content"]
    assert "你是 灵枢" in llm.calls[1]["messages"][0]["content"]
    assert "directly completing one goal" in llm.calls[0]["messages"][-1]["content"]
    assert "直接完成一个单一目标" in llm.calls[1]["messages"][-1]["content"]


async def test_react_step_and_finalizer_use_plan_language() -> None:
    repository = MemoryRepository()
    plan = Plan(
        title="Report",
        goal="Prepare a report",
        language="en",
        steps=[Step(id="1", description="Draft the report")],
    )
    llm = QueueLlm(
        {
            "id": "1",
            "description": "Draft the report",
            "success": True,
            "result": "Drafted",
            "attachments": [],
            "needs_replan": False,
            "replan_reason": None,
        },
        {"message": "Final report", "attachments": []},
    )
    react = ReActAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=JsonParser(),
        tools=[],
    )

    await collect(react.execute_step(plan, plan.steps[0], Message(message="Do it")))
    final_events = await collect(react.summarize(plan.language))

    assert any(
        isinstance(event, MessageEvent) and event.message == "Final report"
        for event in final_events
    )
    assert "You are LingShu" in llm.calls[0]["messages"][0]["content"]
    assert "You are LingShu" in llm.calls[1]["messages"][0]["content"]
    assert "You are executing the task" in llm.calls[0]["messages"][-1]["content"]
    assert "You are finished the task" in llm.calls[1]["messages"][-1]["content"]
