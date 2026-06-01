from uuid import UUID

from app.infrastructure.celery import celery_app
from app.infrastructure.db import SessionLocal
from app.services.app_service import AppService


def _auto_create_app(name: str, description: str, account_id: str) -> None:
    if SessionLocal is None:
        raise RuntimeError("Database is not initialized")
    with SessionLocal() as session:
        AppService().auto_create_app(session, name, description, UUID(str(account_id)))
        session.commit()


@celery_app.task(name="app.tasks.app_task.auto_create_app")
def auto_create_app(name: str, description: str, account_id: str) -> None:
    _auto_create_app(name, description, account_id)


@celery_app.task(name="app.task.app_task.auto_create_app")
def auto_create_app_legacy(name: str, description: str, account_id: str) -> None:
    _auto_create_app(name, description, account_id)
