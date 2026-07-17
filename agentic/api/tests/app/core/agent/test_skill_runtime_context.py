from collections.abc import Callable

import pytest

from app.core.agent.planner import PlannerAgent
from app.core.agent.react import ReActAgent
from app.core.entities.app_config import AgentConfig
from app.core.entities.memory import Memory
from app.core.entities.skill import (
    SelectedSkill,
    SkillManifest,
    SkillRef,
    SkillSelectionMode,
    SkillSource,
)
from app.services.skill_runtime_service import SkillRuntimeContext


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
        self, session_id: str, agent_name: str, memory: Memory
    ) -> None:
        self.memories[(session_id, agent_name)] = memory.model_copy(deep=True)


class FakeUow:
    def __init__(self, session: MemoryRepository) -> None:
        self.session = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class RecordingLlm:
    model_name = "runtime-test"
    temperature = 0
    max_tokens = 128

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def invoke(self, messages, **kwargs):
        self.calls.append(messages)
        return {"role": "assistant", "content": "ok"}


def selected_skill() -> SelectedSkill:
    return SelectedSkill(
        ref=SkillRef(
            source=SkillSource.PERSONAL,
            skill_id="skill-1",
            name="report-writer",
        ),
        version_id="version-1",
        version=1,
        manifest=SkillManifest(
            name="report-writer",
            description="Write structured reports.",
        ),
        selection_mode=SkillSelectionMode.MANUAL,
        reason="Selected manually by the user.",
        package_sha256="a" * 64,
    )


def build_agent(agent_cls, uow_factory: Callable, llm: RecordingLlm):
    return agent_cls(
        uow_factory=uow_factory,
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=object(),
        tools=[],
    )


async def test_runtime_context_is_visible_to_planner_and_react_but_not_memory() -> None:
    repository = MemoryRepository()

    def uow_factory() -> FakeUow:
        return FakeUow(repository)

    planner_llm = RecordingLlm()
    react_llm = RecordingLlm()
    planner = build_agent(PlannerAgent, uow_factory, planner_llm)
    react = build_agent(ReActAgent, uow_factory, react_llm)
    root = "/home/ubuntu/.agentic/skills/run-1/report-writer"
    prompt_block = (
        "<skill_runtime_context>\n"
        f'<skill name="report-writer" root="{root}">\n'
        "Use the report workflow in this SKILL.md.\n"
        "</skill>\n"
        "</skill_runtime_context>"
    )
    context = SkillRuntimeContext(
        selected=[selected_skill()],
        prompt_block=prompt_block,
        sandbox_roots={"report-writer": root},
    )

    planner.set_skill_runtime_context(context)
    react.set_skill_runtime_context(context)
    await planner._invoke_llm([{"role": "user", "content": "plan"}])
    await react._invoke_llm([{"role": "user", "content": "execute"}])

    for messages in (planner_llm.calls[0], react_llm.calls[0]):
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "system", "content": prompt_block}
        assert root in messages[1]["content"]

    for memory in repository.memories.values():
        persisted = "\n".join(str(message) for message in memory.messages)
        assert "skill_runtime_context" not in persisted


async def test_runtime_context_disappears_on_the_next_run() -> None:
    repository = MemoryRepository()

    def uow_factory() -> FakeUow:
        return FakeUow(repository)

    llm = RecordingLlm()
    planner = build_agent(PlannerAgent, uow_factory, llm)
    context = SkillRuntimeContext(
        selected=[selected_skill()],
        prompt_block="<skill_runtime_context>temporary</skill_runtime_context>",
        sandbox_roots={"report-writer": "/home/ubuntu/.agentic/skills/run-1/report-writer"},
    )

    planner.set_skill_runtime_context(context)
    await planner._invoke_llm([{"role": "user", "content": "first run"}])
    planner.set_skill_runtime_context(SkillRuntimeContext())
    await planner._invoke_llm([{"role": "user", "content": "second run"}])

    assert "skill_runtime_context" in str(llm.calls[0])
    assert "skill_runtime_context" not in str(llm.calls[1])
