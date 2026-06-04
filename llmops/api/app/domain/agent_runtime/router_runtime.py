from uuid import UUID

from app.core.exceptions import FailException
from app.domain.agent_runtime.capability import normalize_routing_policy, user_message_for_error
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

    def preflight_plan(
        self,
        plan: RouterPlan,
        *,
        worker_capabilities: dict[str, dict] | None = None,
        user_input: dict | None = None,
        routing_policy: dict | None = None,
    ) -> dict:
        policy = normalize_routing_policy(routing_policy)
        capability_map = worker_capabilities or {}
        input_modalities = self._input_modalities(user_input or {})
        query = self._query(user_input or {})
        results = []
        for step in plan.steps:
            capability = capability_map.get(step.worker_id) or {}
            checks = []
            checks.extend(self._preflight_image_checks(step.worker_id, capability, input_modalities))
            checks.extend(self._preflight_search_checks(step.worker_id, capability, query, policy))
            passed = all(check["passed"] for check in checks)
            results.append(
                {
                    "step_id": step.step_id,
                    "worker_id": step.worker_id,
                    "passed": passed,
                    "status": "succeeded" if passed else "failed",
                    "checks": checks,
                    "capability_snapshot": capability,
                }
            )
        failed_results = [result for result in results if not result["passed"]]
        return {
            "status": "failed" if failed_results else "succeeded",
            "results": results,
            "suggested_worker_ids": self._suggested_worker_ids(failed_results, capability_map),
        }

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

    @classmethod
    def _preflight_image_checks(
        cls,
        worker_id: str,
        capability: dict,
        input_modalities: list[str],
    ) -> list[dict]:
        if not cls._has_image_input(input_modalities):
            return []

        worker_input_modalities = cls._list(capability.get("input_modalities"))
        worker_model_features = cls._list(capability.get("model_features"))
        supports_image_modality = cls._has_image_input(worker_input_modalities)
        supports_image_model = "image_input" in worker_model_features
        if supports_image_modality and not supports_image_model:
            return [
                cls._check(
                    rule_id="image_requires_model_support",
                    worker_id=worker_id,
                    passed=False,
                    error_code="worker_model_unsupported:image_input",
                )
            ]
        return [
            cls._check(
                rule_id="image_requires_vision",
                worker_id=worker_id,
                passed=supports_image_modality and supports_image_model,
                error_code=(
                    None
                    if supports_image_modality and supports_image_model
                    else "capability_missing:image_input"
                ),
            )
        ]

    @classmethod
    def _preflight_search_checks(
        cls,
        worker_id: str,
        capability: dict,
        query: str,
        routing_policy: dict,
    ) -> list[dict]:
        if not cls._search_required(query, routing_policy):
            return []
        semantic_tags = cls._list(capability.get("semantic_tags"))
        passed = "search" in semantic_tags
        return [
            cls._check(
                rule_id="latest_info_requires_search",
                worker_id=worker_id,
                passed=passed,
                error_code=None if passed else "capability_missing:search",
            )
        ]

    @staticmethod
    def _check(
        *,
        rule_id: str,
        worker_id: str,
        passed: bool,
        error_code: str | None,
    ) -> dict:
        return {
            "rule_id": rule_id,
            "worker_id": worker_id,
            "passed": passed,
            "error_code": error_code,
            "user_message": user_message_for_error(error_code or "") if error_code else "",
        }

    @classmethod
    def _input_modalities(cls, user_input: dict) -> list[str]:
        modalities = ["text/plain"]
        explicit = user_input.get("input_modalities")
        if isinstance(explicit, list):
            modalities.extend(str(item) for item in explicit)
        image_urls = user_input.get("image_urls")
        if isinstance(image_urls, list) and image_urls:
            modalities.extend(["image/png", "image/jpeg", "image/webp"])
        return cls._unique(modalities)

    @staticmethod
    def _query(user_input: dict) -> str:
        return str(user_input.get("query") or user_input.get("input") or user_input.get("message") or "")

    @classmethod
    def _search_required(cls, query: str, routing_policy: dict) -> bool:
        lowered = query.lower()
        rules = routing_policy.get("rules") if isinstance(routing_policy.get("rules"), list) else []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            require = rule.get("require") if isinstance(rule.get("require"), dict) else {}
            required_tags = cls._list(require.get("semantic_tags_any"))
            if "search" not in required_tags:
                continue
            when = rule.get("when") if isinstance(rule.get("when"), dict) else {}
            keywords = cls._list(when.get("intent_keywords_any"))
            if not keywords or any(keyword.lower() in lowered for keyword in keywords):
                return True
        return False

    @classmethod
    def _suggested_worker_ids(cls, failed_results: list[dict], capability_map: dict[str, dict]) -> list[str]:
        if not failed_results:
            return []
        needed_search = any(
            check.get("error_code") == "capability_missing:search"
            for result in failed_results
            for check in result.get("checks", [])
        )
        needed_image = any(
            check.get("error_code") in {"capability_missing:image_input", "worker_model_unsupported:image_input"}
            for result in failed_results
            for check in result.get("checks", [])
        )
        suggestions = []
        for worker_id, capability in capability_map.items():
            tags = cls._list(capability.get("semantic_tags"))
            inputs = cls._list(capability.get("input_modalities"))
            features = cls._list(capability.get("model_features"))
            if needed_search and "search" not in tags:
                continue
            if needed_image and not (cls._has_image_input(inputs) and "image_input" in features):
                continue
            suggestions.append(worker_id)
        return suggestions

    @staticmethod
    def _has_image_input(modalities: list[str]) -> bool:
        return any(item in {"image/*", "image/png", "image/jpeg", "image/jpg", "image/webp"} for item in modalities)

    @staticmethod
    def _list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result = []
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result
