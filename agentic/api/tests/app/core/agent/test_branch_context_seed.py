from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.core.agent.planner import PlannerAgent
from app.core.agent.react import ReActAgent
from app.core.entities.app_config import AgentConfig
from app.core.entities.memory import Memory
from app.core.entities.session import BranchContextMessage
from app.models.session import SessionModel
from app.repositories.db_session_repository import DBSessionRepository


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MemoryRepository:
    def __init__(self, seed=None) -> None:
        self.memories: dict[tuple[str, str], Memory] = {}
        self.seed = list(seed or [])

    async def get_memory(self, session_id: str, agent_name: str) -> Memory:
        return self.memories.setdefault(
            (session_id, agent_name),
            Memory(),
        ).model_copy(deep=True)

    async def get_branch_context_seed(
        self, session_id: str
    ) -> list[BranchContextMessage]:
        return [item.model_copy(deep=True) for item in self.seed]

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
    model_name = "branch-context-test"
    temperature = 0
    max_tokens = 128

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def invoke(self, messages, **kwargs):
        self.calls.append(messages)
        return {"role": "assistant", "content": "ok"}


def build_agent(agent_cls, uow_factory: Callable, llm: RecordingLlm):
    return agent_cls(
        uow_factory=uow_factory,
        session_id="branch-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=object(),
        tools=[],
    )


async def test_planner_and_react_inject_safe_seed_after_their_system_prompt() -> None:
    seed = [
        BranchContextMessage(
            role="user",
            content="compare these drafts",
            attachment_names=["draft-a.md"],
        ),
        BranchContextMessage(role="assistant", content="first comparison"),
    ]
    repository = MemoryRepository(seed)

    def uow_factory() -> FakeUow:
        return FakeUow(repository)

    for agent_cls in (PlannerAgent, ReActAgent):
        llm = RecordingLlm()
        agent = build_agent(agent_cls, uow_factory, llm)

        await agent._invoke_llm([{"role": "user", "content": "continue"}])

        messages = llm.calls[0]
        assert messages[0]["role"] == "system"
        assert messages[1] == {
            "role": "user",
            "content": "compare these drafts\n\n历史附件文件名：draft-a.md",
        }
        assert messages[2] == {
            "role": "assistant",
            "content": "first comparison",
        }
        assert messages[3] == {"role": "user", "content": "continue"}
        assert "/uploads/" not in str(messages)


async def test_seed_is_persisted_once_and_not_reinjected_on_later_calls() -> None:
    repository = MemoryRepository(
        [BranchContextMessage(role="user", content="historical question")]
    )

    def uow_factory() -> FakeUow:
        return FakeUow(repository)

    llm = RecordingLlm()
    planner = build_agent(PlannerAgent, uow_factory, llm)

    await planner._invoke_llm([{"role": "user", "content": "first"}])
    await planner._invoke_llm([{"role": "user", "content": "second"}])

    assert str(llm.calls[0]).count("historical question") == 1
    assert str(llm.calls[1]).count("historical question") == 1
    persisted = repository.memories[("branch-1", "planner")].messages
    assert sum(
        message.get("content") == "historical question"
        for message in persisted
    ) == 1


async def test_existing_memory_and_normal_sessions_keep_their_current_behavior() -> None:
    repository = MemoryRepository(
        [BranchContextMessage(role="user", content="must not be injected")]
    )
    repository.memories[("branch-1", "planner")] = Memory(
        messages=[
            {"role": "system", "content": "existing prompt"},
            {"role": "user", "content": "existing turn"},
        ]
    )

    def uow_factory() -> FakeUow:
        return FakeUow(repository)

    llm = RecordingLlm()
    planner = build_agent(PlannerAgent, uow_factory, llm)
    await planner._invoke_llm([{"role": "user", "content": "resume"}])

    assert "must not be injected" not in str(llm.calls[0])
    assert llm.calls[0][:2] == repository.memories[("branch-1", "planner")].messages[:2]

    normal_repository = MemoryRepository()

    def normal_uow_factory() -> FakeUow:
        return FakeUow(normal_repository)

    normal_llm = RecordingLlm()
    normal_agent = build_agent(PlannerAgent, normal_uow_factory, normal_llm)
    await normal_agent._invoke_llm([{"role": "user", "content": "normal"}])
    assert [message["role"] for message in normal_llm.calls[0]] == [
        "system",
        "user",
    ]


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDBSession:
    def __init__(self, value):
        self.value = value

    async def execute(self, statement):
        return _ScalarResult(self.value)


async def test_repository_validates_seed_roles_instead_of_exposing_hidden_roles() -> None:
    repository = DBSessionRepository(
        _FakeDBSession([{"role": "tool", "content": "hidden", "attachment_names": []}])
    )

    with pytest.raises(ValidationError):
        await repository.get_branch_context_seed("branch-1")

    assert SessionModel.context_seed is not None
