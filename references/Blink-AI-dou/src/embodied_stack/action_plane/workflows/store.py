from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.contracts.action import WorkflowRunRecord
from embodied_stack.shared.contracts._common import datetime, utc_now

WORKFLOW_SCHEMA_VERSION = "stage_d.v1"


class WorkflowRunIndexEntry(BaseModel):
    workflow_run_id: str
    workflow_id: str
    status: str
    session_id: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowRunIndexEnvelope(BaseModel):
    schema_version: str = WORKFLOW_SCHEMA_VERSION
    items: list[WorkflowRunIndexEntry] = Field(default_factory=list)


class WorkflowTriggerStateItem(BaseModel):
    trigger_key: str
    workflow_id: str
    session_id: str | None = None
    run_id: str | None = None
    last_seen_at: datetime = Field(default_factory=utc_now)


class WorkflowTriggerStateEnvelope(BaseModel):
    schema_version: str = WORKFLOW_SCHEMA_VERSION
    items: list[WorkflowTriggerStateItem] = Field(default_factory=list)


class WorkflowRunStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir) / "workflows"
        self.runs_dir = self.root_dir / "runs"
        self.artifacts_dir = self.root_dir / "artifacts"
        self.run_index_path = self.root_dir / "run_index.json"
        self.trigger_state_path = self.root_dir / "trigger_state.json"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._run_index = self._load_index()
        self._trigger_state = self._load_trigger_state()

    def _load_index(self) -> WorkflowRunIndexEnvelope:
        loaded = load_json_model_or_quarantine(
            self.run_index_path,
            WorkflowRunIndexEnvelope,
            quarantine_invalid=True,
        )
        return loaded if loaded is not None else WorkflowRunIndexEnvelope()

    def _load_trigger_state(self) -> WorkflowTriggerStateEnvelope:
        loaded = load_json_model_or_quarantine(
            self.trigger_state_path,
            WorkflowTriggerStateEnvelope,
            quarantine_invalid=True,
        )
        return loaded if loaded is not None else WorkflowTriggerStateEnvelope()

    def _persist_index(self) -> None:
        write_json_atomic(self.run_index_path, self._run_index, keep_backups=2)

    def _persist_trigger_state(self) -> None:
        write_json_atomic(self.trigger_state_path, self._trigger_state, keep_backups=2)

    def run_path(self, workflow_run_id: str) -> Path:
        return self.runs_dir / f"{workflow_run_id}.json"

    def run_artifact_dir(self, workflow_run_id: str) -> Path:
        path = self.artifacts_dir / workflow_run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_run(self, run: WorkflowRunRecord) -> WorkflowRunRecord:
        run.updated_at = utc_now()
        write_json_atomic(self.run_path(run.workflow_run_id), run, keep_backups=2)
        entry = WorkflowRunIndexEntry(
            workflow_run_id=run.workflow_run_id,
            workflow_id=run.workflow_id,
            status=run.status.value,
            session_id=run.session_id,
            updated_at=run.updated_at,
        )
        for index, item in enumerate(self._run_index.items):
            if item.workflow_run_id == run.workflow_run_id:
                self._run_index.items[index] = entry
                self._persist_index()
                return run.model_copy(deep=True)
        self._run_index.items.append(entry)
        self._persist_index()
        return run.model_copy(deep=True)

    def get_run(self, workflow_run_id: str) -> WorkflowRunRecord | None:
        path = self.run_path(workflow_run_id)
        loaded = load_json_model_or_quarantine(path, WorkflowRunRecord, quarantine_invalid=True)
        return loaded.model_copy(deep=True) if loaded is not None else None

    def list_runs(self, *, session_id: str | None = None, limit: int | None = 50) -> list[WorkflowRunRecord]:
        items: list[WorkflowRunRecord] = []
        for entry in sorted(self._run_index.items, key=lambda item: item.updated_at, reverse=True):
            if session_id is not None and entry.session_id != session_id:
                continue
            run = self.get_run(entry.workflow_run_id)
            if run is not None:
                items.append(run)
            if limit is not None and len(items) >= limit:
                break
        return items

    def active_runs(self, *, session_id: str | None = None) -> list[WorkflowRunRecord]:
        return [
            item
            for item in self.list_runs(session_id=session_id, limit=None)
            if item.status.value in {"running", "waiting_for_approval", "paused", "suggested"}
        ]

    def mark_trigger_seen(
        self,
        *,
        trigger_key: str,
        workflow_id: str,
        session_id: str | None,
        run_id: str | None,
    ) -> None:
        item = WorkflowTriggerStateItem(
            trigger_key=trigger_key,
            workflow_id=workflow_id,
            session_id=session_id,
            run_id=run_id,
            last_seen_at=utc_now(),
        )
        for index, existing in enumerate(self._trigger_state.items):
            if existing.trigger_key == trigger_key:
                self._trigger_state.items[index] = item
                self._persist_trigger_state()
                return
        self._trigger_state.items.append(item)
        self._persist_trigger_state()

    def trigger_seen(self, trigger_key: str) -> bool:
        return any(item.trigger_key == trigger_key for item in self._trigger_state.items)

    def list_trigger_state(self) -> list[WorkflowTriggerStateItem]:
        return [item.model_copy(deep=True) for item in self._trigger_state.items]


__all__ = [
    "WORKFLOW_SCHEMA_VERSION",
    "WorkflowRunIndexEntry",
    "WorkflowRunIndexEnvelope",
    "WorkflowRunStore",
    "WorkflowTriggerStateEnvelope",
    "WorkflowTriggerStateItem",
]
