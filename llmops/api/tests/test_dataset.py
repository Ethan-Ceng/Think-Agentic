import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_current_account, get_dataset_service, get_db_session
from app.app_factory import create_app
from app.core.config import Settings
from app.infrastructure.vector_store import VectorSearchHit
from app.models.account import Account
from app.schemas.dataset import DatasetResponse, DatasetStats, HitRequest
from app.services.dataset_service import DatasetService


def test_dataset_default_description_uses_name() -> None:
    description = DatasetService._normalize_description("Docs", "")

    assert "Docs" in description


def test_dataset_response_includes_stats() -> None:
    dataset = SimpleNamespace(
        id=uuid.uuid4(),
        name="Docs",
        icon="https://example.test/icon.png",
        description="desc",
        updated_at=datetime(2024, 1, 1),
        created_at=datetime(2024, 1, 1),
    )

    response = DatasetResponse.from_dataset(
        dataset,
        DatasetStats(document_count=2, hit_count=3, related_app_count=4, character_count=5),
    )

    assert response.document_count == 2
    assert response.hit_count == 3
    assert response.related_app_count == 4
    assert response.character_count == 5


def test_dataset_hit_request_validates_retrieval_strategy() -> None:
    req = HitRequest(query="hello", retrieval_strategy="full_text", k=3)

    assert req.retrieval_strategy.value == "full_text"


def test_dataset_keyword_rank_uses_keyword_table_frequency() -> None:
    ranked = DatasetService._rank_keyword_segment_ids(
        {
            "agent": ["segment-1", "segment-2"],
            "workflow": ["segment-2"],
            "unrelated": ["segment-3"],
        },
        ["agent", "workflow"],
        k=2,
        score=0.5,
    )

    assert ranked == [("segment-2", 1.0), ("segment-1", 0.5)]


def test_dataset_lexical_score_matches_query_terms() -> None:
    query_terms = DatasetService._extract_query_terms("agent workflow missing")

    score = DatasetService._lexical_score(query_terms, "An agent can call a workflow tool.")

    assert score == 2 / 3


def test_dataset_vector_hits_keep_vector_rank_and_scores() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    first = SimpleNamespace(id=first_id)
    second = SimpleNamespace(id=second_id)

    class FakeQuery:
        def filter(self, expression):  # noqa: ANN001
            return self

        def all(self):
            return [second, first]

    segments, scores = DatasetService._segments_from_vector_hits(  # noqa: SLF001
        FakeQuery(),
        [
            VectorSearchHit(segment_id=str(first_id), score=0.9),
            VectorSearchHit(segment_id=str(second_id), score=0.7),
        ],
    )

    assert segments == [first, second]
    assert scores == {str(first_id): 0.9, str(second_id): 0.7}


def test_dataset_create_route_keeps_legacy_payload_shape() -> None:
    class FakeDatasetService:
        def create_dataset(self, session, name, icon, description, current_user):  # noqa: ANN001
            return None

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_dataset_service] = lambda: FakeDatasetService()

    with TestClient(app) as client:
        response = client.post(
            "/datasets",
            json={
                "name": "Docs",
                "icon": "https://example.test/icon.png",
                "description": "",
            },
        )

    assert response.status_code == 200
    assert response.json()["code"] == "success"
