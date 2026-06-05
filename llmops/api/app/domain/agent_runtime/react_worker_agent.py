import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.agent import AgentThought, QueueEvent
from app.domain.agent_runtime.protocols import AgentEvent, ArtifactRef, WorkerInvocation, WorkerResult
from app.models.account import Account
from app.models.agent import Agent, AgentVersion
from app.services.app_service import MAX_AGENT_ITERATION_RESPONSE, AppService


class ReActWorkerAgent:
    """Execute one worker step through a ReAct-style execution engine."""

    def __init__(self, *, app_service: AppService | None = None) -> None:
        self.app_service = app_service or AppService()

    def invoke(
        self,
        *,
        session: Session,
        worker: Agent,
        agent_version: AgentVersion | None,
        invocation: WorkerInvocation,
        account: Account,
    ) -> WorkerResult:
        if worker.target_ref_type == "app":
            return self._invoke_app_executor(
                session=session,
                worker=worker,
                agent_version=agent_version,
                invocation=invocation,
                account=account,
            )

        return self._failed_result(
            invocation,
            summary=f"Unsupported worker target: {worker.target_ref_type or 'empty'}",
            error_code="unsupported_worker_target",
            retryable=False,
        )

    def _invoke_app_executor(
        self,
        *,
        session: Session,
        worker: Agent,
        agent_version: AgentVersion | None,
        invocation: WorkerInvocation,
        account: Account,
    ) -> WorkerResult:
        try:
            app_id = uuid.UUID(worker.target_ref_id)
        except ValueError:
            return self._failed_result(
                invocation,
                summary="Worker app target ref is invalid.",
                error_code="invalid_worker_target",
                retryable=False,
            )

        task_text = self._task_text(invocation)
        image_urls = self._image_urls(invocation)
        conversation_id = self._conversation_id(invocation)
        runtime_policy = self._runtime_policy(agent_version, invocation)
        thoughts = list(
            self.app_service.run_app_worker(
                session,
                app_id=app_id,
                task_id=invocation.task_id,
                query=task_text,
                image_urls=image_urls,
                account=account,
                conversation_id=conversation_id,
                runtime_policy=runtime_policy,
            )
        )
        return self._result_from_thoughts(invocation, worker, agent_version, thoughts, runtime_policy)

    def _result_from_thoughts(
        self,
        invocation: WorkerInvocation,
        worker: Agent,
        agent_version: AgentVersion | None,
        thoughts: list[AgentThought],
        runtime_policy: dict[str, Any],
    ) -> WorkerResult:
        answer_parts: list[str] = []
        actions: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        artifacts: list[ArtifactRef] = []
        events: list[AgentEvent] = []
        used_capabilities: list[str] = []
        errors: list[dict[str, Any]] = []
        terminal_status = "succeeded"
        iterations = 0
        internal_steps: list[dict[str, Any]] = []
        terminal_raw_event_payload: dict[str, Any] = {}
        memory_compaction = self._memory_compaction(thoughts, runtime_policy)

        events.append(
            self._agent_event(
                invocation,
                event_type="worker.runtime.started",
                status="running",
                message=self._preview(self._task_text(invocation)),
                payload={
                    "runtime": self._runtime_payload(
                        final_state="running",
                        iterations=0,
                        runtime_policy=runtime_policy,
                    ),
                    "runtime_policy": runtime_policy,
                    "state": "preparing",
                    "worker_id": str(worker.id),
                    "worker_name": worker.name,
                    "task": self._preview(self._task_text(invocation), limit=500),
                },
            )
        )

        for thought in thoughts:
            payload = thought.model_dump(mode="json")
            raw_event_type = str(payload.get("event") or thought.event.value)
            message = str(payload.get("answer") or payload.get("observation") or payload.get("thought") or "")
            if raw_event_type == QueueEvent.AGENT_THOUGHT.value:
                iterations += 1
                events.append(
                    self._agent_event(
                        invocation,
                        event_type="worker.runtime.iteration_started",
                        status="running",
                        message=self._preview(message),
                        payload={
                            "runtime": self._runtime_payload(
                                final_state="running",
                                iterations=iterations,
                                runtime_policy=runtime_policy,
                            ),
                            "state": "reasoning",
                            "iteration": iterations,
                            "tool_calls": self._tool_calls_from_thought(thought.thought),
                            "raw_event": payload,
                        },
                    )
                )
                continue

            if raw_event_type in {QueueEvent.AGENT_ACTION.value, QueueEvent.DATASET_RETRIEVAL.value}:
                metadata = self._thought_metadata(thought)
                tool_call_id = str(thought.id)
                tool_name = thought.tool or raw_event_type
                internal_step_id = f"wstep_{len(internal_steps) + 1}"
                tool_kind = str(
                    metadata.get("executor_type")
                    or ("dataset" if raw_event_type == QueueEvent.DATASET_RETRIEVAL.value else "tool")
                )
                failed = self._tool_failed(thought)
                error_code = str(metadata.get("error_code") or ("tool_execution_failed" if failed else ""))
                tool_payload = {
                    "runtime": self._runtime_payload(
                        final_state="running",
                        iterations=iterations,
                        runtime_policy=runtime_policy,
                    ),
                    "state": "tool_calling",
                    "internal_step_id": internal_step_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "executor_type": tool_kind,
                    "tool_input": thought.tool_input or {},
                    "tool_input_preview": self._preview_json(thought.tool_input or {}),
                    "metadata": metadata,
                    "capability_kind": metadata.get("capability_kind", ""),
                    "target_ref_type": metadata.get("target_ref_type", ""),
                    "target_ref_id": metadata.get("target_ref_id", ""),
                    "workflow_nodes": metadata.get("workflow_nodes", []),
                    "failed_node": metadata.get("failed_node", {}),
                    "error_message": metadata.get("error_message", ""),
                    "raw_event_type": raw_event_type,
                    "raw_event": payload,
                }
                events.append(
                    self._agent_event(
                        invocation,
                        event_type="worker.tool.started",
                        status="running",
                        message=f"Calling {tool_name}",
                        payload={**tool_payload, "inferred": True},
                    )
                )
                terminal_tool_status = "failed" if failed else "succeeded"
                events.append(
                    self._agent_event(
                        invocation,
                        event_type=f"worker.tool.{terminal_tool_status}",
                        status=terminal_tool_status,
                        message=self._preview(thought.observation),
                        payload={
                            **tool_payload,
                            "state": "observing",
                            "observation": thought.observation,
                            "observation_preview": self._preview(thought.observation, limit=500),
                            "error_code": error_code,
                        },
                    )
                )
                internal_steps.append(
                    {
                        "internal_step_id": internal_step_id,
                        "goal": f"Call {tool_name}",
                        "status": terminal_tool_status,
                        "tool_call_ids": [tool_call_id],
                        "tool_name": tool_name,
                        "tool_kind": tool_kind,
                        "executor_type": tool_kind,
                        "error_code": error_code,
                    }
                )
            elif raw_event_type == QueueEvent.AGENT_MESSAGE.value:
                events.append(
                    self._agent_event(
                        invocation,
                        event_type="worker.runtime.state_changed",
                        status="running",
                        message=self._preview(message),
                        payload={
                            "runtime": self._runtime_payload(
                                final_state="running",
                                iterations=iterations,
                                runtime_policy=runtime_policy,
                            ),
                            "state": "summarizing",
                            "answer_preview": self._preview(thought.answer or thought.thought),
                            "raw_event": payload,
                        },
                    )
                )
            elif raw_event_type == QueueEvent.AGENT_END.value:
                terminal_raw_event_payload = payload
            elif raw_event_type in {QueueEvent.ERROR.value, QueueEvent.TIMEOUT.value}:
                terminal_raw_event_payload = payload
            elif raw_event_type == QueueEvent.STOP.value:
                terminal_raw_event_payload = payload
            else:
                events.append(
                    self._agent_event(
                        invocation,
                        event_type=raw_event_type,
                        status=self._event_status(raw_event_type),
                        message=message,
                        payload=payload,
                    )
                )

            if thought.answer:
                answer_parts.append(thought.answer)
            if raw_event_type in {QueueEvent.AGENT_ACTION.value, QueueEvent.DATASET_RETRIEVAL.value}:
                action = {
                    "event_type": "worker.tool.failed" if self._tool_failed(thought) else "worker.tool.succeeded",
                    "raw_event_type": raw_event_type,
                    "tool": thought.tool,
                    "tool_input": thought.tool_input,
                    "observation": thought.observation,
                    "metadata": self._thought_metadata(thought),
                }
                actions.append(action)
                if thought.tool:
                    used_capabilities.append(thought.tool)
            if thought.observation:
                evidence.append(
                    {
                        "event_type": "worker.tool.failed" if self._tool_failed(thought) else "worker.tool.succeeded",
                        "raw_event_type": raw_event_type,
                        "tool": thought.tool,
                        "observation": thought.observation,
                        "metadata": self._thought_metadata(thought),
                    }
                )

            artifacts.extend(self._artifact_refs(payload, invocation, worker))

            if raw_event_type == QueueEvent.ERROR.value:
                terminal_status = "failed"
                errors.append({"error_code": "worker_error", "message": thought.observation})
            elif raw_event_type == QueueEvent.TIMEOUT.value:
                terminal_status = "failed"
                errors.append({"error_code": "worker_timeout", "message": thought.observation})
            elif raw_event_type == QueueEvent.STOP.value:
                terminal_status = "cancelled"
            elif self._thought_waits_for_user(thought):
                terminal_status = "waiting_user"

        answer = "".join(answer_parts)
        failed_actions = [action for action in actions if action.get("event_type") == "worker.tool.failed"]
        if terminal_status == "succeeded" and self._max_iterations_exceeded(answer):
            terminal_status = "failed"
            errors.append(
                {
                    "error_code": "worker_max_iterations_exceeded",
                    "message": MAX_AGENT_ITERATION_RESPONSE,
                }
            )
        elif terminal_status == "succeeded" and self._has_missing_capability(failed_actions):
            terminal_status = "failed"
            errors.append(
                {
                    "error_code": "worker_capability_missing",
                    "message": self._first_failed_action_message(failed_actions),
                }
            )
        elif terminal_status == "succeeded" and not answer and failed_actions:
            terminal_status = "failed"
            first_failed_action = failed_actions[0]
            raw_metadata = first_failed_action.get("metadata")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            errors.append(
                {
                    "error_code": str(metadata.get("error_code") or "worker_tool_execution_failed"),
                    "message": self._first_failed_action_message(failed_actions),
                }
            )

        summary = answer or self._summary_from_evidence(evidence) or self._summary_from_errors(errors)
        replan_signal = self._replan_signal(
            terminal_status=terminal_status,
            errors=errors,
            failed_actions=failed_actions,
            summary=summary,
        )
        plan_feedback = self._plan_feedback(
            thoughts=thoughts,
            terminal_status=terminal_status,
            summary=summary,
            artifacts=artifacts,
            replan_signal=replan_signal,
        )
        if memory_compaction["enabled"]:
            events.append(self._memory_event(invocation, memory_compaction, runtime_policy, iterations))
        final_state = terminal_status if terminal_status in {"failed", "cancelled", "waiting_user"} else "completed"
        final_event_type = {
            "failed": "worker.runtime.failed",
            "cancelled": "worker.runtime.cancelled",
            "waiting_user": "worker.runtime.waiting_user",
        }.get(terminal_status, "worker.runtime.completed")
        final_message = {
            "failed": summary or "Worker runtime failed.",
            "cancelled": summary or "Worker runtime cancelled.",
            "waiting_user": summary or "Worker runtime is waiting for user input.",
        }.get(terminal_status, "Worker runtime completed.")
        events.append(
            self._agent_event(
                invocation,
                event_type=final_event_type,
                status="completed" if terminal_status == "succeeded" else terminal_status,
                message=self._preview(final_message),
                payload={
                    "runtime": self._runtime_payload(
                        final_state=final_state,
                        iterations=iterations,
                        runtime_policy=runtime_policy,
                    ),
                    "state": final_state,
                    "replan_signal": replan_signal,
                    "plan_feedback": plan_feedback,
                    "raw_event": terminal_raw_event_payload,
                    "inferred": not bool(terminal_raw_event_payload),
                },
            )
        )
        runtime = self._runtime_payload(
            final_state=terminal_status if terminal_status in {"failed", "cancelled", "waiting_user"} else "completed",
            iterations=iterations,
            runtime_policy=runtime_policy,
        )
        return WorkerResult(
            trace_id=invocation.trace_id,
            task_id=invocation.task_id,
            step_id=invocation.step_id,
            worker_id=invocation.worker_id,
            status=terminal_status,
            summary=summary,
            data={
                "answer": answer,
                "target_ref_type": worker.target_ref_type,
                "target_ref_id": worker.target_ref_id,
                "agent_version_id": str(agent_version.id) if agent_version else "",
                "thoughts": [thought.model_dump(mode="json") for thought in thoughts],
                "runtime": runtime,
                "internal_steps": internal_steps,
                "memory_compaction": memory_compaction,
                "replan_signal": replan_signal,
                "plan_feedback": plan_feedback,
            },
            evidence=evidence,
            artifacts=artifacts,
            actions=actions,
            events=events,
            retryable=terminal_status == "failed",
            error_code=errors[0]["error_code"] if errors else None,
            errors=errors,
            used_capabilities=sorted(set(used_capabilities)),
        )

    @staticmethod
    def _agent_event(
        invocation: WorkerInvocation,
        *,
        event_type: str,
        status: str,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> AgentEvent:
        return AgentEvent(
            trace_id=invocation.trace_id,
            task_id=invocation.task_id,
            step_id=invocation.step_id,
            worker_id=invocation.worker_id,
            event_type=event_type,
            status=status,
            message=message,
            payload=payload or {},
        )

    @staticmethod
    def _runtime_policy(agent_version: AgentVersion | None, invocation: WorkerInvocation) -> dict[str, Any]:
        worker_config = agent_version.worker_config if agent_version is not None else {}
        worker_config = worker_config if isinstance(worker_config, dict) else {}
        raw_policy: dict[str, Any] = {}
        for key in ("runtime_policy", "runtime"):
            value = worker_config.get(key)
            if isinstance(value, dict):
                raw_policy.update(value)
        for key in (
            "max_iterations",
            "max_iteration_count",
            "allow_tool_calls",
            "allow_builtin_tools",
            "allow_tools",
            "allow_api",
            "allow_api_tools",
            "allow_workflow",
            "allow_workflows",
            "allow_dataset",
            "allow_datasets",
            "allow_knowledge_base",
            "allow_rag",
            "allow_mcp",
            "allow_sandbox",
            "allowed_executor_types",
            "executor_types",
            "memory_compaction",
        ):
            if key in worker_config:
                raw_policy[key] = worker_config[key]
        invocation_policy = invocation.execution_policy.get("runtime_policy")
        if isinstance(invocation_policy, dict):
            raw_policy.update(invocation_policy)
        return AppService.normalize_worker_runtime_policy(raw_policy)

    @staticmethod
    def _runtime_payload(
        *,
        final_state: str,
        iterations: int,
        runtime_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "mode": "worker_react_v1",
            "max_iterations": int(runtime_policy.get("max_iterations") or 5),
            "iterations": iterations,
            "final_state": final_state,
            "policy": {
                "allowed_executor_types": runtime_policy.get("allowed_executor_types", []),
                "allow_tool_calls": bool(runtime_policy.get("allow_tool_calls", True)),
            },
        }

    @staticmethod
    def _thought_metadata(thought: AgentThought) -> dict[str, Any]:
        metadata = thought.metadata if isinstance(thought.metadata, dict) else {}
        return metadata

    def _memory_compaction(self, thoughts: list[AgentThought], runtime_policy: dict[str, Any]) -> dict[str, Any]:
        raw_policy = runtime_policy.get("memory_compaction")
        policy = raw_policy if isinstance(raw_policy, dict) else {}
        max_items = int(policy.get("max_items") or 20)
        max_observation_chars = int(policy.get("max_observation_chars") or 500)
        max_message_chars = int(policy.get("max_message_chars") or 1000)
        items: list[dict[str, Any]] = []
        truncated_observations = 0
        truncated_messages = 0
        for thought in thoughts[-max_items:]:
            observation = thought.observation or thought.answer or thought.thought
            observation_preview = self._preview(observation, limit=max_observation_chars)
            if len(str(observation or "")) > max_observation_chars:
                truncated_observations += 1
            message_preview = self._preview_json(thought.message, limit=max_message_chars) if thought.message else ""
            message_text = self._json_text(thought.message) if thought.message else ""
            if message_text and len(message_text) > max_message_chars:
                truncated_messages += 1
            items.append(
                {
                    "event": thought.event.value,
                    "tool": thought.tool,
                    "executor_type": self._thought_metadata(thought).get("executor_type", ""),
                    "status": self._thought_metadata(thought).get("status", ""),
                    "observation_preview": observation_preview,
                    "message_preview": message_preview,
                    "truncated": len(str(observation or "")) > max_observation_chars,
                }
            )
        summary_parts = []
        for item in items:
            label = item["tool"] or item["event"]
            preview = item["observation_preview"]
            if preview:
                summary_parts.append(f"{label}: {preview}")
        return {
            "schema_version": "worker_memory_compaction_v1",
            "enabled": bool(policy.get("enabled", True)),
            "strategy": "recent_event_preview",
            "input_event_count": len(thoughts),
            "retained_event_count": len(items),
            "truncated_event_count": max(0, len(thoughts) - len(items)),
            "truncated_observation_count": truncated_observations,
            "truncated_message_count": truncated_messages,
            "limits": {
                "max_items": max_items,
                "max_observation_chars": max_observation_chars,
                "max_message_chars": max_message_chars,
            },
            "summary": self._preview("\n".join(summary_parts), limit=1200),
            "items": items,
        }

    def _memory_event(
        self,
        invocation: WorkerInvocation,
        memory_compaction: dict[str, Any],
        runtime_policy: dict[str, Any],
        iterations: int,
    ) -> AgentEvent:
        return self._agent_event(
            invocation,
            event_type="worker.memory.compacted",
            status="completed",
            message=self._preview(memory_compaction.get("summary"), limit=260),
            payload={
                "runtime": self._runtime_payload(
                    final_state="running",
                    iterations=iterations,
                    runtime_policy=runtime_policy,
                ),
                "state": "memory_compacted",
                "memory_compaction": memory_compaction,
            },
        )

    @staticmethod
    def _tool_calls_from_thought(thought: str) -> list[dict[str, Any]]:
        if not thought:
            return []
        try:
            payload = json.loads(thought)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _tool_failed(thought: AgentThought) -> bool:
        metadata = thought.metadata if isinstance(thought.metadata, dict) else {}
        if metadata.get("status") == "failed" or metadata.get("error_code"):
            return True
        observation = (thought.observation or "").strip().lower()
        return bool(
            observation.startswith("tool does not exist:")
            or "execution failed:" in observation
            or observation.startswith("tool execution failed")
            or observation.startswith("workflow execution failed")
            or observation.startswith("api execution failed")
            or observation.startswith("dataset execution failed")
            or observation.startswith("unsupported capability type:")
        )

    @staticmethod
    def _thought_waits_for_user(thought: AgentThought) -> bool:
        metadata = thought.metadata if isinstance(thought.metadata, dict) else {}
        if metadata.get("status") == "waiting_user" or metadata.get("requires_user_input"):
            return True
        if thought.tool in {"message_ask_user", "ask_user"}:
            return True
        tool_input = thought.tool_input if isinstance(thought.tool_input, dict) else {}
        return bool(tool_input.get("requires_user_input"))

    @staticmethod
    def _max_iterations_exceeded(answer: str) -> bool:
        return MAX_AGENT_ITERATION_RESPONSE.lower() in str(answer or "").lower()

    @staticmethod
    def _has_missing_capability(failed_actions: list[dict[str, Any]]) -> bool:
        return any(
            str(ReActWorkerAgent._action_metadata(action).get("error_code") or "") == "worker_capability_missing"
            or str(action.get("observation") or "").strip().lower().startswith("tool does not exist:")
            for action in failed_actions
        )

    @staticmethod
    def _first_failed_action_message(failed_actions: list[dict[str, Any]]) -> str:
        if not failed_actions:
            return ""
        return str(failed_actions[0].get("observation") or failed_actions[0].get("tool") or "Worker tool failed")

    @staticmethod
    def _replan_signal(
        *,
        terminal_status: str,
        errors: list[dict[str, Any]],
        failed_actions: list[dict[str, Any]],
        summary: str,
    ) -> dict[str, Any]:
        error_code = str(errors[0].get("error_code") or "") if errors else ""
        failed_tools = [
            {
                "tool": str(action.get("tool") or ""),
                "executor_type": str(ReActWorkerAgent._action_metadata(action).get("executor_type") or ""),
                "error_code": str(ReActWorkerAgent._action_metadata(action).get("error_code") or ""),
                "message": str(action.get("observation") or ""),
            }
            for action in failed_actions
        ]
        needs_replan = terminal_status == "failed"
        reason = error_code
        missing_info: list[str] = []
        suggested_worker_tags: list[str] = []
        if error_code == "worker_max_iterations_exceeded":
            reason = "max_iterations_exceeded"
            suggested_worker_tags.append("decompose_task")
        elif error_code == "worker_capability_missing":
            reason = "worker_capability_missing"
            suggested_worker_tags.extend([item["tool"] for item in failed_tools if item["tool"]])
        elif terminal_status == "failed":
            reason = error_code or "worker_failed"
            suggested_worker_tags.extend(
                [item["executor_type"] for item in failed_tools if item["executor_type"]]
            )
        return {
            "schema_version": "worker_replan_signal_v1",
            "needs_replan": needs_replan,
            "reason": reason,
            "missing_info": missing_info,
            "suggested_worker_tags": sorted(set(suggested_worker_tags)),
            "failed_tools": failed_tools,
            "summary": summary,
        }

    @staticmethod
    def _plan_feedback(
        *,
        thoughts: list[AgentThought],
        terminal_status: str,
        summary: str,
        artifacts: list[ArtifactRef],
        replan_signal: dict[str, Any],
    ) -> dict[str, Any]:
        for thought in reversed(thoughts):
            metadata = thought.metadata if isinstance(thought.metadata, dict) else {}
            raw_feedback = metadata.get("plan_feedback")
            if isinstance(raw_feedback, dict):
                feedback = dict(raw_feedback)
                feedback.setdefault("schema_version", "worker_plan_feedback_v1")
                feedback.setdefault("summary", summary)
                return feedback
        missing_info = replan_signal.get("missing_info") if isinstance(replan_signal, dict) else []
        return {
            "schema_version": "worker_plan_feedback_v1",
            "needs_plan_update": False,
            "completed_enough": False,
            "reason_code": "waiting_user" if terminal_status == "waiting_user" else "",
            "summary": summary,
            "missing_info": missing_info if isinstance(missing_info, list) else [],
            "suggested_worker_tags": [],
            "suggested_next_steps": [],
            "artifact_refs": [artifact.model_dump(mode="json") for artifact in artifacts],
            "confidence": None,
        }

    @staticmethod
    def _action_metadata(action: dict[str, Any]) -> dict[str, Any]:
        metadata = action.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _preview(value: Any, *, limit: int = 260) -> str:
        text = str(value or "")
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _preview_json(value: Any, *, limit: int = 260) -> str:
        if value in (None, {}, []):
            return ""
        text = ReActWorkerAgent._json_text(value)
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _json_text(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            return str(value)

    @staticmethod
    def _task_text(invocation: WorkerInvocation) -> str:
        task = invocation.task
        base_text = str(
            task.get("task")
            or task.get("query")
            or task.get("input")
            or task.get("message")
            or task.get("user_input", {}).get("query")
            or f"Run worker {invocation.worker_id}"
        )
        context_parts = ReActWorkerAgent._input_files_context(invocation.context.get("input_files"))
        artifact_parts = ReActWorkerAgent._artifacts_context(invocation.context.get("artifacts"))
        contract_parts = ReActWorkerAgent._task_contract_context(invocation.task)
        suffix = "\n\n".join(part for part in [contract_parts, context_parts, artifact_parts] if part)
        return f"{base_text}\n\n{suffix}" if suffix else base_text

    @staticmethod
    def _task_contract_context(task: dict[str, Any]) -> str:
        if not isinstance(task, dict):
            return ""
        lines = []
        expected_output = str(task.get("expected_output") or "").strip()
        if expected_output:
            lines.append(f"Expected output: {expected_output}")
        success_criteria = task.get("success_criteria")
        if isinstance(success_criteria, list) and success_criteria:
            lines.append("Success criteria:")
            lines.extend(f"- {item}" for item in success_criteria if str(item).strip())
        required_artifacts = task.get("required_artifacts")
        if isinstance(required_artifacts, list) and required_artifacts:
            lines.append("Required artifacts:")
            lines.extend(f"- {item}" for item in required_artifacts if str(item).strip())
        handoff_context = str(task.get("handoff_context") or "").strip()
        if handoff_context:
            lines.append(f"Handoff context: {handoff_context}")
        return "\n".join(lines)

    @staticmethod
    def _input_files_context(input_files: Any) -> str:
        if not isinstance(input_files, list) or not input_files:
            return ""
        parts = ["Input files:"]
        for index, item in enumerate(input_files, 1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("file_id") or f"file_{index}")
            file_id = str(item.get("file_id") or item.get("id") or "")
            mime_type = str(item.get("mime_type") or "")
            header = f"- {name}"
            if file_id:
                header += f" (file_id: {file_id})"
            if mime_type:
                header += f" [{mime_type}]"
            parts.append(header)
            content = item.get("content")
            if content:
                truncated = " [truncated]" if item.get("content_truncated") else ""
                parts.append(f"  content{truncated}:\n{content}")
        return "\n".join(parts) if len(parts) > 1 else ""

    @staticmethod
    def _artifacts_context(artifacts: Any) -> str:
        if not isinstance(artifacts, list) or not artifacts:
            return ""
        parts = ["Available upstream artifacts:"]
        for index, item in enumerate(artifacts, 1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("artifact_id") or item.get("file_id") or f"artifact_{index}")
            file_id = str(item.get("file_id") or "")
            summary = str(item.get("summary") or "")
            line = f"- {name}"
            if file_id:
                line += f" (file_id: {file_id})"
            if summary:
                line += f": {summary}"
            parts.append(line)
        return "\n".join(parts) if len(parts) > 1 else ""

    @staticmethod
    def _image_urls(invocation: WorkerInvocation) -> list[str]:
        value = invocation.context.get("image_urls") or invocation.task.get("image_urls") or []
        return [str(item) for item in value if item][:5] if isinstance(value, list) else []

    @staticmethod
    def _conversation_id(invocation: WorkerInvocation) -> uuid.UUID | None:
        value = invocation.context.get("conversation_id") if isinstance(invocation.context, dict) else None
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None

    @staticmethod
    def _event_status(event_type: str) -> str:
        if event_type in {QueueEvent.ERROR.value, QueueEvent.TIMEOUT.value}:
            return "failed"
        if event_type == QueueEvent.STOP.value:
            return "cancelled"
        if event_type == QueueEvent.AGENT_END.value:
            return "completed"
        return "running"

    @staticmethod
    def _artifact_refs(payload: dict[str, Any], invocation: WorkerInvocation, worker: Agent) -> list[ArtifactRef]:
        raw_items = payload.get("artifacts") or payload.get("attachments") or []
        if not isinstance(raw_items, list):
            return []

        refs: list[ArtifactRef] = []
        for item in raw_items:
            if isinstance(item, dict):
                refs.append(
                    ArtifactRef(
                        **{
                            **item,
                            "task_id": item.get("task_id") or str(invocation.task_id),
                            "step_id": item.get("step_id") or (str(invocation.step_id) if invocation.step_id else None),
                            "worker_id": item.get("worker_id") or str(worker.id),
                        }
                    )
                )
            elif item:
                refs.append(
                    ArtifactRef(
                        name=str(item),
                        task_id=str(invocation.task_id),
                        step_id=str(invocation.step_id) if invocation.step_id else None,
                        worker_id=str(worker.id),
                    )
                )
        return refs

    @staticmethod
    def _summary_from_evidence(evidence: list[dict[str, Any]]) -> str:
        if not evidence:
            return ""
        return str(evidence[-1].get("observation") or "")[:500]

    @staticmethod
    def _summary_from_errors(errors: list[dict[str, Any]]) -> str:
        if not errors:
            return ""
        return str(errors[0].get("message") or errors[0].get("error_code") or "")

    @staticmethod
    def _failed_result(
        invocation: WorkerInvocation,
        *,
        summary: str,
        error_code: str,
        retryable: bool,
    ) -> WorkerResult:
        return WorkerResult(
            trace_id=invocation.trace_id,
            task_id=invocation.task_id,
            step_id=invocation.step_id,
            worker_id=invocation.worker_id,
            status="failed",
            summary=summary,
            retryable=retryable,
            error_code=error_code,
            errors=[{"error_code": error_code, "message": summary}],
        )
