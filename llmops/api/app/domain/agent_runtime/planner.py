import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.core.language_model.chat_runtime import ChatCompletionRuntime
from app.core.language_model.entities import BaseLanguageModel
from app.domain.agent_runtime.protocols import RouterPlan


@dataclass(frozen=True)
class PlannerWorkerDescriptor:
    worker_id: str
    name: str
    description: str
    runtime_type: str
    product_category: str
    target_ref_type: str
    target_ref_id: str
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    config_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannerInput:
    router_id: str
    query: str
    conversation_id: str | None = None
    message_id: str | None = None
    input_files: list[dict[str, Any]] = field(default_factory=list)
    recent_history: list[dict[str, Any]] = field(default_factory=list)
    workers: list[PlannerWorkerDescriptor] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannerReplanInput:
    router_id: str
    original_query: str
    current_plan: dict[str, Any]
    failed_step: dict[str, Any]
    failure: dict[str, Any]
    completed_steps: list[dict[str, Any]]
    workers: list[PlannerWorkerDescriptor] = field(default_factory=list)
    input_files: list[dict[str, Any]] = field(default_factory=list)
    recent_history: list[dict[str, Any]] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1


@dataclass(frozen=True)
class PlannerResult:
    plan: RouterPlan | None
    raw_output: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.plan is not None and not self.error


