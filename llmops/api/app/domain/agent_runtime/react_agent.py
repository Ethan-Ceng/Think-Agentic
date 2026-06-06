from sqlalchemy.orm import Session

from app.domain.agent_runtime.protocols import WorkerInvocation, WorkerResult
from app.domain.agent_runtime.worker_runtime import WorkerRuntime
from app.models.account import Account
from app.models.agent import Agent, AgentVersion
from app.models.task import AgentPlan, AgentStep


class ReActAgent:
    """Execute a single plan step through the worker ReAct runtime."""

    def __init__(self, *, worker_runtime: WorkerRuntime | None = None) -> None:
        self.worker_runtime = worker_runtime or WorkerRuntime()

    def execute_step(
        self,
        *,
        session: Session,
        plan: AgentPlan | None = None,
        step: AgentStep | None = None,
        worker: Agent,
        invocation: WorkerInvocation,
        account: Account,
        agent_version: AgentVersion | None = None,
    ) -> WorkerResult:
        _ = (plan, step)
        if agent_version is None:
            return self.worker_runtime.invoke(
                invocation,
                session=session,
                worker=worker,
                account=account,
            )
        return self.worker_runtime.invoke(
            invocation,
            session=session,
            worker=worker,
            account=account,
            agent_version=agent_version,
        )
