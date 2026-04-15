from __future__ import annotations

from pathlib import Path

from embodied_stack.action_plane.models import ExecutionLogEnvelope
from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.contracts.action import ActionExecutionRecord


class ExecutionStore:
    def __init__(self, root_dir: str | Path) -> None:
        self._path = Path(root_dir) / "execution_log.json"
        self._envelope = self._load()

    def _load(self) -> ExecutionLogEnvelope:
        loaded = load_json_model_or_quarantine(self._path, ExecutionLogEnvelope, quarantine_invalid=True)
        return loaded if loaded is not None else ExecutionLogEnvelope()

    def _persist(self) -> None:
        write_json_atomic(self._path, self._envelope, keep_backups=2)

    def list_records(self, *, limit: int | None = None) -> list[ActionExecutionRecord]:
        items = [item.model_copy(deep=True) for item in reversed(self._envelope.items)]
        if limit is not None:
            return items[:limit]
        return items

    def last_record(self) -> ActionExecutionRecord | None:
        if not self._envelope.items:
            return None
        return self._envelope.items[-1].model_copy(deep=True)

    def get_by_action_id(self, action_id: str) -> ActionExecutionRecord | None:
        for item in reversed(self._envelope.items):
            if item.action_id == action_id:
                return item.model_copy(deep=True)
        return None

    def get_by_idempotency_key(self, idempotency_key: str) -> ActionExecutionRecord | None:
        for item in reversed(self._envelope.items):
            if item.idempotency_key == idempotency_key:
                return item.model_copy(deep=True)
        return None

    def upsert(self, record: ActionExecutionRecord) -> ActionExecutionRecord:
        for index, item in enumerate(self._envelope.items):
            if item.action_id == record.action_id:
                self._envelope.items[index] = record
                self._persist()
                return record.model_copy(deep=True)
        self._envelope.items.append(record)
        self._persist()
        return record.model_copy(deep=True)


__all__ = ["ExecutionStore"]
