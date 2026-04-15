from __future__ import annotations

import csv
import json
import logging
import shutil
from io import StringIO
from pathlib import Path

from pydantic import BaseModel, ValidationError

from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic, write_text_atomic
from embodied_stack.shared.models import ShiftReportListResponse, ShiftReportRecord, ShiftReportSummary

logger = logging.getLogger(__name__)


class ShiftReportStore:
    SUMMARY_FILE = "summary.json"

    def __init__(self, report_dir: str | Path) -> None:
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        report: ShiftReportRecord,
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
    ) -> ShiftReportRecord:
        report_dir = self.report_dir / report.report_id
        report_dir.mkdir(parents=True, exist_ok=True)

        artifact_files: dict[str, str] = {}
        summary_path = report_dir / self.SUMMARY_FILE
        report.artifact_dir = str(report_dir)
        artifact_files["summary"] = str(summary_path)

        report_path = report_dir / "report.json"
        self._write_json(report_path, report)
        artifact_files["report"] = str(report_path)

        steps_path = report_dir / "shift_steps.json"
        self._write_json(steps_path, report.steps)
        artifact_files["shift_steps"] = str(steps_path)

        if report.simulation_definition is not None:
            definition_path = report_dir / "simulation_definition.json"
            self._write_json(definition_path, report.simulation_definition)
            artifact_files["simulation_definition"] = str(definition_path)

        score_path = report_dir / "score_summary.json"
        self._write_json(score_path, report.score_summary)
        artifact_files["score_summary"] = str(score_path)

        metrics_csv_path = report_dir / "metrics.csv"
        write_text_atomic(metrics_csv_path, self._metrics_csv(report))
        artifact_files["metrics_csv"] = str(metrics_csv_path)

        if sessions is not None:
            sessions_path = report_dir / "sessions.json"
            self._write_json(sessions_path, sessions)
            artifact_files["sessions"] = str(sessions_path)
        if traces is not None:
            traces_path = report_dir / "traces.json"
            self._write_json(traces_path, traces)
            artifact_files["traces"] = str(traces_path)
        if telemetry_log is not None:
            telemetry_path = report_dir / "telemetry_log.json"
            self._write_json(telemetry_path, telemetry_log)
            artifact_files["telemetry_log"] = str(telemetry_path)
        if command_history is not None:
            command_path = report_dir / "command_history.json"
            self._write_json(command_path, command_history)
            artifact_files["command_history"] = str(command_path)
        if perception_snapshots is not None:
            perception_path = report_dir / "perception_snapshots.json"
            self._write_json(perception_path, perception_snapshots)
            artifact_files["perception_snapshots"] = str(perception_path)
        if world_model_transitions is not None:
            world_model_path = report_dir / "world_model_transitions.json"
            self._write_json(world_model_path, world_model_transitions)
            artifact_files["world_model_transitions"] = str(world_model_path)
        if shift_transitions is not None:
            shift_path = report_dir / "shift_transitions.json"
            self._write_json(shift_path, shift_transitions)
            artifact_files["shift_transitions"] = str(shift_path)
        if incidents is not None:
            incidents_path = report_dir / "incidents.json"
            self._write_json(incidents_path, incidents)
            artifact_files["incidents"] = str(incidents_path)
        if incident_timeline is not None:
            incident_timeline_path = report_dir / "incident_timeline.json"
            self._write_json(incident_timeline_path, incident_timeline)
            artifact_files["incident_timeline"] = str(incident_timeline_path)
        if executive_decisions is not None:
            decisions_path = report_dir / "executive_decisions.json"
            self._write_json(decisions_path, executive_decisions)
            artifact_files["executive_decisions"] = str(decisions_path)
        if grounding_sources is not None:
            grounding_path = report_dir / "grounding_sources.json"
            self._write_json(grounding_path, grounding_sources)
            artifact_files["grounding_sources"] = str(grounding_path)

        manifest_path = report_dir / "manifest.json"
        manifest = {
            "report_id": report.report_id,
            "schema_version": report.schema_version,
            "simulation_name": report.simulation_name,
            "site_name": report.site_name,
            "status": report.status.value,
            "created_at": report.created_at.isoformat(),
            "completed_at": report.completed_at.isoformat() if report.completed_at else None,
            "artifact_files": artifact_files,
        }
        self._write_json(manifest_path, manifest)
        artifact_files["manifest"] = str(manifest_path)

        report.artifact_files = artifact_files
        self._write_json(summary_path, self._summary_from_report(report))
        self._write_json(report_path, report)
        return report.model_copy(deep=True)

    def get(self, report_id: str) -> ShiftReportRecord | None:
        path = self.report_dir / report_id / "report.json"
        if not path.exists():
            return None
        try:
            return load_json_model_or_quarantine(path, ShiftReportRecord, quarantine_invalid=True)
        except (OSError, ValueError, ValidationError) as exc:
            logger.warning("Ignoring invalid shift report artifact at %s.", path, exc_info=exc)
            return None

    def list(self, *, limit: int = 25) -> ShiftReportListResponse:
        items: list[ShiftReportSummary] = []
        for summary_path in sorted(self.report_dir.glob(f"*/{self.SUMMARY_FILE}")):
            try:
                item = load_json_model_or_quarantine(summary_path, ShiftReportSummary, quarantine_invalid=True)
                if item is not None:
                    items.append(item)
            except (OSError, ValueError, ValidationError) as exc:
                logger.warning("Skipping invalid shift report summary at %s.", summary_path, exc_info=exc)
                continue
        items.sort(key=lambda item: item.created_at, reverse=True)
        return ShiftReportListResponse(items=items[:limit])

    def clear(self) -> None:
        for path in self.report_dir.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
                continue
            if path.suffix == ".json":
                path.unlink()

    def _summary_from_report(self, report: ShiftReportRecord) -> ShiftReportSummary:
        return ShiftReportSummary(
            report_id=report.report_id,
            schema_version=report.schema_version,
            simulation_name=report.simulation_name,
            description=report.description,
            site_name=report.site_name,
            fixture_path=report.fixture_path,
            created_at=report.created_at,
            completed_at=report.completed_at,
            status=report.status,
            configured_dialogue_backend=report.configured_dialogue_backend,
            observed_dialogue_backends=list(report.observed_dialogue_backends),
            runtime_profile=report.runtime_profile,
            deployment_target=report.deployment_target,
            session_ids=list(report.session_ids),
            metrics=report.metrics.model_copy(deep=True),
            score_summary=report.score_summary.model_copy(deep=True),
            artifact_dir=report.artifact_dir,
            artifact_files=dict(report.artifact_files),
            notes=list(report.notes),
        )

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

    def _metrics_csv(self, report: ShiftReportRecord) -> str:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["metric", "value"])
        metrics = report.metrics.model_dump(mode="json")
        for key, value in metrics.items():
            writer.writerow([key, value])
        writer.writerow(["score", report.score_summary.score])
        writer.writerow(["max_score", report.score_summary.max_score])
        writer.writerow(["rating", report.score_summary.rating])
        return output.getvalue()
