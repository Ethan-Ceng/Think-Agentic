import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.agent import AgentThought, QueueEvent
from app.domain.agent_runtime.protocols import AgentEvent, ArtifactRef, WorkerInvocation, WorkerResult
from app.models.account import Account
from app.models.agent import Agent, AgentVersion
from app.services.app_service import AppService


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
        thoughts = list(
            self.app_service.run_app_worker(
                session,
                app_id=app_id,
                task_id=invocation.task_id,
                query=task_text,
                image_urls=image_urls,
                account=account,
            )
        )
        return self._result_from_thoughts(invocation, worker, agent_version, thoughts)

    def _result_from_thoughts(
        self,
        invocation: WorkerInvocation,
        worker: Agent,
        agent_version: AgentVersion | None,
        thoughts: list[AgentThought],
    ) -> WorkerResult:
        answer_parts: list[str] = []
        actions: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        artifacts: list[ArtifactRef] = []
        events: list[AgentEvent] = []
        used_capabilities: list[str] = []
        errors: list[dict[str, Any]] = []
        terminal_status = "succeeded"

        for thought in thoughts:
            payload = thought.model_dump(mode="json")
            event_type = str(payload.get("event") or thought.event.value)
            message = str(payload.get("answer") or payload.get("observation") or payload.get("thought") or "")
            events.append(
                AgentEvent(
                    trace_id=invocation.trace_id,
                    task_id=invocation.task_id,
                    step_id=invocation.step_id,
                    worker_id=invocation.worker_id,
                    event_type=event_type,
                    status=self._event_status(event_type),
                    message=message,
                    payload=payload,
                )
            )

            if thought.answer:
                answer_parts.append(thought.answer)
            if event_type in {QueueEvent.AGENT_ACTION.value, QueueEvent.DATASET_RETRIEVAL.value}:
                action = {
                    "event_type": event_type,
                    "tool": thought.tool,
                    "tool_input": thought.tool_input,
                    "observation": thought.observation,
                }
                actions.append(action)
                if thought.tool:
                    used_capabilities.append(thought.tool)
            if thought.observation:
                evidence.append(
                    {
                        "event_type": event_type,
                        "tool": thought.tool,
                        "observation": thought.observation,
                    }
                )

            artifacts.extend(self._artifact_refs(payload, invocation, worker))

            if event_type == QueueEvent.ERROR.value:
                terminal_status = "failed"
                errors.append({"error_code": "worker_error", "message": thought.observation})
            elif event_type == QueueEvent.TIMEOUT.value:
                terminal_status = "failed"
                errors.append({"error_code": "worker_timeout", "message": thought.observation})
            elif event_type == QueueEvent.STOP.value:
                terminal_status = "cancelled"

        answer = "".join(answer_parts)
        summary = answer or self._summary_from_evidence(evidence) or self._summary_from_errors(errors)
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
        suffix = "\n\n".join(part for part in [context_parts, artifact_parts] if part)
        return f"{base_text}\n\n{suffix}" if suffix else base_text

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
