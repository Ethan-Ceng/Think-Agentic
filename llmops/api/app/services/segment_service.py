import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha3_256
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dataset import DocumentStatus, SegmentStatus
from app.core.exceptions import FailException, NotFoundException, ValidateErrorException
from app.infrastructure.vector_store import WeaviateVectorStore
from app.models.account import Account
from app.models.dataset import Document, Segment
from app.services.base_service import BaseService


@dataclass
class SegmentService(BaseService):
    vector_store: WeaviateVectorStore = field(default_factory=WeaviateVectorStore)

    def create_segment(
        self,
        session: Session,
        dataset_id: UUID,
        document_id: UUID,
        content: str,
        keywords: list[str],
        account: Account,
    ) -> Segment:
        document = self._get_document(session, dataset_id, document_id, account)
        if document.status != DocumentStatus.COMPLETED.value:
            raise FailException("Document cannot add segments before indexing completes")

        token_count = self._calculate_token_count(content)
        if token_count > 1000:
            raise ValidateErrorException("Segment content cannot exceed 1000 tokens")

        position = self._get_latest_segment_position(session, document_id) + 1
        keywords = keywords or self._extract_keywords(content)
        segment = self.create(
            session,
            Segment,
            account_id=account.id,
            dataset_id=dataset_id,
            document_id=document_id,
            node_id=uuid.uuid4(),
            position=position,
            content=content,
            character_count=len(content),
            token_count=token_count,
            keywords=keywords,
            hash=self._hash_text(content),
            enabled=True,
            processing_started_at=datetime.now(),
            indexing_completed_at=datetime.now(),
            completed_at=datetime.now(),
            status=SegmentStatus.COMPLETED.value,
        )
        self._refresh_document_counts(session, document)
        self._upsert_segment_vector(segment)
        return segment

    def update_segment(
        self,
        session: Session,
        dataset_id: UUID,
        document_id: UUID,
        segment_id: UUID,
        content: str,
        keywords: list[str],
        account: Account,
    ) -> Segment:
        segment = self.get_segment(session, dataset_id, document_id, segment_id, account)
        if segment.status != SegmentStatus.COMPLETED.value:
            raise FailException("Segment cannot be updated in current status")

        token_count = self._calculate_token_count(content)
        if token_count > 1000:
            raise ValidateErrorException("Segment content cannot exceed 1000 tokens")

        segment = self.update(
            session,
            segment,
            content=content,
            keywords=keywords or self._extract_keywords(content),
            hash=self._hash_text(content),
            character_count=len(content),
            token_count=token_count,
        )
        document = self._get_document(session, dataset_id, document_id, account)
        self._refresh_document_counts(session, document)
        self._upsert_segment_vector(segment)
        return segment

    def get_segments_with_page(
        self,
        session: Session,
        dataset_id: UUID,
        document_id: UUID,
        account: Account,
        search_word: str = "",
        current_page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Segment], int, int]:
        self._get_document(session, dataset_id, document_id, account)
        query = session.query(Segment).filter(Segment.document_id == document_id)
        if search_word:
            query = query.filter(Segment.content.ilike(f"%{search_word}%"))

        total_record = query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        segments = (
            query.order_by(Segment.position.asc())
            .offset((current_page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return list(segments), total_record, total_page

    def get_segment(
        self,
        session: Session,
        dataset_id: UUID,
        document_id: UUID,
        segment_id: UUID,
        account: Account,
    ) -> Segment:
        segment = self.get(session, Segment, segment_id)
        if (
            segment is None
            or segment.account_id != account.id
            or segment.dataset_id != dataset_id
            or segment.document_id != document_id
        ):
            raise NotFoundException("Segment does not exist")
        return segment

    def update_segment_enabled(
        self,
        session: Session,
        dataset_id: UUID,
        document_id: UUID,
        segment_id: UUID,
        enabled: bool,
        account: Account,
    ) -> Segment:
        segment = self.get_segment(session, dataset_id, document_id, segment_id, account)
        if segment.status != SegmentStatus.COMPLETED.value:
            raise FailException("Segment cannot be enabled or disabled in current status")
        if segment.enabled == enabled:
            raise FailException("Segment enabled state is unchanged")
        segment = self.update(
            session,
            segment,
            enabled=enabled,
            disabled_at=None if enabled else datetime.now(),
        )
        self._update_segment_vector_enabled(segment.node_id, enabled)
        return segment

    def delete_segment(
        self,
        session: Session,
        dataset_id: UUID,
        document_id: UUID,
        segment_id: UUID,
        account: Account,
    ) -> Segment:
        segment = self.get_segment(session, dataset_id, document_id, segment_id, account)
        if segment.status not in {SegmentStatus.COMPLETED.value, SegmentStatus.ERROR.value}:
            raise FailException("Segment cannot be deleted in current status")
        document = self._get_document(session, dataset_id, document_id, account)
        self._delete_segment_vector(segment.node_id)
        self.delete(session, segment)
        self._refresh_document_counts(session, document)
        return segment

    def _get_document(self, session: Session, dataset_id: UUID, document_id: UUID, account: Account) -> Document:
        document = self.get(session, Document, document_id)
        if document is None or document.dataset_id != dataset_id or document.account_id != account.id:
            raise NotFoundException("Document does not exist")
        return document

    @staticmethod
    def _get_latest_segment_position(session: Session, document_id: UUID) -> int:
        value = session.query(func.coalesce(func.max(Segment.position), 0)).filter(
            Segment.document_id == document_id
        ).scalar()
        return int(value or 0)

    @staticmethod
    def _refresh_document_counts(session: Session, document: Document) -> None:
        character_count, token_count = (
            session.query(
                func.coalesce(func.sum(Segment.character_count), 0),
                func.coalesce(func.sum(Segment.token_count), 0),
            )
            .filter(Segment.document_id == document.id)
            .one()
        )
        document.character_count = int(character_count or 0)
        document.token_count = int(token_count or 0)
        session.flush()

    @staticmethod
    def _calculate_token_count(content: str) -> int:
        return max(1, len(re.findall(r"\w+|[^\w\s]", content)))

    @staticmethod
    def _extract_keywords(content: str, limit: int = 10) -> list[str]:
        words = re.findall(r"[\w\u4e00-\u9fff]+", content.lower())
        deduped = list(dict.fromkeys(word for word in words if len(word) > 1))
        return deduped[:limit]

    @staticmethod
    def _hash_text(content: str) -> str:
        return sha3_256((str(content) + "None").encode()).hexdigest()

    def _upsert_segment_vector(self, segment: Segment) -> None:
        try:
            self.vector_store.upsert_segments([segment])
        except Exception:
            return

    def _update_segment_vector_enabled(self, node_id: UUID, enabled: bool) -> None:
        try:
            self.vector_store.update_segment_enabled(node_id, enabled)
        except Exception:
            return

    def _delete_segment_vector(self, node_id: UUID) -> None:
        try:
            self.vector_store.delete_segments([node_id])
        except Exception:
            return

