from app.domain.agent_runtime.protocols import WorkerInvocation, WorkerResult


class WorkerRuntime:
    """Worker Agent runtime placeholder."""

    def invoke(self, invocation: WorkerInvocation) -> WorkerResult:
        return WorkerResult(
            trace_id=invocation.trace_id,
            task_id=invocation.task_id,
            step_id=invocation.step_id,
            worker_id=invocation.worker_id,
            status="failed",
            summary="Worker runtime is not implemented yet.",
            retryable=False,
            error_code="not_implemented",
        )
