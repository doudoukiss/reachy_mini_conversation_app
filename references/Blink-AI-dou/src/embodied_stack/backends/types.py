from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from datetime import datetime

from embodied_stack.shared.models import RuntimeBackendAvailability, RuntimeBackendKind, RuntimeBackendStatus


@dataclass(frozen=True)
class BackendProfileSpec:
    name: str
    text_candidates: tuple[str, ...]
    vision_candidates: tuple[str, ...]
    embedding_candidates: tuple[str, ...]
    stt_candidates: tuple[str, ...]
    tts_candidates: tuple[str, ...]
    note: str
    memory_pressure_note: str


@dataclass(frozen=True)
class BackendRouteDecision:
    kind: RuntimeBackendKind
    backend_id: str
    status: RuntimeBackendAvailability
    provider: str
    model: str | None = None
    local: bool = False
    cloud: bool = False
    requested_backend_id: str | None = None
    fallback_from: str | None = None
    detail: str | None = None
    requested_model: str | None = None
    active_model: str | None = None
    reachable: bool | None = None
    installed: bool | None = None
    warm: bool | None = None
    keep_alive: str | None = None
    last_success_latency_ms: float | None = None
    last_failure_reason: str | None = None
    last_failure_at: datetime | None = None
    last_timeout_seconds: float | None = None
    cold_start_retry_used: bool = False

    def to_status_model(self) -> RuntimeBackendStatus:
        return RuntimeBackendStatus(
            kind=self.kind,
            backend_id=self.backend_id,
            status=self.status,
            provider=self.provider,
            model=self.model,
            local=self.local,
            cloud=self.cloud,
            requested_backend_id=self.requested_backend_id,
            fallback_from=self.fallback_from,
            detail=self.detail,
            requested_model=self.requested_model,
            active_model=self.active_model,
            reachable=self.reachable,
            installed=self.installed,
            warm=self.warm,
            keep_alive=self.keep_alive,
            last_success_latency_ms=self.last_success_latency_ms,
            last_failure_reason=self.last_failure_reason,
            last_failure_at=self.last_failure_at,
            last_timeout_seconds=self.last_timeout_seconds,
            cold_start_retry_used=self.cold_start_retry_used,
        )


class EmbeddingBackendError(RuntimeError):
    pass


class EmbeddingBackend(Protocol):
    backend_id: str

    def embed(self, inputs: list[str]) -> list[list[float]]:
        ...

    def resolved_backend_id(self) -> str:
        ...
