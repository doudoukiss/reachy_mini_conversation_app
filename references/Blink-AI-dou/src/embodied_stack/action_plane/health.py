from __future__ import annotations

from pathlib import Path

from embodied_stack.action_plane.models import ConnectorHealthEnvelope
from embodied_stack.action_plane.registry import ActionRegistry
from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.contracts.action import ConnectorHealthRecord
from embodied_stack.shared.contracts._common import utc_now


class ConnectorHealthStore:
    def __init__(self, root_dir: str | Path, *, registry: ActionRegistry) -> None:
        self._path = Path(root_dir) / "connector_health.json"
        self._registry = registry
        self._envelope = self._load()
        self._sync_defaults()

    def _load(self) -> ConnectorHealthEnvelope:
        loaded = load_json_model_or_quarantine(self._path, ConnectorHealthEnvelope, quarantine_invalid=True)
        return loaded if loaded is not None else ConnectorHealthEnvelope()

    def _persist(self) -> None:
        write_json_atomic(self._path, self._envelope, keep_backups=2)

    def _sync_defaults(self) -> None:
        by_id = {item.connector_id: item for item in self._envelope.items}
        changed = False
        for descriptor in self._registry.list_connectors():
            connector_runtime = self._registry.get_connector_runtime(descriptor.connector_id)
            runtime_record = connector_runtime.health() if connector_runtime is not None else None
            if descriptor.connector_id in by_id:
                record = by_id[descriptor.connector_id]
                expected = runtime_record or ConnectorHealthRecord(
                    connector_id=descriptor.connector_id,
                    supported=descriptor.supported,
                    configured=descriptor.configured,
                    status=(
                        "healthy"
                        if descriptor.supported and descriptor.configured
                        else ("unsupported" if not descriptor.supported else "unconfigured")
                    ),
                    detail=(
                        None
                        if descriptor.supported and descriptor.configured
                        else ("connector_unsupported" if not descriptor.supported else "connector_unconfigured")
                    ),
                )
                if record.model_dump(mode="json") != expected.model_dump(mode="json"):
                    record.supported = expected.supported
                    record.configured = expected.configured
                    record.status = expected.status
                    record.detail = expected.detail
                    record.updated_at = utc_now()
                    changed = True
                continue
            self._envelope.items.append(
                runtime_record
                or ConnectorHealthRecord(
                    connector_id=descriptor.connector_id,
                    supported=descriptor.supported,
                    configured=descriptor.configured,
                    status=(
                        "healthy"
                        if descriptor.supported and descriptor.configured
                        else ("unsupported" if not descriptor.supported else "unconfigured")
                    ),
                    detail=(
                        None
                        if descriptor.supported and descriptor.configured
                        else ("connector_unsupported" if not descriptor.supported else "connector_unconfigured")
                    ),
                )
            )
            changed = True
        if changed:
            self._persist()

    def refresh(self) -> None:
        self._sync_defaults()

    def list_records(self) -> list[ConnectorHealthRecord]:
        return [item.model_copy(deep=True) for item in self._envelope.items]

    def get_record(self, connector_id: str) -> ConnectorHealthRecord | None:
        for item in self._envelope.items:
            if item.connector_id == connector_id:
                return item.model_copy(deep=True)
        return None


__all__ = ["ConnectorHealthStore"]
