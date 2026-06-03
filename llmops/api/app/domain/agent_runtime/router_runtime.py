from uuid import UUID

from app.core.exceptions import FailException
from app.domain.agent_runtime.protocols import RouterPlan


class RouterRuntime:
    """Validate manager-mode Router plans before Task Engine persistence."""

    def validate_plan(
        self,
        plan: RouterPlan,
        allowed_worker_ids: set[str] | None = None,
        *,
        router_id: str | None = None,
        max_steps: int = 5,
        allow_async: bool = False,
        allow_required_approval: bool = True,
    ) -> RouterPlan:
        if router_id is not None and plan.router_id != router_id:
            raise FailException("Router plan router_id does not match current router agent")
        if not plan.steps:
            raise FailException("Router plan must contain at least one step")
        if len(plan.steps) > max_steps:
            raise FailException(f"Router plan can contain at most {max_steps} steps")

        step_ids = set()
        for step in plan.steps:
            if step.step_id in step_ids:
                raise FailException(f"Duplicate router plan step id: {step.step_id}")
            step_ids.add(step.step_id)
            if not step.task.strip():
                raise FailException(f"Router plan step {step.step_id} has empty task")
            if not allow_async and step.execution_mode != "sync":
                raise FailException(f"Router plan step {step.step_id} uses unsupported execution mode")
            if not allow_required_approval and step.required_approval:
                raise FailException(f"Router plan step {step.step_id} requires unsupported approval")

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

        self._validate_acyclic_dependencies({step.step_id: step.dependencies for step in plan.steps})
        return plan

    @staticmethod
    def _validate_acyclic_dependencies(dependencies_by_step: dict[str, list[str]]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            if step_id in visiting:
                raise FailException("Router plan dependencies contain a cycle")
            visiting.add(step_id)
            for dependency in dependencies_by_step.get(step_id, []):
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in dependencies_by_step:
            visit(step_id)
