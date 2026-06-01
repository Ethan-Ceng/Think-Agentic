from uuid import UUID

from app.core.conversation import InvokeFrom


class AgentQueueManager:
    _stopped_tasks: set[str] = set()
    _task_owners: dict[str, str] = {}

    @classmethod
    def register_task(cls, task_id: UUID, invoke_from: InvokeFrom, user_id: UUID) -> None:
        cls._task_owners[str(task_id)] = cls._owner_key(invoke_from, user_id)

    @classmethod
    def clear_task(cls, task_id: UUID) -> None:
        task_key = str(task_id)
        cls._task_owners.pop(task_key, None)
        cls._stopped_tasks.discard(task_key)

    @classmethod
    def is_stopped(cls, task_id: UUID) -> bool:
        return str(task_id) in cls._stopped_tasks

    @classmethod
    def set_stop_flag(cls, task_id: UUID, invoke_from: InvokeFrom, user_id: UUID) -> None:
        task_key = str(task_id)
        if cls._task_owners.get(task_key) == cls._owner_key(invoke_from, user_id):
            cls._stopped_tasks.add(task_key)

    @classmethod
    def _owner_key(cls, invoke_from: InvokeFrom, user_id: UUID) -> str:
        user_prefix = "account" if invoke_from in {
            InvokeFrom.WEB_APP,
            InvokeFrom.DEBUGGER,
            InvokeFrom.ASSISTANT_AGENT,
        } else "end-user"
        return f"{user_prefix}-{user_id}"
