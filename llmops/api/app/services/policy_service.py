from dataclasses import dataclass, field
from typing import Any

from app.models.capability import Capability


@dataclass(frozen=True)
class PolicyDecision:
    status: str
    reason: str = ""
    risk_level: str = "low"
    requires_approval: bool = False
    audit_required: bool = True
    policy: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.status in {"allowed", "approval_required"}


class PolicyService:
    """Deterministic first-pass capability policy evaluator."""

    def evaluate_capability(
        self,
        capability: Capability,
        *,
        input_json: dict[str, Any] | None = None,
        idempotency_key: str = "",
    ) -> PolicyDecision:
        if not capability.enabled:
            return PolicyDecision(
                status="blocked",
                reason="capability_disabled",
                risk_level=capability.risk_level,
                policy=self._policy_snapshot(capability),
            )

        if capability.idempotency_required and not idempotency_key:
            return PolicyDecision(
                status="blocked",
                reason="idempotency_key_required",
                risk_level=capability.risk_level,
                policy=self._policy_snapshot(capability),
            )

        risk_level = self._risk_level(capability)
        requires_approval = capability.requires_approval or risk_level in {"high", "critical"}
        if requires_approval:
            return PolicyDecision(
                status="approval_required",
                reason="capability_requires_approval",
                risk_level=risk_level,
                requires_approval=True,
                audit_required=True,
                policy=self._policy_snapshot(capability, input_json=input_json),
            )

        return PolicyDecision(
            status="allowed",
            reason="policy_allowed",
            risk_level=risk_level,
            audit_required=True,
            policy=self._policy_snapshot(capability, input_json=input_json),
        )

    @staticmethod
    def _risk_level(capability: Capability) -> str:
        risk_level = str(capability.risk_level or "low").lower()
        if risk_level in {"low", "medium", "high", "critical"}:
            return risk_level
        if capability.side_effect not in {"", "none", "read"}:
            return "medium"
        return "low"

    @staticmethod
    def _policy_snapshot(capability: Capability, *, input_json: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "capability_id": str(capability.id) if capability.id else "",
            "permission": capability.permission,
            "side_effect": capability.side_effect,
            "data_scope_policy": capability.data_scope_policy,
            "audit_policy": capability.audit_policy,
            "input_keys": sorted((input_json or {}).keys()),
        }
