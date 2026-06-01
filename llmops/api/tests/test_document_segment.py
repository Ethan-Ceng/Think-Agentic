import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_current_account, get_db_session, get_document_service
from app.app_factory import create_app
from app.core.config import Settings
from app.core.file_extractor import FileExtractor
from app.models.account import Account
from app.schemas.document import DocumentResponse
from app.schemas.segment import SegmentResponse
from app.services.indexing_service import IndexingService
from app.services.segment_service import SegmentService


def test_document_response_keeps_legacy_timestamps() -> None:
    document = SimpleNamespace(
        id=uuid.uuid4(),
        dataset_id=uuid.uuid4(),
        name="doc.txt",
        position=1,
        character_count=10,
        token_count=2,
        enabled=True,
        disabled_at=None,
        status="completed",
        error="",
        updated_at=datetime(2024, 1, 1),
        created_at=datetime(2024, 1, 1),
    )

    response = DocumentResponse.from_document(document, hit_count=5)

    assert response.hit_count == 5
    assert response.status == "completed"


def test_segment_helpers_are_deterministic() -> None:
    assert SegmentService._hash_text("hello") == SegmentService._hash_text("hello")
    assert SegmentService._extract_keywords("hello hello world") == ["hello", "world"]


def test_file_extractor_and_indexing_helpers_support_local_text(tmp_path) -> None:
    source = tmp_path / "doc.html"
    source.write_text("<html><body>Hello   world\n\nhttps://example.test</body></html>", encoding="utf-8")

    text = FileExtractor.load_from_file(str(source))
    cleaned = IndexingService._clean_text_by_rule(
        text,
        {
            "pre_process_rules": [
                {"id": "remove_extra_space", "enabled": True},
                {"id": "remove_url_and_email", "enabled": True},
            ],
            "segment": {"chunk_size": 5, "chunk_overlap": 1},
        },
    )
    chunks = IndexingService._split_text(cleaned, {"segment": {"chunk_size": 5, "chunk_overlap": 1}})

    assert "Hello" in cleaned
    assert "example.test" not in cleaned
    assert chunks


def test_document_list_route_keeps_legacy_payload_shape() -> None:
    class FakeDocumentService:
        def get_documents_with_page(self, session, dataset_id, current_user, search_word, current_page, page_size):
            return [], 0, 0

        def get_document_hit_count(self, session, document_id):
            return 0

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_document_service] = lambda: FakeDocumentService()

    with TestClient(app) as client:
        response = client.get(f"/datasets/{uuid.uuid4()}/documents")

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert response.json()["data"]["list"] == []


def test_segment_response_serializes_keywords() -> None:
    segment = SimpleNamespace(
        id=uuid.uuid4(),
        dataset_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        position=1,
        content="hello",
        character_count=5,
        token_count=1,
        keywords=["hello"],
        hash="h",
        hit_count=0,
        enabled=True,
        disabled_at=None,
        status="completed",
        error="",
        updated_at=datetime(2024, 1, 1),
        created_at=datetime(2024, 1, 1),
    )

    response = SegmentResponse.from_segment(segment)

    assert response.keywords == ["hello"]
