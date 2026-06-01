from uuid import UUID

from app.core.exceptions import FailException
from app.domain.agent_runtime.protocols import RouterPlan


class RouterRuntime:
    """Validate manager-mode Router plans before Task Engine persistence."""

    def validate_plan(self, plan: RouterPlan, allowed_worker_ids: set[str] | None = None) -> RouterPlan:
        step_ids = set()
        for step in plan.steps:
            if step.step_id in step_ids:
                raise FailException(f"Duplicate router plan step id: {step.step_id}")
            step_ids.add(step.step_id)

            try:
                UUID(step.worker_id)
            except ValueError as exc:
                raise FailException(f"Router plan step {step.step_id} has invalid worker id") from exc

            if allowed_worker_ids is not None and step.worker_id not in allowed_worker_ids:
                raise FailException(f"Router plan step {step.step_id} uses unbound worker")

        for step in plan.steps:
            unknown_dependencies = [dependency for dependency in step.dependencies if dependency not in step_ids]
            if unknown_dependencies:
                raise FailException(
                    f"Router plan step {step.step_id} references unknown dependencies: "
                    f"{', '.join(unknown_dependencies)}",
                )

        return plan
