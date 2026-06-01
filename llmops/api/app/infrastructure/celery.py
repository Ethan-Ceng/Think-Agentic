from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("llmops_api")
celery_app.conf.broker_url = settings.celery_broker_url
celery_app.conf.result_backend = settings.celery_result_backend
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"
celery_app.conf.imports = (
    "app.tasks.agent_task",
    "app.tasks.app_task",
    "app.tasks.dataset_task",
    "app.tasks.document_task",
)
celery_app.conf.task_routes = {
    "app.tasks.agent_task.*": {"queue": "agent_runtime"},
    "app.tasks.app_task.*": {"queue": "agent_runtime"},
    "app.task.app_task.*": {"queue": "agent_runtime"},
    "app.tasks.dataset_task.*": {"queue": "dataset_indexing"},
    "app.task.dataset_task.*": {"queue": "dataset_indexing"},
    "app.tasks.document_task.*": {"queue": "dataset_indexing"},
    "app.task.document_task.*": {"queue": "dataset_indexing"},
}
