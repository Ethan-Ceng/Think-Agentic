import math
import re
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session

from app.core.dataset import DEFAULT_DATASET_DESCRIPTION_FORMATTER, RetrievalSource, RetrievalStrategy, SegmentStatus
from app.core.exceptions import NotFoundException, ValidateErrorException
from app.infrastructure.vector_store import VectorSearchHit, WeaviateVectorStore
from app.models.account import Account
from app.models.dataset import Dataset, DatasetQuery, Document, KeywordTable, ProcessRule, Segment
from app.models.file import File
from app.schemas.dataset import DatasetStats
from app.services.base_service import BaseService


@dataclass
class DatasetService(BaseService):
    vector_store: WeaviateVectorStore = field(default_factory=WeaviateVectorStore)

    def create_dataset(
        self,
        session: Session,
        name: str,
        icon: str,
        description: str,
        account: Account,
    ) -> Dataset:
        duplicated = (
            session.query(Dataset)
            .filter(Dataset.account_id == account.id, Dataset.name == name)
            .one_or_none()
        )
        if duplicated:
            raise ValidateErrorException(f"Dataset already exists: {name}")

        description = self._normalize_description(name, description)
        return self.create(
            session,
            Dataset,
            account_id=account.id,
            name=name,
            icon=icon,
            description=description,
        )

    def get_dataset(self, session: Session, dataset_id: UUID, account: Account) -> Dataset:
        dataset = self.get(session, Dataset, dataset_id)
        if dataset is None or dataset.account_id != account.id:
            raise NotFoundException("Dataset does not exist")
        return dataset

    def update_dataset(
        self,
        session: Session,
        dataset_id: UUID,
        name: str,
        icon: str,
        description: str,
        account: Account,
    ) -> Dataset:
        dataset = self.get_dataset(session, dataset_id, account)
        duplicated = (
            session.query(Dataset)
            .filter(Dataset.account_id == account.id, Dataset.name == name, Dataset.id != dataset.id)
            .one_or_none()
        )
        if duplicated:
            raise ValidateErrorException(f"Dataset already exists: {name}")

        return self.update(
            session,
            dataset,
            name=name,
            icon=icon,
            description=self._normalize_description(name, description),
        )

    def delete_dataset(self, session: Session, dataset_id: UUID, account: Account) -> Dataset:
        dataset = self.get_dataset(session, dataset_id, account)
        self._delete_dataset_vectors(dataset.id)
        session.execute(sql_delete(Segment).where(Segment.dataset_id == dataset.id))
        session.execute(sql_delete(Document).where(Document.dataset_id == dataset.id))
        session.execute(sql_delete(ProcessRule).where(ProcessRule.dataset_id == dataset.id))
        session.execute(sql_delete(KeywordTable).where(KeywordTable.dataset_id == dataset.id))
        session.execute(sql_delete(DatasetQuery).where(DatasetQuery.dataset_id == dataset.id))
        session.execute(
            text("delete from app_dataset_join where dataset_id = :dataset_id"),
            {"dataset_id": str(dataset.id)},
        )
        self.delete(session, dataset)
        return dataset

    def _delete_dataset_vectors(self, dataset_id: UUID) -> None:
        try:
            self.vector_store.delete_dataset(dataset_id)
        except Exception:
            return

    def get_datasets_with_page(
        self,
        session: Session,
        account: Account,
        search_word: str = "",
        current_page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Dataset], int, int]:
        query = session.query(Dataset).filter(Dataset.account_id == account.id)
        if search_word:
            query = query.filter(Dataset.name.ilike(f"%{search_word}%"))

        total_record = query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        datasets = (
            query.order_by(desc(Dataset.created_at))
            .offset((current_page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return list(datasets), total_record, total_page

    def get_dataset_queries(self, session: Session, dataset_id: UUID, account: Account) -> list[DatasetQuery]:
        self.get_dataset(session, dataset_id, account)
        return list(
            session.query(DatasetQuery)
            .filter(DatasetQuery.dataset_id == dataset_id)
            .order_by(desc(DatasetQuery.created_at))
            .limit(10)
            .all()
        )

    def get_dataset_stats(self, session: Session, dataset_ids: list[UUID]) -> dict[UUID, DatasetStats]:
        stats = {dataset_id: DatasetStats() for dataset_id in dataset_ids}
        if not dataset_ids:
            return stats

        document_rows = (
            session.query(
                Document.dataset_id,
                func.count(Document.id),
                func.coalesce(func.sum(Document.character_count), 0),
            )
            .filter(Document.dataset_id.in_(dataset_ids))
            .group_by(Document.dataset_id)
            .all()
        )
        for dataset_id, document_count, character_count in document_rows:
            stats[dataset_id].document_count = int(document_count or 0)
            stats[dataset_id].character_count = int(character_count or 0)

        hit_rows = (
            session.query(Segment.dataset_id, func.coalesce(func.sum(Segment.hit_count), 0))
            .filter(Segment.dataset_id.in_(dataset_ids))
            .group_by(Segment.dataset_id)
            .all()
        )
        for dataset_id, hit_count in hit_rows:
            stats[dataset_id].hit_count = int(hit_count or 0)

        for dataset_id in dataset_ids:
            related_count = session.execute(
                text("select count(*) from app_dataset_join where dataset_id = :dataset_id"),
                {"dataset_id": str(dataset_id)},
            ).scalar()
            stats[dataset_id].related_app_count = int(related_count or 0)

        return stats

    def hit(
        self,
        session: Session,
        dataset_id: UUID,
        query: str,
        retrieval_strategy: str,
        k: int,
        score: float,
        account: Account,
    ) -> list[dict]:
        dataset = self.get_dataset(session, dataset_id, account)
        segments, score_by_segment_id = self._search_segments(
            session=session,
            dataset=dataset,
            account=account,
            query=query,
            retrieval_strategy=retrieval_strategy,
            k=k,
            score=score,
        )
        if not segments:
            return []

        segment_ids = [segment.id for segment in segments]
        for segment in segments:
            segment.hit_count += 1

        self.create(
            session,
            DatasetQuery,
            dataset_id=dataset.id,
            query=query,
            source=RetrievalSource.HIT_TESTING.value,
            source_app_id=None,
            created_by=account.id,
        )

        document_ids = [segment.document_id for segment in segments]
        document_rows = session.query(Document).filter(Document.id.in_(document_ids))
        documents = {document.id: document for document in document_rows}
        upload_files = {
            upload_file.id: upload_file
            for upload_file in session.query(File).filter(
                File.id.in_([document.upload_file_id for document in documents.values()])
            )
        }

        return [
            self._format_hit_result(
                segment,
                documents.get(segment.document_id),
                upload_files,
                score_by_segment_id.get(str(segment.id), 0.0),
            )
            for segment in segments
            if segment.id in segment_ids
        ]

    def _search_segments(
        self,
        session: Session,
        dataset: Dataset,
        account: Account,
        query: str,
        retrieval_strategy: str,
        k: int,
        score: float,
    ) -> tuple[list[Segment], dict[str, float]]:
        base_query = self._base_segment_query(session, dataset.id, account.id)
        if not query:
            segments = base_query.order_by(desc(Segment.hit_count), Segment.position.asc()).limit(k).all()
            return list(segments), {str(segment.id): 1.0 for segment in segments}

        query_terms = self._extract_query_terms(query)
        if retrieval_strategy == RetrievalStrategy.FULL_TEXT.value:
            return self._search_segments_by_keyword_table(session, base_query, dataset.id, query_terms, k, score)
        if retrieval_strategy == RetrievalStrategy.HYBRID.value:
            return self._search_segments_hybrid(session, base_query, dataset, account, query, query_terms, k, score)
        vector_segments = self._search_segments_by_vector_store(base_query, dataset, account, query, k, score)
        if vector_segments is not None:
            return vector_segments
        return self._search_segments_by_lexical_score(base_query, query_terms, k, score)

    @staticmethod
    def _base_segment_query(session: Session, dataset_id: UUID, account_id: UUID):
        return session.query(Segment).filter(
            Segment.dataset_id == dataset_id,
            Segment.account_id == account_id,
            Segment.enabled.is_(True),
            Segment.status == SegmentStatus.COMPLETED.value,
        )

    def _search_segments_by_keyword_table(
        self,
        session: Session,
        base_query,
        dataset_id: UUID,
        query_terms: list[str],
        k: int,
        score: float,
    ) -> tuple[list[Segment], dict[str, float]]:
        keyword_record = session.query(KeywordTable).filter(KeywordTable.dataset_id == dataset_id).one_or_none()
        ranked_ids = self._rank_keyword_segment_ids(
            keyword_record.keyword_table if keyword_record else {},
            query_terms,
            k,
            score,
        )
        if not ranked_ids:
            return self._search_segments_by_lexical_score(base_query, query_terms, k, score)

        rank = {segment_id: index for index, (segment_id, _) in enumerate(ranked_ids)}
        score_by_segment_id = {segment_id: segment_score for segment_id, segment_score in ranked_ids}
        segments = base_query.filter(Segment.id.in_([segment_id for segment_id, _ in ranked_ids])).all()
        segments.sort(key=lambda segment: rank[str(segment.id)])
        return segments, score_by_segment_id

    def _search_segments_hybrid(
        self,
        session: Session,
        base_query,
        dataset: Dataset,
        account: Account,
        query: str,
        query_terms: list[str],
        k: int,
        score: float,
    ) -> tuple[list[Segment], dict[str, float]]:
        keyword_segments, keyword_scores = self._search_segments_by_keyword_table(
            session,
            base_query,
            dataset.id,
            query_terms,
            k=max(k * 2, k),
            score=0,
        )
        vector_result = self._search_segments_by_vector_store(
            base_query,
            dataset,
            account,
            query,
            k=max(k * 2, k),
            score=0,
        )
        if vector_result is None:
            secondary_segments, secondary_scores = self._search_segments_by_lexical_score(
                base_query,
                query_terms,
                k=max(k * 2, k),
                score=0,
            )
        else:
            secondary_segments, secondary_scores = vector_result

        segment_map = {str(segment.id): segment for segment in [*keyword_segments, *secondary_segments]}
        combined_scores = {
            segment_id: (keyword_scores.get(segment_id, 0.0) * 0.5) + (secondary_scores.get(segment_id, 0.0) * 0.5)
            for segment_id in segment_map
        }
        filtered_ids = [
            segment_id
            for segment_id, segment_score in sorted(combined_scores.items(), key=lambda item: item[1], reverse=True)
            if segment_score >= score
        ][:k]
        return [segment_map[segment_id] for segment_id in filtered_ids], {
            segment_id: combined_scores[segment_id] for segment_id in filtered_ids
        }

    def _search_segments_by_vector_store(
        self,
        base_query,
        dataset: Dataset,
        account: Account,
        query: str,
        k: int,
        score: float,
    ) -> tuple[list[Segment], dict[str, float]] | None:
        try:
            hits = self.vector_store.search_segments(
                dataset_id=dataset.id,
                account_id=account.id,
                query=query,
                k=k,
                score=score,
            )
        except Exception:
            return None
        if not hits:
            return None
        return self._segments_from_vector_hits(base_query, hits)

    @staticmethod
    def _segments_from_vector_hits(
        base_query,
        hits: list[VectorSearchHit],
    ) -> tuple[list[Segment], dict[str, float]]:
        ranked_ids = []
        for hit in hits:
            try:
                ranked_ids.append((UUID(str(hit.segment_id)), hit.score))
            except (TypeError, ValueError):
                continue
        if not ranked_ids:
            return [], {}

        rank = {str(segment_id): index for index, (segment_id, _) in enumerate(ranked_ids)}
        score_by_segment_id = {str(segment_id): segment_score for segment_id, segment_score in ranked_ids}
        segments = base_query.filter(Segment.id.in_([segment_id for segment_id, _ in ranked_ids])).all()
        segments.sort(key=lambda segment: rank[str(segment.id)])
        return segments, score_by_segment_id

    def _search_segments_by_lexical_score(
        self,
        base_query,
        query_terms: list[str],
        k: int,
        score: float,
    ) -> tuple[list[Segment], dict[str, float]]:
        segments = base_query.all()
        scored_segments = [
            (segment, self._lexical_score(query_terms, segment.content))
            for segment in segments
        ]
        scored_segments = [
            (segment, segment_score)
            for segment, segment_score in scored_segments
            if segment_score >= score and segment_score > 0
        ]
        scored_segments.sort(key=lambda item: (item[1], item[0].hit_count, -item[0].position), reverse=True)
        selected = scored_segments[:k]
        return [segment for segment, _ in selected], {
            str(segment.id): segment_score for segment, segment_score in selected
        }

    @classmethod
    def _normalize_description(cls, name: str, description: str) -> str:
        description = description.strip() if description else ""
        return description or DEFAULT_DATASET_DESCRIPTION_FORMATTER.format(name=name)

    @classmethod
    def _rank_keyword_segment_ids(
        cls,
        keyword_table: dict,
        query_terms: list[str],
        k: int,
        score: float,
    ) -> list[tuple[str, float]]:
        if not query_terms:
            return []

        query_term_set = set(query_terms)
        counter: Counter[str] = Counter()
        for keyword, segment_ids in (keyword_table or {}).items():
            if str(keyword).lower() not in query_term_set or not isinstance(segment_ids, list):
                continue
            counter.update(str(segment_id) for segment_id in segment_ids)

        ranked = []
        for segment_id, count in counter.most_common():
            segment_score = min(1.0, count / len(query_term_set))
            if segment_score >= score:
                ranked.append((segment_id, segment_score))
            if len(ranked) >= k:
                break
        return ranked

    @staticmethod
    def _extract_query_terms(query: str, limit: int = 20) -> list[str]:
        terms = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
        return list(dict.fromkeys(term for term in terms if len(term) > 1))[:limit]

    @classmethod
    def _lexical_score(cls, query_terms: list[str], content: str) -> float:
        if not query_terms or not content:
            return 0.0
        content_terms = set(cls._extract_query_terms(content, limit=2000))
        if not content_terms:
            return 0.0
        matched_terms = set(query_terms) & content_terms
        return len(matched_terms) / len(set(query_terms))

    @staticmethod
    def _format_hit_result(
        segment: Segment,
        document: Document | None,
        upload_files: dict[UUID, File],
        score: float,
    ) -> dict:
        upload_file = upload_files.get(document.upload_file_id) if document else None
        return {
            "id": segment.id,
            "dataset_id": segment.dataset_id,
            "score": score,
            "position": segment.position,
            "content": segment.content,
            "keywords": segment.keywords or [],
            "character_count": segment.character_count,
            "token_count": segment.token_count,
            "hit_count": segment.hit_count,
            "enabled": segment.enabled,
            "disabled_at": int(segment.disabled_at.timestamp()) if segment.disabled_at else 0,
            "status": segment.status,
            "error": segment.error,
            "updated_at": int(segment.updated_at.timestamp()) if segment.updated_at else 0,
            "created_at": int(segment.created_at.timestamp()) if segment.created_at else 0,
            "document": {
                "id": document.id if document else "",
                "name": document.name if document else "",
                "extension": upload_file.extension if upload_file else "",
                "mime_type": upload_file.mime_type if upload_file else "",
            },
        }
