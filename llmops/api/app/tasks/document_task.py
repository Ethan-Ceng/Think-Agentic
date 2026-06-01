from uuid import UUID

from app.infrastructure.celery import celery_app
from app.infrastructure.db import SessionLocal
from app.models.dataset import Document
from app.services.indexing_service import IndexingService


def _build_documents(document_ids: list[str]) -> None:
    if SessionLocal is None:
        raise RuntimeError("Database is not initialized")
    with SessionLocal() as session:
        IndexingService().build_documents(session, [UUID(str(document_id)) for document_id in document_ids])
        session.commit()


def _update_document_enabled(document_id: str, enabled: bool | None) -> None:
    if SessionLocal is None:
        raise RuntimeError("Database is not initialized")
    with SessionLocal() as session:
        document_uuid = UUID(str(document_id))
        if enabled is None:
            document = session.get(Document, document_uuid)
            if document is None:
                return
            enabled = bool(document.enabled)
        IndexingService().update_document_enabled(session, document_uuid, enabled)
        session.commit()


def _delete_document(document_id: str) -> None:
    IndexingService().delete_document_vectors(UUID(str(document_id)))


@celery_app.task(name="app.tasks.document_task.build_documents")
def build_documents(document_ids: list[str]) -> None:
    _build_documents(document_ids)


@celery_app.task(name="app.task.document_task.build_documents")
def build_documents_legacy(document_ids: list[str]) -> None:
    _build_documents(document_ids)


@celery_app.task(name="app.tasks.document_task.update_document_enabled")
def update_document_enabled(document_id: str, enabled: bool) -> None:
    _update_document_enabled(document_id, enabled)


@celery_app.task(name="app.task.document_task.update_document_enabled")
def update_document_enabled_legacy(document_id: str) -> None:
    _update_document_enabled(document_id, None)


@celery_app.task(name="app.tasks.document_task.update_document_enabled_from_db")
def update_document_enabled_from_db(document_id: str) -> None:
    _update_document_enabled(document_id, None)


@celery_app.task(name="app.tasks.document_task.delete_document")
def delete_document(dataset_id: str, document_id: str) -> None:
    _delete_document(document_id)


@celery_app.task(name="app.task.document_task.delete_document")
def delete_document_legacy(dataset_id: str, document_id: str) -> None:
    _delete_document(document_id)