class PlannerPromptBuilder:
    def build_system_prompt(self) -> str:
        return "\n".join(
            [
                "You are a Router Planner for an enterprise LLMOps platform.",
                "You create a RouterPlan only. You do not execute tools or worker tasks.",
                "Use only worker_id values from the provided worker list.",
                "Return exactly one JSON object and no natural-language explanation.",
            ]
        )

    def build_user_prompt(self, planner_input: PlannerInput) -> str:
        constraints = {
            "allow_parallel": False,
            "allow_replan": False,
            "allow_required_approval": False,
            "execution_mode": "sync",
            "max_steps": 5,
            **planner_input.constraints,
        }
        payload = {
            "router_id": planner_input.router_id,
            "user_query": planner_input.query,
            "conversation_id": planner_input.conversation_id,
            "message_id": planner_input.message_id,
            "input_files": planner_input.input_files,
            "recent_history": planner_input.recent_history,
            "workers": [worker.__dict__ for worker in planner_input.workers],
            "constraints": constraints,
            "required_output_schema": {
                "schema_version": "router_plan_v1",
                "router_id": planner_input.router_id,
                "user_intent": "string",
                "risk_assessment": {
                    "risk_level": "low|medium|high",
                    "source": "llm_planner_v1",
                },
                "steps": [
                    {
                        "step_id": "step_1",
                        "worker_id": "one provided worker_id",
                        "task": "clear executable subtask for that worker",
                        "dependencies": [],
                        "execution_mode": "sync",
                        "required_approval": False,
                    }
                ],
                "final_response_policy": {"mode": "summarize_worker_results"},
            },
        }
        return (
            "Create the smallest valid sequential plan for this user request.\n"
            "If one worker can do the job, use one step. If multiple workers are needed, "
            "make later tasks explain how to use previous results.\n"
            "Use recent_history to resolve short follow-up requests, and make each worker task explicit.\n"
            "Input files are references only; do not pretend to have read unavailable content.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )

    def build_replan_user_prompt(self, replan_input: PlannerReplanInput) -> str:
        constraints = {
            "allow_parallel": False,
            "allow_replan": True,
            "allow_required_approval": False,
            "execution_mode": "sync",
            "max_steps": 5,
            "attempt": replan_input.attempt,
            **replan_input.constraints,
        }
        step_prefix = f"replan_{replan_input.attempt}_step_"
        payload = {
            "router_id": replan_input.router_id,
            "original_query": replan_input.original_query,
            "current_plan": replan_input.current_plan,
            "failed_step": replan_input.failed_step,
            "failure": replan_input.failure,
            "completed_steps": replan_input.completed_steps,
            "input_files": replan_input.input_files,
            "recent_history": replan_input.recent_history,
            "workers": [worker.__dict__ for worker in replan_input.workers],
            "constraints": constraints,
            "required_output_schema": {
                "schema_version": "router_plan_v1",
                "router_id": replan_input.router_id,
                "user_intent": "string",
                "risk_assessment": {
                    "risk_level": "low|medium|high",
                    "source": "llm_replan_v1",
                },
                "steps": [
                    {
                        "step_id": f"{step_prefix}1",
                        "worker_id": "one provided worker_id",
                        "task": "remaining or replacement subtask for that worker",
                        "dependencies": [],
                        "execution_mode": "sync",
                        "required_approval": False,
                    }
                ],
                "final_response_policy": {"mode": "summarize_worker_results"},
            },
        }
        return (
            "Create a replacement RouterPlan for the failed or remaining work only.\n"
            "Use only worker_id values from the provided workers list. Do not use the failed worker "
            "when another suitable worker is available.\n"
            f"Use unique step_id values beginning with {step_prefix}.\n"
            "Do not depend on step ids from the previous plan; completed step outputs and artifacts "
            "will be provided as execution context.\n"
            "Return exactly one JSON object and no explanation.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )


class RouterPlannerAgent:
    def __init__(
        self,
        *,
        chat_runtime: ChatCompletionRuntime | None = None,
        prompt_builder: PlannerPromptBuilder | None = None,
    ) -> None:
        self.chat_runtime = chat_runtime or ChatCompletionRuntime()
        self.prompt_builder = prompt_builder or PlannerPromptBuilder()

    def create_plan(
        self,
        *,
        model: BaseLanguageModel,
        planner_input: PlannerInput,
        timeout: float = 60.0,
    ) -> PlannerResult:
        started_at = time.monotonic()
        try:
            response = self.chat_runtime.create_response(
                model=model,
                system_prompt=self.prompt_builder.build_system_prompt(),
                query=self.prompt_builder.build_user_prompt(planner_input),
                response_format={"type": "json_object"},
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            return PlannerResult(
                plan=None,
                latency_ms=self._latency_ms(started_at),
                error=f"planner_request_failed: {exc}",
            )

        raw_output = response.content.strip()
        try:
            payload = self._parse_json_object(raw_output)
            plan = RouterPlan.model_validate(payload)
            plan = self._normalize_plan(plan, planner_input.router_id)
        except (ValueError, ValidationError) as exc:
            return PlannerResult(
                plan=None,
                raw_output=raw_output,
                usage=response.usage,
                latency_ms=self._latency_ms(started_at),
                error=f"planner_output_invalid: {exc}",
            )

        return PlannerResult(
            plan=plan,
            raw_output=raw_output,
            usage=response.usage,
            latency_ms=self._latency_ms(started_at),
        )

    def update_plan(
        self,
        *,
        model: BaseLanguageModel,
        replan_input: PlannerReplanInput,
        timeout: float = 60.0,
    ) -> PlannerResult:
        started_at = time.monotonic()
        try:
            response = self.chat_runtime.create_response(
                model=model,
                system_prompt=self.prompt_builder.build_system_prompt(),
                query=self.prompt_builder.build_replan_user_prompt(replan_input),
                response_format={"type": "json_object"},
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            return PlannerResult(
                plan=None,
                latency_ms=self._latency_ms(started_at),
                error=f"planner_replan_request_failed: {exc}",
            )

        raw_output = response.content.strip()
        try:
            payload = self._parse_json_object(raw_output)
            plan = RouterPlan.model_validate(payload)
            plan = self._normalize_replan_plan(plan, replan_input.router_id, replan_input.attempt)
        except (ValueError, ValidationError) as exc:
            return PlannerResult(
                plan=None,
                raw_output=raw_output,
                usage=response.usage,
                latency_ms=self._latency_ms(started_at),
                error=f"planner_replan_output_invalid: {exc}",
            )

        return PlannerResult(
            plan=plan,
            raw_output=raw_output,
            usage=response.usage,
            latency_ms=self._latency_ms(started_at),
        )

    @classmethod
    def _parse_json_object(cls, raw_output: str) -> dict[str, Any]:
        text = cls._strip_json_fence(raw_output)
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("Planner output must be a JSON object")
        return value

    @staticmethod
    def _strip_json_fence(text: str) -> str:
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _normalize_plan(plan: RouterPlan, router_id: str) -> RouterPlan:
        data = plan.model_dump(mode="json")
        data["router_id"] = router_id
        risk_assessment = data.get("risk_assessment") if isinstance(data.get("risk_assessment"), dict) else {}
        risk_assessment["source"] = risk_assessment.get("source") or "llm_planner_v1"
        data["risk_assessment"] = risk_assessment
        if not isinstance(data.get("final_response_policy"), dict):
            data["final_response_policy"] = {"mode": "summarize_worker_results"}
        elif not data["final_response_policy"].get("mode"):
            data["final_response_policy"]["mode"] = "summarize_worker_results"
        return RouterPlan.model_validate(data)

    @classmethod
    def _normalize_replan_plan(cls, plan: RouterPlan, router_id: str, attempt: int) -> RouterPlan:
        normalized = cls._normalize_plan(plan, router_id)
        data = normalized.model_dump(mode="json")
        risk_assessment = data.get("risk_assessment") if isinstance(data.get("risk_assessment"), dict) else {}
        risk_assessment["source"] = "llm_replan_v1"
        data["risk_assessment"] = risk_assessment

        prefix = f"replan_{attempt}_step_"
        steps = data.get("steps") if isinstance(data.get("steps"), list) else []
        step_id_map: dict[str, str] = {}
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            original_step_id = str(step.get("step_id") or f"step_{index}")
            next_step_id = original_step_id if original_step_id.startswith(prefix) else f"{prefix}{index}"
            step_id_map[original_step_id] = next_step_id
            step["step_id"] = next_step_id

        valid_step_ids = {str(step.get("step_id")) for step in steps if isinstance(step, dict)}
        for step in steps:
            if not isinstance(step, dict):
                continue
            dependencies = step.get("dependencies") if isinstance(step.get("dependencies"), list) else []
            rewritten_dependencies = [step_id_map.get(str(dep), str(dep)) for dep in dependencies]
            step["dependencies"] = [dep for dep in rewritten_dependencies if dep in valid_step_ids]
        return RouterPlan.model_validate(data)

    @staticmethod
    def _latency_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
