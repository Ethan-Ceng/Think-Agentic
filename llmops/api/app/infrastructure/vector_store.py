import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from app.core.config import Settings, get_settings
from app.models.dataset import Segment


@dataclass(frozen=True)
class VectorSearchHit:
    segment_id: str
    score: float


class HashEmbeddingProvider:
    def __init__(self, dimension: int = 256) -> None:
        self.dimension = max(16, int(dimension or 256))

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        terms = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        if not terms:
            return vector

        for term in terms:
            digest = hashlib.sha256(term.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class OpenAIEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.openai_api_key:
            raise RuntimeError("Missing OpenAI API key for embeddings")

        payload = {"model": self.settings.openai_embedding_model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        base_url = self.settings.openai_base_url.rstrip("/")
        with httpx.Client(timeout=self.settings.weaviate_timeout) as client:
            response = client.post(f"{base_url}/embeddings", headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        data = sorted(body.get("data") or [], key=lambda item: int(item.get("index", 0)))
        return [item["embedding"] for item in data]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class EmbeddingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._hash_provider = HashEmbeddingProvider(self.settings.embedding_dimension)
        self._openai_provider = OpenAIEmbeddingProvider(self.settings)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.settings.embedding_provider == "openai":
            return self._openai_provider.embed_texts(texts)
        return self._hash_provider.embed_texts(texts)

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


@dataclass
class WeaviateVectorStore:
    settings: Settings | None = None
    embedding_service: EmbeddingService | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.embedding_service = self.embedding_service or EmbeddingService(self.settings)

    def upsert_segments(self, segments: list[Segment]) -> bool:
        if not self._enabled() or not segments:
            return False

        vectors = self.embedding_service.embed_texts([segment.content for segment in segments])
        self._ensure_schema(len(vectors[0]) if vectors else self.settings.embedding_dimension)
        objects = [
            {
                "class": self.settings.weaviate_collection_name,
                "id": str(segment.node_id),
                "properties": self._segment_properties(segment),
                "vector": vector,
            }
            for segment, vector in zip(segments, vectors, strict=True)
        ]
        self._request("POST", "/v1/batch/objects", json={"objects": objects})
        return True

    def search_segments(
        self,
        dataset_id: UUID,
        account_id: UUID,
        query: str,
        k: int,
        score: float,
    ) -> list[VectorSearchHit]:
        if not self._enabled() or not query:
            return []

        vector = self.embedding_service.embed_text(query)
        self._ensure_schema(len(vector))
        where_filter = {
            "operator": "And",
            "operands": [
                {"path": ["dataset_id"], "operator": "Equal", "valueText": str(dataset_id)},
                {"path": ["account_id"], "operator": "Equal", "valueText": str(account_id)},
                {"path": ["document_enabled"], "operator": "Equal", "valueBoolean": True},
                {"path": ["segment_enabled"], "operator": "Equal", "valueBoolean": True},
            ],
        }
        query_payload = {
            "query": (
                "{ Get { "
                f"{self.settings.weaviate_collection_name}"
                f"(nearVector: {{vector: {json.dumps(vector)}}}, "
                f"where: {self._to_graphql_input(where_filter)}, limit: {max(1, int(k))}) "
                "{ segment_id _additional { certainty distance } } "
                "} }"
            )
        }
        body = self._request("POST", "/v1/graphql", json=query_payload)
        rows = ((body.get("data") or {}).get("Get") or {}).get(self.settings.weaviate_collection_name) or []
        hits: list[VectorSearchHit] = []
        for row in rows:
            segment_id = str(row.get("segment_id") or "")
            if not segment_id:
                continue
            segment_score = self._score_from_additional(row.get("_additional") or {})
            if segment_score >= score:
                hits.append(VectorSearchHit(segment_id=segment_id, score=segment_score))
        return hits[:k]

    def update_document_enabled(self, node_ids: list[UUID], enabled: bool) -> bool:
        if not self._enabled() or not node_ids:
            return False
        for node_id in node_ids:
            self._request(
                "PATCH",
                f"/v1/objects/{self.settings.weaviate_collection_name}/{node_id}",
                json={"properties": {"document_enabled": enabled}},
            )
        return True

    def update_segment_enabled(self, node_id: UUID, enabled: bool) -> bool:
        if not self._enabled():
            return False
        self._request(
            "PATCH",
            f"/v1/objects/{self.settings.weaviate_collection_name}/{node_id}",
            json={"properties": {"segment_enabled": enabled}},
        )
        return True

    def delete_segments(self, node_ids: list[UUID]) -> bool:
        if not self._enabled() or not node_ids:
            return False
        for node_id in node_ids:
            self._request("DELETE", f"/v1/objects/{self.settings.weaviate_collection_name}/{node_id}")
        return True

    def delete_document(self, document_id: UUID) -> bool:
        return self._delete_by_property("document_id", str(document_id))

    def delete_dataset(self, dataset_id: UUID) -> bool:
        return self._delete_by_property("dataset_id", str(dataset_id))

    def _delete_by_property(self, property_name: str, value: str) -> bool:
        if not self._enabled():
            return False
        self._request(
            "DELETE",
            "/v1/batch/objects",
            json={
                "match": {
                    "class": self.settings.weaviate_collection_name,
                    "where": {"path": [property_name], "operator": "Equal", "valueText": value},
                },
                "output": "minimal",
            },
        )
        return True

    def _ensure_schema(self, vector_size: int) -> None:
        response = self._raw_request("GET", f"/v1/schema/{self.settings.weaviate_collection_name}")
        if response.status_code == 200:
            return
        if response.status_code != 404:
            response.raise_for_status()

        self._request(
            "POST",
            "/v1/schema",
            json={
                "class": self.settings.weaviate_collection_name,
                "vectorizer": "none",
                "vectorIndexConfig": {"distance": "cosine", "vectorCacheMaxObjects": 100000},
                "moduleConfig": {},
                "properties": [
                    {"name": "text", "dataType": ["text"]},
                    {"name": "account_id", "dataType": ["text"]},
                    {"name": "dataset_id", "dataType": ["text"]},
                    {"name": "document_id", "dataType": ["text"]},
                    {"name": "segment_id", "dataType": ["text"]},
                    {"name": "document_enabled", "dataType": ["boolean"]},
                    {"name": "segment_enabled", "dataType": ["boolean"]},
                    {"name": "position", "dataType": ["int"]},
                    {"name": "hash", "dataType": ["text"]},
                    {"name": "vector_size", "dataType": ["int"]},
                ],
            },
        )
        if vector_size <= 0:
            raise RuntimeError("Vector size must be positive")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._raw_request(method, path, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def _raw_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(timeout=self.settings.weaviate_timeout) as client:
            return client.request(method, f"{self._base_url()}{path}", headers=self._headers(), **kwargs)

    def _base_url(self) -> str:
        host = self.settings.weaviate_http_host
        if host.startswith(("http://", "https://")):
            base_url = host.rstrip("/")
            if re.search(r":\d+$", base_url):
                return base_url
            return f"{base_url}:{self.settings.weaviate_http_port}"
        return f"{self.settings.weaviate_http_scheme}://{host}:{self.settings.weaviate_http_port}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.weaviate_api_key:
            headers["Authorization"] = f"Bearer {self.settings.weaviate_api_key}"
        return headers

    def _enabled(self) -> bool:
        return bool(self.settings.weaviate_enabled)

    @staticmethod
    def _segment_properties(segment: Segment) -> dict[str, Any]:
        return {
            "text": segment.content,
            "account_id": str(segment.account_id),
            "dataset_id": str(segment.dataset_id),
            "document_id": str(segment.document_id),
            "segment_id": str(segment.id),
            "document_enabled": bool(segment.enabled),
            "segment_enabled": bool(segment.enabled),
            "position": int(segment.position or 0),
            "hash": segment.hash,
        }

    @staticmethod
    def _score_from_additional(additional: dict[str, Any]) -> float:
        if additional.get("certainty") is not None:
            return float(additional["certainty"])
        if additional.get("distance") is not None:
            return max(0.0, 1.0 - float(additional["distance"]))
        return 0.0

    @classmethod
    def _to_graphql_input(cls, value: Any) -> str:
        if isinstance(value, dict):
            return "{" + ", ".join(f"{key}: {cls._to_graphql_input(item)}" for key, item in value.items()) + "}"
        if isinstance(value, list):
            return "[" + ", ".join(cls._to_graphql_input(item) for item in value) + "]"
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, (int, float)):
            return str(value)
        return json.dumps(str(value))
