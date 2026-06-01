from app.infrastructure.celery import celery_app


@celery_app.task(name="app.tasks.agent_task.run_agent_task")
def run_agent_task(task_id: str) -> dict[str, str]:
    return {"task_id": task_id, "status": "not_implemented"}
