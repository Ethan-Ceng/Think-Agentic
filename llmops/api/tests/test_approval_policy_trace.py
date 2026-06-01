import uuid

import pytest

from app.core.exceptions import FailException
from app.models.capability import Capability
from app.models.task import AgentPlan, AgentStep, AgentTask, CapabilityCall
from app.services.approval_service import ApprovalService, ApprovalStatus
from app.services.policy_service import PolicyService
from app.services.trace_service import TraceService


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flushed = 0

    def add(self, model_instance) -> None:  # noqa: ANN001
        if getattr(model_instance, "id", None) is None:
            model_instance.id = uuid.uuid4()
        self.added.append(model_instance)

    def flush(self) -> None:
        self.flushed += 1

    def refresh(self, model_instance) -> None:  # noqa: ANN001
        return None


def test_policy_blocks_disabled_and_missing_idempotency() -> None:
    disabled = Capability(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Export",
        type="tool",
        target_ref_type="api_tool",
        target_ref_id="export",
        enabled=False,
        risk_level="low",
        side_effect="write",
        permission="",
        data_scope_policy={},
        audit_policy={},
        idempotency_required=False,
        requires_approval=False,
    )
    idempotent = Capability(
        id=uuid.uuid4(),
        tenant_id=disabled.tenant_id,
        name="Create Ticket",
        type="tool",
        target_ref_type="api_tool",
        target_ref_id="ticket",
        enabled=True,
        risk_level="medium",
        side_effect="write",
        permission="ticket:create",
        data_scope_policy={},
        audit_policy={},
        idempotency_required=True,
        requires_approval=False,
    )

    service = PolicyService()

    disabled_decision = service.evaluate_capability(disabled)
    idempotency_decision = service.evaluate_capability(idempotent)

    assert disabled_decision.status == "blocked"
    assert disabled_decision.reason == "capability_disabled"
    assert idempotency_decision.status == "blocked"
    assert idempotency_decision.reason == "idempotency_key_required"


def test_policy_requires_approval_for_high_risk_capability() -> None:
    capability = Capability(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Send Quote",
        type="tool",
        target_ref_type="api_tool",
        target_ref_id="quote",
        enabled=True,
        risk_level="high",
        side_effect="external_write",
        permission="quote:send",
        data_scope_policy={"scope": "tenant"},
        audit_policy={"level": "full"},
        idempotency_required=False,
        requires_approval=False,
    )

    decision = PolicyService().evaluate_capability(capability, input_json={"customer_id": "c1"})

    assert decision.status == "approval_required"
    assert decision.allowed is True
    assert decision.requires_approval is True
    assert decision.risk_level == "high"
    assert decision.policy["input_keys"] == ["customer_id"]


def test_approval_request_lifecycle_and_capability_link() -> None:
    session = FakeSession()
    tenant_id = uuid.uuid4()
    capability_call = CapabilityCall(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        task_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        capability_id=uuid.uuid4(),
        input_json={"amount": 1200},
        output_json={},
        status="waiting_approval",
        risk_level="high",
        idempotency_key="quote-1",
        latency=0,
    )
    service = ApprovalService()

    approval = service.create_request(
        session,
        tenant_id=tenant_id,
        task_id=capability_call.task_id,
        capability_call=capability_call,
        action_type="capability_call",
        title="Send quote",
        proposed_payload=capability_call.input_json,
        risk_level="high",
        approver_policy={"roles": ["owner"]},
    )

    assert approval.status == ApprovalStatus.PENDING
    assert approval.capability_call_id == capability_call.id
    assert capability_call.approval_id == approval.id

    service.approve(session, approval, approved_by=uuid.uuid4(), decision_payload={"comment": "ok"})

    assert approval.status == ApprovalStatus.APPROVED
    assert approval.decision_payload == {"comment": "ok"}
    assert approval.decided_at is not None

    with pytest.raises(FailException):
        service.reject(session, approval, rejected_by=uuid.uuid4())


def test_trace_event_records_governance_chain() -> None:
    session = FakeSession()
    tenant_id = uuid.uuid4()
    task = AgentTask(id=uuid.uuid4(), tenant_id=tenant_id, router_agent_id=uuid.uuid4(), status="running")
    plan = AgentPlan(id=uuid.uuid4(), tenant_id=tenant_id, task_id=task.id, router_agent_id=task.router_agent_id)
    step = AgentStep(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        task_id=task.id,
        plan_id=plan.id,
        step_key="send_quote",
        worker_agent_id=uuid.uuid4(),
    )
    capability_call = CapabilityCall(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        task_id=task.id,
        step_id=step.id,
        capability_id=uuid.uuid4(),
        input_json={},
        output_json={},
        status="waiting_approval",
    )
    approval = ApprovalService().create_request(
        session,
        tenant_id=tenant_id,
        task_id=task.id,
        capability_call=capability_call,
        action_type="capability_call",
        title="Approve capability",
    )

    event = TraceService().record(
        session,
        tenant_id=tenant_id,
        event_type="approval.required",
        task=task,
        plan=plan,
        step=step,
        capability_call=capability_call,
        approval=approval,
        payload={"risk_level": "high"},
        latency=0.12,
    )

    assert event.trace_id == f"task:{task.id}"
    assert event.task_id == task.id
    assert event.plan_id == plan.id
    assert event.step_id == step.id
    assert event.capability_call_id == capability_call.id
    assert event.approval_id == approval.id
    assert event.event_type == "approval.required"
    assert event.payload == {"risk_level": "high"}
