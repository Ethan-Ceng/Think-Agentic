import math
import random
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.dataset import ALLOWED_DOCUMENT_EXTENSION, DEFAULT_PROCESS_RULE, DocumentStatus, ProcessType
from app.core.exceptions import FailException, ForbiddenException, NotFoundException
from app.models.account import Account
from app.models.dataset import Dataset, Document, ProcessRule, Segment
from app.models.file import File
from app.services.base_service import BaseService
from app.services.indexing_service import IndexingService


@dataclass
class DocumentService(BaseService):
    def create_documents(
        self,
        session: Session,
        dataset_id: UUID,
        upload_file_ids: list[UUID],
        process_type: str,
        rule: dict | None,
        account: Account,
    ) -> tuple[list[Document], str]:
        dataset = self._get_dataset(session, dataset_id, account)
        upload_files = (
            session.query(File)
            .filter(
                File.account_id == account.id,
                File.id.in_(upload_file_ids),
                File.type == "file",
                File.status == "available",
            )
            .all()
        )
        upload_files = [
            upload_file
            for upload_file in upload_files
            if upload_file.extension.lower().lstrip(".") in ALLOWED_DOCUMENT_EXTENSION
        ]
        if not upload_files:
            raise FailException("No valid document upload files found")

        batch = time.strftime("%Y%m%d%H%M%S") + str(random.randint(100000, 999999))
        process_rule = self.create(
            session,
            ProcessRule,
            account_id=account.id,
            dataset_id=dataset.id,
            mode=process_type or ProcessType.AUTOMATIC.value,
            rule=rule or DEFAULT_PROCESS_RULE["rule"],
        )
        position = self.get_latest_document_position(session, dataset.id)
        documents = []
        for upload_file in upload_files:
            position += 1
            documents.append(
                self.create(
                    session,
                    Document,
                    account_id=account.id,
                    dataset_id=dataset.id,
                    upload_file_id=upload_file.id,
                    process_rule_id=process_rule.id,
                    batch=batch,
                    name=upload_file.name,
                    position=position,
                    status=DocumentStatus.WAITING.value,
                )
            )
        IndexingService().build_documents(session, [document.id for document in documents])
        return documents, batch

    def get_documents_with_page(
        self,
        session: Session,
        dataset_id: UUID,
        account: Account,
        search_word: str = "",
        current_page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Document], int, int]:
        self._get_dataset(session, dataset_id, account)
        query = session.query(Document).filter(Document.account_id == account.id, Document.dataset_id == dataset_id)
        if search_word:
            query = query.filter(Document.name.ilike(f"%{search_word}%"))

        total_record = query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        documents = (
            query.order_by(desc(Document.created_at))
            .offset((current_page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return list(documents), total_record, total_page

    def get_documents_status(self, session: Session, dataset_id: UUID, batch: str, account: Account) -> list[dict]:
        self._get_dataset(session, dataset_id, account)
        documents = (
            session.query(Document)
            .filter(Document.dataset_id == dataset_id, Document.batch == batch)
            .order_by(Document.position.asc())
            .all()
        )
        if not documents:
            raise NotFoundException("Document batch does not exist")

        upload_files = self._get_upload_file_map(session, documents)
        statuses = []
        for document in documents:
            segment_count = session.query(func.count(Segment.id)).filter(Segment.document_id == document.id).scalar()
            completed_segment_count = (
                session.query(func.count(Segment.id))
                .filter(Segment.document_id == document.id, Segment.status == "completed")
                .scalar()
            )
            upload_file = upload_files.get(document.upload_file_id)
            statuses.append(
                {
                    "id": document.id,
                    "name": document.name,
                    "size": upload_file.size if upload_file else 0,
                    "extension": upload_file.extension if upload_file else "",
                    "mime_type": upload_file.mime_type if upload_file else "",
                    "position": document.position,
                    "segment_count": int(segment_count or 0),
                    "completed_segment_count": int(completed_segment_count or 0),
                    "error": document.error,
                    "status": document.status,
                    "processing_started_at": self._ts(document.processing_started_at),
                    "parsing_completed_at": self._ts(document.parsing_completed_at),
                    "splitting_completed_at": self._ts(document.splitting_completed_at),
                    "indexing_completed_at": self._ts(document.indexing_completed_at),
                    "completed_at": self._ts(document.completed_at),
                    "stopped_at": self._ts(document.stopped_at),
                    "created_at": self._ts(document.created_at),
                }
            )
        return statuses

    def get_document(self, session: Session, dataset_id: UUID, document_id: UUID, account: Account) -> Document:
        document = self.get(session, Document, document_id)
        if document is None:
            raise NotFoundException("Document does not exist")
        if document.dataset_id != dataset_id or document.account_id != account.id:
            raise ForbiddenException("Current account cannot access this document")
        return document

    def update_document(
        self,
        session: Session,
        dataset_id: UUID,
        document_id: UUID,
        account: Account,
        **kwargs,
    ) -> Document:
        document = self.get_document(session, dataset_id, document_id, account)
        return self.update(session, document, **kwargs)

    def update_document_enabled(
        self,
        session: Session,
        dataset_id: UUID,
        document_id: UUID,
        enabled: bool,
        account: Account,
    ) -> Document:
        document = self.get_document(session, dataset_id, document_id, account)
        if document.status != DocumentStatus.COMPLETED.value:
            raise ForbiddenException("Document cannot be enabled or disabled before indexing completes")
        if document.enabled == enabled:
            raise FailException("Document enabled state is unchanged")
        document = self.update(
            session,
            document,
            enabled=enabled,
            disabled_at=None if enabled else datetime.now(),
        )
        IndexingService().update_document_enabled(session, document.id, enabled)
        return document

    def delete_document(self, session: Session, dataset_id: UUID, document_id: UUID, account: Account) -> Document:
        document = self.get_document(session, dataset_id, document_id, account)
        if document.status not in {
            DocumentStatus.WAITING.value,
            DocumentStatus.COMPLETED.value,
            DocumentStatus.ERROR.value,
        }:
            raise FailException("Document cannot be deleted in current status")
        IndexingService().delete_document_vectors(document.id)
        session.query(Segment).filter(Segment.document_id == document.id).delete(synchronize_session=False)
        self.delete(session, document)
        return document

    def get_latest_document_position(self, session: Session, dataset_id: UUID) -> int:
        document = (
            session.query(Document)
            .filter(Document.dataset_id == dataset_id)
            .order_by(desc(Document.position))
            .first()
        )
        return int(document.position) if document else 0

    def get_document_hit_count(self, session: Session, document_id: UUID) -> int:
        return int(
            session.query(func.coalesce(func.sum(Segment.hit_count), 0))
            .filter(Segment.document_id == document_id)
            .scalar()
            or 0
        )

    def _get_dataset(self, session: Session, dataset_id: UUID, account: Account) -> Dataset:
        dataset = self.get(session, Dataset, dataset_id)
        if dataset is None or dataset.account_id != account.id:
            raise NotFoundException("Dataset does not exist")
        return dataset

    @staticmethod
    def _get_upload_file_map(session: Session, documents: list[Document]) -> dict[UUID, File]:
        upload_file_ids = [document.upload_file_id for document in documents]
        return {
            upload_file.id: upload_file
            for upload_file in session.query(File).filter(File.id.in_(upload_file_ids))
        }

    @staticmethod
    def _ts(value) -> int:
        return int(value.timestamp()) if value else 0
