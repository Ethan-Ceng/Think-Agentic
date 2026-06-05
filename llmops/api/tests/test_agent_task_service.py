import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.core.conversation import InvokeFrom, MessageStatus
from app.models.account import Account
from app.models.agent import Agent
from app.models.conversation import Conversation, Message, MessageAgentThought
from app.models.end_user import EndUser
from app.models.task import AgentPlan, AgentStep, AgentTask, CapabilityCall, WorkerCall
from app.models.trace import TraceEvent
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
    def __init__(
        self,
        conversation: Conversation,
        message: Message,
        thought: MessageAgentThought,
        *,
        agent: Agent | None = None,
        task: AgentTask | None = None,
        plan: AgentPlan | None = None,
        step: AgentStep | None = None,
        worker_call: WorkerCall | None = None,
        trace_event: TraceEvent | None = None,
    ) -> None:
        self.conversation = conversation
        self.message = message
        self.thought = thought
        self.agent = agent
        self.task = task
        self.plan = plan
        self.step = step
        self.worker_call = worker_call
        self.trace_event = trace_event

    def query(self, *models):  # noqa: ANN002
        model = models[0]
        if model is Conversation.created_by:
            return FakeQuery(rows=[(self.conversation.created_by,)])
        if model is MessageAgentThought.conversation_id:
            return FakeQuery(rows=[(self.conversation.id, 1)])
        if model is TraceEvent.task_id:
            return FakeQuery(rows=[(self.task.id, 1)] if self.task else [])
        if model is AgentStep.task_id:
            return FakeQuery(rows=[(self.task.id,)] if self.task else [])
        if model is Conversation:
            return FakeQuery([self.conversation])
        if model is Account:
            return FakeQuery([])
        if model is EndUser:
            return FakeQuery([])
        if model is Agent:
            return FakeQuery([self.agent] if self.agent else [])
        if model is AgentTask:
            return FakeQuery([self.task] if self.task else [])
        if model is AgentPlan:
            return FakeQuery([self.plan] if self.plan else [])
        if model is AgentStep:
            return FakeQuery([self.step] if self.step else [])
        if model is WorkerCall:
            return FakeQuery([self.worker_call] if self.worker_call else [])
        if model is CapabilityCall:
            return FakeQuery([])
        if model is TraceEvent:
            return FakeQuery([self.trace_event] if self.trace_event else [])
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


def test_agent_task_service_attaches_task_execution_to_conversation_message() -> None:
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
        created_by=conversation.created_by,
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
    agent = Agent(
        id=uuid.uuid4(),
        tenant_id=account.id,
        created_by=account.id,
        name="Router",
        icon="",
        description="",
        runtime_type="router",
        product_category="router",
        status="published",
        visibility_scope={},
        target_ref_type="app",
        target_ref_id=str(app_id),
        created_at=now,
        updated_at=now,
    )
    task = AgentTask(
        id=uuid.uuid4(),
        tenant_id=account.id,
        conversation_id=conversation.id,
        router_agent_id=agent.id,
        user_id=message.created_by,
        status="succeeded",
        user_input={"query": "hello", "message_id": str(message.id)},
        final_result={"answer": "worker answer", "artifacts": [{"name": "result.txt"}]},
        error_code="",
        error_message="",
        version=1,
        started_at=now,
        finished_at=now,
        created_at=now,
        updated_at=now,
    )
    plan = AgentPlan(
        id=uuid.uuid4(),
        tenant_id=account.id,
        task_id=task.id,
        router_agent_id=agent.id,
        schema_version="router_plan_v1",
        plan_json={"steps": []},
        risk_level="low",
        status="succeeded",
        created_at=now,
        updated_at=now,
    )
    step = AgentStep(
        id=uuid.uuid4(),
        tenant_id=account.id,
        task_id=task.id,
        plan_id=plan.id,
        step_key="worker_1",
        worker_agent_id=agent.id,
        dependencies=[],
        execution_mode="sync",
        status="succeeded",
        input_json={
            "task": "hello",
            "planner_selection": {
                "reason": "Planner selected Router for the test step",
                "signals": ["name:Router"],
            },
        },
        output_json={"answer": "worker answer"},
        retry_count=0,
        timeout_seconds=120,
        started_at=now,
        finished_at=now,
        created_at=now,
        updated_at=now,
    )
    worker_call = WorkerCall(
        id=uuid.uuid4(),
        tenant_id=account.id,
        task_id=task.id,
        step_id=step.id,
        worker_agent_id=agent.id,
        invocation_json={"task": {"task": "hello"}, "context": {"input_files": [{"name": "input.txt"}]}},
        result_json={"answer": "worker answer"},
        status="succeeded",
        token_count=8,
        cost=Decimal("0"),
        latency=Decimal("0.4"),
        created_at=now,
        updated_at=now,
    )
    trace_event = TraceEvent(
        id=uuid.uuid4(),
        tenant_id=account.id,
        trace_id=f"task:{task.id}",
        task_id=task.id,
        plan_id=plan.id,
        step_id=step.id,
        worker_call_id=worker_call.id,
        event_type="worker.call.succeeded",
        payload={"message": "worker completed"},
        token_count=8,
        cost=Decimal("0"),
        latency=Decimal("0.4"),
        created_at=now,
        updated_at=now,
    )
    service = AgentTaskService(app_service=FakeAppService())
    session = FakeSession(
        conversation,
        message,
        thought,
        agent=agent,
        task=task,
        plan=plan,
        step=step,
        worker_call=worker_call,
        trace_event=trace_event,
    )

    records, *_ = service.list_app_tasks_with_page(session, app_id=app_id, account=account, page=1, page_size=20)
    detail = service.get_app_task_detail(session, app_id=app_id, task_id=conversation.id, account=account)
    message_detail = detail["messages"][0]
    message_task = message_detail["agent_tasks"][0]

    assert records[0]["trace_count"] == 2
    assert detail["trace_count"] == 2
    assert message_task["id"] == task.id
    assert message_task["steps"][0]["id"] == step.id
    assert message_task["worker_calls"][0]["id"] == worker_call.id
    assert any(event["event_type"] == "worker.call.succeeded" for event in message_detail["trace_events"])
    task_trace = next(
        event for event in message_detail["trace_events"] if event["event_type"] == "worker.call.succeeded"
    )
    assert task_trace["agent"]["name"] == "Router"
    assert task_trace["step"]["step_key"] == "worker_1"
    assert task_trace["step"]["task"] == "hello"
    assert task_trace["step"]["selection_reason"] == "Planner selected Router for the test step"
    assert "hello" in task_trace["step"]["input_preview"]
    assert task_trace["worker_call"]["id"] == worker_call.id
    assert "hello" in task_trace["worker_call"]["invocation_preview"]
    assert detail["input_files"][0]["name"] == "input.txt"
    assert detail["artifacts"][0]["name"] == "result.txt"
