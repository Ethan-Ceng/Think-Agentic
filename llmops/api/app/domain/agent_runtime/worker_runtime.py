from sqlalchemy.orm import Session

from app.domain.agent_runtime.protocols import WorkerInvocation, WorkerResult
from app.domain.agent_runtime.react_worker_agent import ReActWorkerAgent
from app.models.account import Account
from app.models.agent import Agent, AgentVersion
from app.services.app_service import AppService


class WorkerRuntime:
    """Dispatch WorkerInvocation to the configured execution engine."""

    def __init__(
        self,
        *,
        react_worker_agent: ReActWorkerAgent | None = None,
        app_service: AppService | None = None,
    ) -> None:
        self.react_worker_agent = react_worker_agent or ReActWorkerAgent(app_service=app_service)

    def invoke(
        self,
        invocation: WorkerInvocation,
        *,
        session: Session | None = None,
        worker: Agent | None = None,
        account: Account | None = None,
        agent_version: AgentVersion | None = None,
    ) -> WorkerResult:
        if session is None or worker is None or account is None:
            return self._failed_result(
                invocation,
                summary="Worker runtime context is incomplete.",
                error_code="runtime_context_missing",
                retryable=False,
            )

        resolved_version = agent_version or self._resolve_agent_version(session, worker)
        execution_agent_type = self._execution_agent_type(worker, resolved_version)
        if execution_agent_type == "react_worker":
            return self.react_worker_agent.invoke(
                session=session,
                worker=worker,
                agent_version=resolved_version,
                invocation=invocation,
                account=account,
            )

        return self._failed_result(
            invocation,
            summary=f"Unsupported worker execution agent type: {execution_agent_type}",
            error_code="unsupported_execution_agent_type",
            retryable=False,
        )

    @staticmethod
    def _resolve_agent_version(session: Session, worker: Agent) -> AgentVersion | None:
        version_id = worker.published_version_id or worker.draft_version_id
        if version_id is not None:
            return session.get(AgentVersion, version_id)
        return None

    @staticmethod
    def _execution_agent_type(worker: Agent, agent_version: AgentVersion | None) -> str:
        worker_config = agent_version.worker_config if agent_version is not None else {}
        configured_type = str(
            worker_config.get("executor_type")
            or worker_config.get("execution_agent_type")
            or worker_config.get("worker_runtime")
            or ""
        )
        if configured_type:
            if configured_type == "app":
                return "react_worker"
            if configured_type == "a2a":
                return "a2a_worker"
            return configured_type
        if worker.target_ref_type == "app":
            return "react_worker"
        if worker.target_ref_type == "a2a_agent":
            return "a2a_worker"
        return "unsupported_worker"

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
