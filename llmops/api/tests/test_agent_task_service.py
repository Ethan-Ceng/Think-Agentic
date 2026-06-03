import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.core.conversation import InvokeFrom, MessageStatus
from app.models.account import Account
from app.models.agent import Agent
from app.models.conversation import Conversation, Message, MessageAgentThought
from app.models.end_user import EndUser
from app.models.task import AgentTask
from app.services.agent_task_service import AgentTaskService


class FakeQuery:
    def __init__(self, items=None, rows=None) -> None:
        self.items = list(items or [])
        self.rows = rows
        self.limit_value = None

    def filter(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self

    def order_by(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self

    def group_by(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self

    def distinct(self):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def count(self):
        return len(self.items)

    def all(self):
        if self.rows is not None:
            return self.rows
        if self.limit_value is None:
            return self.items
        return self.items[: self.limit_value]

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self, conversation: Conversation, message: Message, thought: MessageAgentThought) -> None:
        self.conversation = conversation
        self.message = message
        self.thought = thought

    def query(self, *models):  # noqa: ANN002
        model = models[0]
        if model is Conversation.created_by:
            return FakeQuery(rows=[(self.conversation.created_by,)])
        if model is Conversation:
            return FakeQuery([self.conversation])
        if model is Account:
            return FakeQuery([])
        if model is EndUser:
            return FakeQuery([])
        if model is Agent:
            return FakeQuery([])
        if model is AgentTask:
            return FakeQuery([])
        if model is Message:
            return FakeQuery([self.message])
        if model is MessageAgentThought:
            return FakeQuery([self.thought])
        return FakeQuery(rows=[(self.conversation.id, 1)])


class FakeAppService:
    def get_app(self, session, app_id, account):  # noqa: ANN001
        return SimpleNamespace(id=app_id, account_id=account.id)


def test_agent_task_service_groups_app_chat_messages_by_conversation() -> None:
    app_id = uuid.uuid4()
    account = SimpleNamespace(id=uuid.uuid4())
    now = datetime.now()
    conversation = Conversation(
        id=uuid.uuid4(),
        app_id=app_id,
        name="New Conversation",
        summary="",
        is_pinned=False,
        is_deleted=False,
        invoke_from=InvokeFrom.WEB_APP.value,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=uuid.uuid4(),
        app_id=app_id,
        conversation_id=conversation.id,
        invoke_from=InvokeFrom.WEB_APP.value,
        created_by=uuid.uuid4(),
        query="hello",
        image_urls=[],
        message=[],
        answer="hi",
        status=MessageStatus.NORMAL.value,
        error="",
        total_token_count=12,
        total_price=Decimal("0"),
        latency=1.2,
        is_deleted=False,
        created_at=now,
        updated_at=now,
    )
    thought = MessageAgentThought(
        id=uuid.uuid4(),
        app_id=app_id,
        conversation_id=message.conversation_id,
        message_id=message.id,
        invoke_from=InvokeFrom.WEB_APP.value,
        created_by=message.created_by,
        position=1,
        event="agent_message",
        thought="thinking",
        observation="",
        tool="",
        tool_input={},
        message=[],
        answer="hi",
        total_token_count=12,
        total_price=Decimal("0"),
        latency=1.2,
        created_at=now,
        updated_at=now,
    )
    service = AgentTaskService(app_service=FakeAppService())
    session = FakeSession(conversation, message, thought)

    records, total_record, total_page, users = service.list_app_tasks_with_page(
        session,
        app_id=app_id,
        account=account,
        page=1,
        page_size=20,
    )
    detail = service.get_app_task_detail(session, app_id=app_id, task_id=conversation.id, account=account)

    assert total_record == 1
    assert total_page == 1
    assert users[0]["id"] == str(conversation.created_by)
    assert records[0]["id"] == conversation.id
    assert records[0]["run_type"] == InvokeFrom.WEB_APP.value
    assert records[0]["status"] == "succeeded"
    assert records[0]["message_count"] == 1
    assert records[0]["trace_count"] == 1
    assert detail["messages"][0]["id"] == message.id
    assert detail["trace_events"][0]["event_type"] == "agent_message"
    assert detail["trace_events"][0]["payload"]["answer"] == "hi"
