from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.conversation import MessageStatus


class QueueEvent(StrEnum):
    LONG_TERM_MEMORY_RECALL = "long_term_memory_recall"
    AGENT_THOUGHT = "agent_thought"
    AGENT_MESSAGE = "agent_message"
    AGENT_ACTION = "agent_action"
    DATASET_RETRIEVAL = "dataset_retrieval"
    AGENT_END = "agent_end"
    STOP = "stop"
    ERROR = "error"
    TIMEOUT = "timeout"
    PING = "ping"


class AgentThought(BaseModel):
    id: UUID
    task_id: UUID
    event: QueueEvent
    thought: str = ""
    observation: str = ""
    tool: str = ""
    tool_input: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    message: list[dict] = Field(default_factory=list)
    message_token_count: int = 0
    message_unit_price: float = 0.0
    message_price_unit: float = 0.0
    answer: str = ""
    answer_token_count: int = 0
    answer_unit_price: float = 0.0
    answer_price_unit: float = 0.0
    total_token_count: int = 0
    total_price: float = 0.0
    latency: float = 0.0


class AgentResult(BaseModel):
    query: str = ""
    image_urls: list[str] = Field(default_factory=list)
    message: list[dict] = Field(default_factory=list)
    message_token_count: int = 0
    message_unit_price: float = 0.0
    message_price_unit: float = 0.0
    answer: str = ""
    answer_token_count: int = 0
    answer_unit_price: float = 0.0
    answer_price_unit: float = 0.0
    total_token_count: int = 0
    total_price: float = 0.0
    latency: float = 0.0
    status: str = MessageStatus.NORMAL.value
    error: str = ""
    agent_thoughts: list[AgentThought] = Field(default_factory=list)
