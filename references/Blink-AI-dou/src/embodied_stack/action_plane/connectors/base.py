from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from embodied_stack.shared.contracts.action import (
    ActionArtifactRecord,
    ActionRequestRecord,
    ConnectorDescriptorRecord,
    ConnectorHealthRecord,
)
from embodied_stack.shared.contracts._common import utc_now


class ConnectorActionError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


class ConnectorPreviewResult(BaseModel):
    summary: str | None = None
    detail: str | None = None
    output_payload: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)


class ConnectorExecutionResult(BaseModel):
    summary: str | None = None
    detail: str | None = None
    output_payload: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)


class ActionConnector(Protocol):
    @property
    def descriptor(self) -> ConnectorDescriptorRecord:
        ...

    def supports_action(self, action_name: str) -> bool:
        ...

    def health(self) -> ConnectorHealthRecord:
        ...

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        ...

    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        ...


class BaseConnector:
    def __init__(self, descriptor: ConnectorDescriptorRecord) -> None:
        self._descriptor = descriptor

    @property
    def descriptor(self) -> ConnectorDescriptorRecord:
        return self._descriptor.model_copy(deep=True)

    def supports_action(self, action_name: str) -> bool:
        return action_name in self._descriptor.supported_actions

    def health(self) -> ConnectorHealthRecord:
        return ConnectorHealthRecord(
            connector_id=self._descriptor.connector_id,
            supported=self._descriptor.supported,
            configured=self._descriptor.configured,
            status=(
                "healthy"
                if self._descriptor.supported and self._descriptor.configured
                else ("unsupported" if not self._descriptor.supported else "unconfigured")
            ),
            detail=None if self._descriptor.supported and self._descriptor.configured else "connector_not_available",
            updated_at=utc_now(),
        )

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        del action_name, request, runtime_context
        return ConnectorPreviewResult(summary=reason, detail=reason)


def artifact_for_path(*, kind: str, label: str, path: Path, metadata: dict[str, Any] | None = None) -> ActionArtifactRecord:
    return ActionArtifactRecord(
        kind=kind,
        label=label,
        path=str(path),
        metadata=dict(metadata or {}),
    )


__all__ = [
    "ActionConnector",
    "BaseConnector",
    "ConnectorActionError",
    "ConnectorExecutionResult",
    "ConnectorPreviewResult",
    "artifact_for_path",
]
