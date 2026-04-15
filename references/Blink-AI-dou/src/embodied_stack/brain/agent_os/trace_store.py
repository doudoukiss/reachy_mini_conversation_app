from __future__ import annotations

import json
from pathlib import Path

from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.models import CheckpointListResponse, CheckpointRecord, RunListResponse, RunRecord


class AgentOSTraceStore:
    def __init__(self, root_dir: str = "runtime/agent_os") -> None:
        self.root_dir = Path(root_dir)
        self.run_dir = self.root_dir / "runs"
        self.checkpoint_dir = self.root_dir / "checkpoints"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_run(self, record: RunRecord) -> RunRecord:
        path = self.run_dir / f"{record.run_id}.json"
        write_json_atomic(path, record)
        return record.model_copy(deep=True)

    def get_run(self, run_id: str) -> RunRecord | None:
        path = self.run_dir / f"{run_id}.json"
        if not path.exists():
            return None
        return load_json_model_or_quarantine(path, RunRecord, quarantine_invalid=True)

    def list_runs(self, *, session_id: str | None = None, limit: int = 50) -> RunListResponse:
        items = [
            item
            for path in sorted(self.run_dir.glob("*.json"))
            if (item := load_json_model_or_quarantine(path, RunRecord, quarantine_invalid=True)) is not None
        ]
        items.sort(key=lambda item: item.created_at, reverse=True)
        if session_id:
            items = [item for item in items if item.session_id == session_id]
        return RunListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def find_run_by_trace_id(self, trace_id: str) -> RunRecord | None:
        for record in self.list_runs(limit=500).items:
            if record.trace_id == trace_id:
                return record
        return None

    def save_checkpoint(self, record: CheckpointRecord) -> CheckpointRecord:
        path = self.checkpoint_dir / f"{record.checkpoint_id}.json"
        write_json_atomic(path, record)
        return record.model_copy(deep=True)

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord | None:
        path = self.checkpoint_dir / f"{checkpoint_id}.json"
        if not path.exists():
            return None
        return load_json_model_or_quarantine(path, CheckpointRecord, quarantine_invalid=True)

    def list_checkpoints(self, *, run_id: str | None = None, limit: int = 100) -> CheckpointListResponse:
        items = [
            item
            for path in sorted(self.checkpoint_dir.glob("*.json"))
            if (item := load_json_model_or_quarantine(path, CheckpointRecord, quarantine_invalid=True)) is not None
        ]
        items.sort(key=lambda item: item.created_at, reverse=True)
        if run_id:
            items = [item for item in items if item.run_id == run_id]
        return CheckpointListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def _normalize_payload(self, payload: object) -> object:
        return json.loads(json.dumps(payload))


__all__ = [
    "AgentOSTraceStore",
]
