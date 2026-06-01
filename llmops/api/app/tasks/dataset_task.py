from uuid import UUID

from app.infrastructure.celery import celery_app
from app.infrastructure.db import SessionLocal
from app.infrastructure.vector_store import WeaviateVectorStore


def _delete_dataset(dataset_id: str) -> None:
    if SessionLocal is None:
        raise RuntimeError("Database is not initialized")
    WeaviateVectorStore().delete_dataset(UUID(str(dataset_id)))


@celery_app.task(name="app.tasks.dataset_task.delete_dataset")
def delete_dataset(dataset_id: str) -> None:
    _delete_dataset(dataset_id)


@celery_app.task(name="app.task.dataset_task.delete_dataset")
def delete_dataset_legacy(dataset_id: str) -> None:
    _delete_dataset(dataset_id)
