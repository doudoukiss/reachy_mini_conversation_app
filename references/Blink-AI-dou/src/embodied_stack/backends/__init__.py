from .embeddings import (
    FallbackEmbeddingBackend,
    HashEmbeddingBackend,
    OllamaEmbeddingBackend,
    RetrievalDocument,
    RetrievalHit,
    SemanticRetriever,
    cosine_similarity,
)
from .profiles import BACKEND_PROFILES, backend_candidates_for, backend_profile_names, resolve_backend_profile, resolve_backend_profile_name
from .router import BackendRouter, OllamaRuntimeProbe
from .types import BackendProfileSpec, BackendRouteDecision, EmbeddingBackend, EmbeddingBackendError

__all__ = [
    "BACKEND_PROFILES",
    "BackendProfileSpec",
    "BackendRouteDecision",
    "BackendRouter",
    "EmbeddingBackend",
    "EmbeddingBackendError",
    "FallbackEmbeddingBackend",
    "HashEmbeddingBackend",
    "OllamaEmbeddingBackend",
    "OllamaRuntimeProbe",
    "RetrievalDocument",
    "RetrievalHit",
    "SemanticRetriever",
    "backend_candidates_for",
    "backend_profile_names",
    "cosine_similarity",
    "resolve_backend_profile",
    "resolve_backend_profile_name",
]
