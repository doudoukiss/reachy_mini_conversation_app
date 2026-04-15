from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable

import httpx

from .types import EmbeddingBackend, EmbeddingBackendError


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-']+")


class HashEmbeddingBackend:
    backend_id = "hash_embed"

    def __init__(self, *, dimensions: int = 192) -> None:
        self.dimensions = dimensions

    def embed(self, inputs: list[str]) -> list[list[float]]:
        return [_hash_embed(item, dimensions=self.dimensions) for item in inputs]

    def resolved_backend_id(self) -> str:
        return self.backend_id


class OllamaEmbeddingBackend:
    backend_id = "ollama_embed"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        success_reporter: Callable[[str, float], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.success_reporter = success_reporter

    def embed(self, inputs: list[str]) -> list[list[float]]:
        if not self.base_url:
            raise EmbeddingBackendError("ollama_base_url_missing")
        if not self.model:
            raise EmbeddingBackendError("ollama_embedding_model_missing")

        try:
            start = perf_counter()
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": inputs},
                )
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise EmbeddingBackendError("ollama_embedding_timeout") from exc
        except httpx.HTTPError as exc:
            raise EmbeddingBackendError(f"ollama_embedding_transport_error:{exc}") from exc
        except ValueError as exc:
            raise EmbeddingBackendError("ollama_embedding_invalid_json") from exc

        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(inputs):
            raise EmbeddingBackendError("ollama_embedding_invalid_response")
        normalized: list[list[float]] = []
        for item in embeddings:
            if not isinstance(item, list) or not item:
                raise EmbeddingBackendError("ollama_embedding_invalid_vector")
            normalized.append([float(value) for value in item])
        if self.success_reporter is not None:
            self.success_reporter(self.model, round((perf_counter() - start) * 1000.0, 2))
        return normalized

    def resolved_backend_id(self) -> str:
        return self.backend_id


class FallbackEmbeddingBackend:
    def __init__(self, *, primary: EmbeddingBackend | None, fallback: EmbeddingBackend) -> None:
        self.primary = primary
        self.fallback = fallback
        self.backend_id = primary.backend_id if primary is not None else fallback.backend_id
        self._resolved_backend_id = self.backend_id

    def embed(self, inputs: list[str]) -> list[list[float]]:
        if self.primary is None:
            vectors = self.fallback.embed(inputs)
            self._resolved_backend_id = self.fallback.resolved_backend_id()
            return vectors
        try:
            vectors = self.primary.embed(inputs)
            self._resolved_backend_id = self.primary.resolved_backend_id()
            return vectors
        except EmbeddingBackendError:
            vectors = self.fallback.embed(inputs)
            self._resolved_backend_id = self.fallback.resolved_backend_id()
            return vectors

    def resolved_backend_id(self) -> str:
        return self._resolved_backend_id


@dataclass(frozen=True)
class RetrievalDocument:
    document_id: str
    tool_name: str
    text: str
    answer_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalHit:
    document: RetrievalDocument
    score: float
    backend_id: str


class SemanticRetriever:
    def __init__(
        self,
        *,
        embedding_backend: EmbeddingBackend,
        static_documents: list[RetrievalDocument] | None = None,
    ) -> None:
        self.embedding_backend = embedding_backend
        self.static_documents = static_documents or []
        self._cached_backend_id: str | None = None
        self._cached_vectors: list[list[float]] = []

    def search(
        self,
        query: str,
        *,
        extra_documents: list[RetrievalDocument] | None = None,
        minimum_score: float = 0.58,
    ) -> RetrievalHit | None:
        query = query.strip()
        if not query:
            return None

        documents = [*self.static_documents, *(extra_documents or [])]
        if not documents:
            return None

        query_vector = self.embedding_backend.embed([query])[0]
        active_backend_id = self.embedding_backend.resolved_backend_id()
        static_vectors = self._static_vectors()
        extra = extra_documents or []
        extra_vectors = self.embedding_backend.embed([item.text for item in extra]) if extra else []
        document_vectors = [*static_vectors, *extra_vectors]

        best_hit: RetrievalHit | None = None
        for document, vector in zip(documents, document_vectors, strict=True):
            score = cosine_similarity(query_vector, vector)
            if best_hit is None or score > best_hit.score:
                best_hit = RetrievalHit(document=document, score=score, backend_id=active_backend_id)

        if best_hit is None or best_hit.score < minimum_score:
            return None
        return best_hit

    def _static_vectors(self) -> list[list[float]]:
        active_backend_id = self.embedding_backend.resolved_backend_id()
        if self._cached_backend_id == active_backend_id and self._cached_vectors:
            return self._cached_vectors
        if not self.static_documents:
            self._cached_backend_id = active_backend_id
            self._cached_vectors = []
            return self._cached_vectors
        self._cached_backend_id = active_backend_id
        self._cached_vectors = self.embedding_backend.embed([item.text for item in self.static_documents])
        self._cached_backend_id = self.embedding_backend.resolved_backend_id()
        return self._cached_vectors


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _hash_embed(text: str, *, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = -1.0 if digest[4] % 2 else 1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]
