from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel, ValidationError

from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.models import DemoRunListResponse, DemoRunRecord

logger = logging.getLogger(__name__)


class DemoReportStore:
    SUMMARY_FILE = "summary.json"

    def __init__(self, report_dir: str | Path) -> None:
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        report: DemoRunRecord,
        *,
        sessions: list[BaseModel] | None = None,
        traces: list[BaseModel] | None = None,
        telemetry_log: BaseModel | None = None,
        command_history: BaseModel | None = None,
        perception_snapshots: BaseModel | None = None,
        world_model_transitions: BaseModel | None = None,
        shift_transitions: BaseModel | None = None,
        incidents: BaseModel | None = None,
        incident_timeline: BaseModel | None = None,
        executive_decisions: BaseModel | None = None,
        grounding_sources: BaseModel | None = None,
    ) -> DemoRunRecord:
        run_dir = self.report_dir / report.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        artifact_files: dict[str, str] = {}
        summary_path = run_dir / self.SUMMARY_FILE
        report.artifact_dir = str(run_dir)
        artifact_files["summary"] = str(summary_path)
        if sessions is not None:
            sessions_path = run_dir / "sessions.json"
            self._write_json(sessions_path, sessions)
            artifact_files["sessions"] = str(sessions_path)
        if traces is not None:
            trace_path = run_dir / "traces.json"
            self._write_json(trace_path, traces)
            artifact_files["traces"] = str(trace_path)
        if telemetry_log is not None:
            telemetry_path = run_dir / "telemetry_log.json"
            self._write_json(telemetry_path, telemetry_log)
            artifact_files["telemetry_log"] = str(telemetry_path)
        if command_history is not None:
            command_path = run_dir / "command_history.json"
            self._write_json(command_path, command_history)
            artifact_files["command_history"] = str(command_path)
        if perception_snapshots is not None:
            perception_path = run_dir / "perception_snapshots.json"
            self._write_json(perception_path, perception_snapshots)
            artifact_files["perception_snapshots"] = str(perception_path)
        if world_model_transitions is not None:
            transitions_path = run_dir / "world_model_transitions.json"
            self._write_json(transitions_path, world_model_transitions)
            artifact_files["world_model_transitions"] = str(transitions_path)
        if shift_transitions is not None:
            shift_transitions_path = run_dir / "shift_transitions.json"
            self._write_json(shift_transitions_path, shift_transitions)
            artifact_files["shift_transitions"] = str(shift_transitions_path)
        if incidents is not None:
            incidents_path = run_dir / "incidents.json"
            self._write_json(incidents_path, incidents)
            artifact_files["incidents"] = str(incidents_path)
        if incident_timeline is not None:
            incident_timeline_path = run_dir / "incident_timeline.json"
            self._write_json(incident_timeline_path, incident_timeline)
            artifact_files["incident_timeline"] = str(incident_timeline_path)
        if executive_decisions is not None:
            decisions_path = run_dir / "executive_decisions.json"
            self._write_json(decisions_path, executive_decisions)
            artifact_files["executive_decisions"] = str(decisions_path)
        if grounding_sources is not None:
            grounding_path = run_dir / "grounding_sources.json"
            self._write_json(grounding_path, grounding_sources)
            artifact_files["grounding_sources"] = str(grounding_path)

        report.artifact_files = artifact_files
        report.report_path = str(summary_path)
        self._write_json(summary_path, report)

        manifest_path = run_dir / "manifest.json"
        manifest = {
            "run_id": report.run_id,
            "scenario_names": report.scenario_names,
            "status": report.status.value,
            "passed": report.passed,
            "created_at": report.created_at.isoformat(),
            "completed_at": report.completed_at.isoformat() if report.completed_at else None,
            "artifact_files": artifact_files,
        }
        self._write_json(manifest_path, manifest)
        report.artifact_files["manifest"] = str(manifest_path)
        self._write_json(summary_path, report)
        return report.model_copy(deep=True)

    def get(self, run_id: str) -> DemoRunRecord | None:
        path = self._summary_path_for_run(run_id)
        if not path.exists():
            return None
        try:
            return load_json_model_or_quarantine(path, DemoRunRecord, quarantine_invalid=True)
        except (OSError, ValueError, ValidationError) as exc:
            logger.warning("Ignoring invalid demo run artifact at %s.", path, exc_info=exc)
            return None

    def list(self) -> DemoRunListResponse:
        items: list[DemoRunRecord] = []
        for path in self._iter_summary_paths():
            try:
                item = load_json_model_or_quarantine(path, DemoRunRecord, quarantine_invalid=True)
                if item is not None:
                    items.append(item)
            except (OSError, ValueError, ValidationError) as exc:
                logger.warning("Skipping invalid demo run summary at %s.", path, exc_info=exc)
        items.sort(key=lambda item: item.created_at, reverse=True)
        return DemoRunListResponse(items=items)

    def clear(self) -> None:
        for path in self.report_dir.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
                continue
            if path.suffix == ".json":
                path.unlink()

    def _summary_path_for_run(self, run_id: str) -> Path:
        directory_path = self.report_dir / run_id / self.SUMMARY_FILE
        if directory_path.exists():
            return directory_path
        return self.report_dir / f"{run_id}.json"

    def _iter_summary_paths(self) -> list[Path]:
        summary_paths = sorted(path / self.SUMMARY_FILE for path in self.report_dir.iterdir() if path.is_dir() and (path / self.SUMMARY_FILE).exists())
        legacy_paths = sorted(
            path
            for path in self.report_dir.glob("*.json")
            if path.name not in {self.SUMMARY_FILE}
        )
        return [*summary_paths, *legacy_paths]

    def _write_json(self, path: Path, payload) -> None:
        write_json_atomic(path, self._normalize_payload(payload))

    def _normalize_payload(self, payload):
        if isinstance(payload, BaseModel):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize_payload(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize_payload(value) for key, value in payload.items()}
        return payload
