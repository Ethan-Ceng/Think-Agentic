import math
import uuid
from types import SimpleNamespace

from app.infrastructure.vector_store import HashEmbeddingProvider, WeaviateVectorStore
from app.services.indexing_service import IndexingService


def test_hash_embedding_provider_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(dimension=32)

    first = provider.embed_text("agent workflow workflow")
    second = provider.embed_text("agent workflow workflow")

    assert first == second
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_weaviate_graphql_input_serializes_filters() -> None:
    payload = WeaviateVectorStore._to_graphql_input(  # noqa: SLF001
        {
            "operator": "And",
            "operands": [
                {"path": ["dataset_id"], "operator": "Equal", "valueText": "dataset-1"},
                {"path": ["segment_enabled"], "operator": "Equal", "valueBoolean": True},
            ],
        }
    )

    assert "operator: \"And\"" in payload
    assert "valueText: \"dataset-1\"" in payload
    assert "valueBoolean: true" in payload


def test_indexing_service_vector_index_is_best_effort() -> None:
    class FailingVectorStore:
        def upsert_segments(self, segments):  # noqa: ANN001
            raise RuntimeError("offline")

    segment = SimpleNamespace(id=uuid.uuid4(), content="hello")

    IndexingService(vector_store=FailingVectorStore())._index_segments_in_vector_store([segment])  # noqa: SLF001
