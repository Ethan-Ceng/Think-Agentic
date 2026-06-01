import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha3_256
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.dataset import DEFAULT_PROCESS_RULE, DocumentStatus, SegmentStatus
from app.core.file_extractor import FileExtractor
from app.infrastructure.vector_store import WeaviateVectorStore
from app.models.dataset import Document, KeywordTable, ProcessRule, Segment
from app.models.upload_file import UploadFile
from app.services.base_service import BaseService


@dataclass
class IndexingService(BaseService):
    file_extractor: FileExtractor = field(default_factory=FileExtractor)
    vector_store: WeaviateVectorStore = field(default_factory=WeaviateVectorStore)

    def build_documents(self, session: Session, document_ids: list[UUID]) -> None:
        documents = session.query(Document).filter(Document.id.in_(document_ids)).all()
        for document in documents:
            try:
                self.update(
                    session,
                    document,
                    status=DocumentStatus.PARSING.value,
                    error="",
                    processing_started_at=datetime.now(),
                )
                upload_file = session.get(UploadFile, document.upload_file_id)
                if upload_file is None:
                    raise FileNotFoundError("Upload file does not exist")

                text = self.file_extractor.load(upload_file)
                process_rule = session.get(ProcessRule, document.process_rule_id)
                rule = process_rule.rule if process_rule and process_rule.rule else DEFAULT_PROCESS_RULE["rule"]

                text = self._clean_text_by_rule(text, rule)
                self.update(
                    session,
                    document,
                    character_count=len(text),
                    status=DocumentStatus.SPLITTING.value,
                    parsing_completed_at=datetime.now(),
                )

                chunks = self._split_text(text, rule)
                session.query(Segment).filter(Segment.document_id == document.id).delete(synchronize_session=False)
                self.update(
                    session,
                    document,
                    status=DocumentStatus.INDEXING.value,
                    splitting_completed_at=datetime.now(),
                )

                segments = self._create_segments(session, document, chunks)
                self._refresh_keyword_table(session, document.dataset_id, segments)
                self._index_segments_in_vector_store(segments)
                self.update(
                    session,
                    document,
                    token_count=sum(segment.token_count for segment in segments),
                    character_count=sum(segment.character_count for segment in segments),
                    status=DocumentStatus.COMPLETED.value,
                    enabled=True,
                    error="",
                    indexing_completed_at=datetime.now(),
                    completed_at=datetime.now(),
                )
            except Exception as exc:
                self.update(
                    session,
                    document,
                    status=DocumentStatus.ERROR.value,
                    error=str(exc),
                    stopped_at=datetime.now(),
                )

    def update_document_enabled(self, session: Session, document_id: UUID, enabled: bool) -> None:
        disabled_at = None if enabled else datetime.now()
        session.query(Segment).filter(
            Segment.document_id == document_id,
            Segment.status == SegmentStatus.COMPLETED.value,
        ).update(
            {"enabled": enabled, "disabled_at": disabled_at},
            synchronize_session=False,
        )
        session.flush()
        node_ids = [
            node_id
            for (node_id,) in session.query(Segment.node_id)
            .filter(Segment.document_id == document_id, Segment.status == SegmentStatus.COMPLETED.value)
            .all()
        ]
        self._update_document_enabled_in_vector_store(node_ids, enabled)

    def delete_document_vectors(self, document_id: UUID) -> None:
        try:
            self.vector_store.delete_document(document_id)
        except Exception:
            return

    def _create_segments(self, session: Session, document: Document, chunks: list[str]) -> list[Segment]:
        segments = []
        for position, content in enumerate(chunks, start=1):
            segments.append(
                self.create(
                    session,
                    Segment,
                    account_id=document.account_id,
                    dataset_id=document.dataset_id,
                    document_id=document.id,
                    node_id=uuid.uuid4(),
                    position=position,
                    content=content,
                    character_count=len(content),
                    token_count=self._calculate_token_count(content),
                    keywords=self._extract_keywords(content),
                    hash=self._hash_text(content),
                    enabled=True,
                    processing_started_at=datetime.now(),
                    indexing_completed_at=datetime.now(),
                    completed_at=datetime.now(),
                    status=SegmentStatus.COMPLETED.value,
                )
            )
        return segments

    def _refresh_keyword_table(self, session: Session, dataset_id: UUID, segments: list[Segment]) -> None:
        keyword_record = session.query(KeywordTable).filter(KeywordTable.dataset_id == dataset_id).one_or_none()
        keyword_table = dict(keyword_record.keyword_table) if keyword_record else {}
        for segment in segments:
            for keyword in segment.keywords:
                keyword_table.setdefault(keyword, [])
                if str(segment.id) not in keyword_table[keyword]:
                    keyword_table[keyword].append(str(segment.id))

        if keyword_record is None:
            self.create(session, KeywordTable, dataset_id=dataset_id, keyword_table=keyword_table)
        else:
            self.update(session, keyword_record, keyword_table=keyword_table)

    def _index_segments_in_vector_store(self, segments: list[Segment]) -> None:
        try:
            self.vector_store.upsert_segments(segments)
        except Exception:
            return

    def _update_document_enabled_in_vector_store(self, node_ids: list[UUID], enabled: bool) -> None:
        try:
            self.vector_store.update_document_enabled(node_ids, enabled)
        except Exception:
            return

    @classmethod
    def _split_text(cls, text: str, rule: dict) -> list[str]:
        segment_rule = (rule or {}).get("segment", {})
        chunk_size = max(1, int(segment_rule.get("chunk_size", 500) or 500))
        chunk_overlap = max(0, int(segment_rule.get("chunk_overlap", 50) or 0))
        chunk_overlap = min(chunk_overlap, chunk_size - 1)
        text = text.strip()
        if not text:
            return []

        chunks = []
        step = chunk_size - chunk_overlap
        for index in range(0, len(text), step):
            chunk = text[index : index + chunk_size].strip()
            if chunk:
                chunks.append(chunk)
            if index + chunk_size >= len(text):
                break
        return chunks

    @staticmethod
    def _clean_text_by_rule(text: str, rule: dict) -> str:
        enabled_rules = {
            item.get("id")
            for item in (rule or {}).get("pre_process_rules", [])
            if item.get("enabled")
        }
        if "remove_url_and_email" in enabled_rules:
            text = re.sub(r"https?://\S+|www\.\S+", " ", text)
            text = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", " ", text)
        if "remove_extra_space" in enabled_rules:
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s+\n", "\n\n", text)
        return text.strip()

    @staticmethod
    def _calculate_token_count(content: str) -> int:
        return max(1, len(re.findall(r"\w+|[^\w\s]", content))) if content else 0

    @staticmethod
    def _extract_keywords(content: str, limit: int = 10) -> list[str]:
        words = re.findall(r"[\w\u4e00-\u9fff]+", content.lower())
        return list(dict.fromkeys(word for word in words if len(word) > 1))[:limit]

    @staticmethod
    def _hash_text(content: str) -> str:
        return sha3_256((content + "None").encode()).hexdigest()
