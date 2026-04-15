from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from embodied_stack.action_plane.bundles import ActionBundleStore
from embodied_stack.brain.memory import apply_episode_redaction_profile, collect_sensitive_content_flags
from embodied_stack.brain.memory_layers import MemoryLayerService
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.coordinator import EdgeGateway
from embodied_stack.persistence import load_json_value_or_quarantine, quarantine_invalid_file, write_json_atomic
from embodied_stack.demo.report_store import DemoReportStore
from embodied_stack.demo.shift_reports import ShiftReportStore
from embodied_stack.shared.contracts._common import (
    CommandType,
    EpisodeAssetKind,
    EpisodeLabelName,
    EpisodeSourceType,
    ExportRedactionProfile,
    SensitiveContentFlag,
)
from embodied_stack.shared.contracts.brain import (
    EpisodicMemoryRecord,
    ExecutiveDecisionType,
    GroundingSourceRecord,
    GroundingSourceType,
    IncidentTicketRecord,
    IncidentTimelineRecord,
    ProceduralMemoryRecord,
    RelationshipMemoryRecord,
    SessionRecord,
    SessionStatus,
    SemanticMemoryRecord,
    TraceOutcome,
    TraceRecord,
    UserMemoryRecord,
    WorldState,
)
from embodied_stack.shared.contracts.demo import (
    DemoRunRecord,
    EpisodeAcknowledgementRecord,
    EpisodeAnnotationLabel,
    EpisodeAssetReference,
    EpisodeCommandRecord,
    EpisodeExportRunRequest,
    EpisodeExportSessionRequest,
    EpisodeExportShiftReportRequest,
    EpisodeSessionMetadata,
    EpisodeTelemetryRecord,
    EpisodeToolCallRecord,
    EpisodeTranscriptEntry,
    ShiftReportRecord,
)
from embodied_stack.shared.contracts.episode import (
    EpisodeDatasetMembership,
    EpisodeListResponseV2,
    EpisodeManifestV2,
    EpisodeRecordV2,
    EpisodeSummaryV2,
    TeacherAnnotationRecord,
    TeacherSupervisionSummary,
)
from embodied_stack.shared.contracts.edge import CommandHistoryResponse, TelemetryLogResponse
from embodied_stack.shared.contracts.perception import (
    EmbodiedWorldModel,
    ExecutiveDecisionRecord,
    PerceptionFactRecord,
    PerceptionSnapshotRecord,
    WorldModelTransitionRecord,
)

logger = logging.getLogger(__name__)


class EpisodeStore:
    SUMMARY_FILE = "summary.json"
    EPISODE_FILE = "episode.json"
    MANIFEST_FILE = "manifest.json"

    def __init__(self, export_dir: str | Path) -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        episode: EpisodeRecordV2,
        *,
        extra_artifacts: dict[str, Any] | None = None,
    ) -> EpisodeRecordV2:
        episode_dir = self.export_dir / episode.episode_id
        episode_dir.mkdir(parents=True, exist_ok=True)

        artifact_files = {
            "summary": str(episode_dir / self.SUMMARY_FILE),
            "episode": str(episode_dir / self.EPISODE_FILE),
            "sessions": str(episode_dir / "sessions.json"),
            "input_events": str(episode_dir / "input_events.json"),
            "transcript": str(episode_dir / "transcript.json"),
            "traces": str(episode_dir / "traces.json"),
            "tool_calls": str(episode_dir / "tool_calls.json"),
            "perception_snapshots": str(episode_dir / "perception_snapshots.json"),
            "world_model_transitions": str(episode_dir / "world_model_transitions.json"),
            "executive_decisions": str(episode_dir / "executive_decisions.json"),
            "incidents": str(episode_dir / "incidents.json"),
            "incident_timeline": str(episode_dir / "incident_timeline.json"),
            "commands": str(episode_dir / "commands.json"),
            "acknowledgements": str(episode_dir / "acknowledgements.json"),
            "telemetry": str(episode_dir / "telemetry.json"),
            "episodic_memory": str(episode_dir / "episodic_memory.json"),
            "semantic_memory": str(episode_dir / "semantic_memory.json"),
            "profile_memory": str(episode_dir / "profile_memory.json"),
            "relationship_memory": str(episode_dir / "relationship_memory.json"),
            "procedural_memory": str(episode_dir / "procedural_memory.json"),
            "grounding_sources": str(episode_dir / "grounding_sources.json"),
            "asset_refs": str(episode_dir / "asset_refs.json"),
            "annotations": str(episode_dir / "annotations.json"),
            "scene_facts": str(episode_dir / "scene_facts.json"),
            "memory_actions": str(episode_dir / "memory_actions.json"),
            "memory_reviews": str(episode_dir / "memory_reviews.json"),
            "memory_retrievals": str(episode_dir / "memory_retrievals.json"),
            "teacher_annotations": str(episode_dir / "teacher_annotations.json"),
            "teacher_supervision_summary": str(episode_dir / "teacher_supervision_summary.json"),
            "benchmark_labels": str(episode_dir / "benchmark_labels.json"),
            "dataset_memberships": str(episode_dir / "dataset_memberships.json"),
            "manifest": str(episode_dir / self.MANIFEST_FILE),
        }
        if extra_artifacts:
            for name in extra_artifacts:
                artifact_files[name] = str(episode_dir / f"{name}.json")

        episode.artifact_dir = str(episode_dir)
        episode.artifact_files = artifact_files

        summary = self._build_summary(episode)
        manifest = self._manifest_from_episode(episode)

        self._write_json(Path(artifact_files["summary"]), summary)
        self._write_json(Path(artifact_files["episode"]), episode)
        self._write_json(Path(artifact_files["sessions"]), episode.sessions)
        self._write_json(Path(artifact_files["input_events"]), episode.input_events)
        self._write_json(Path(artifact_files["transcript"]), episode.transcript)
        self._write_json(Path(artifact_files["traces"]), episode.traces)
        self._write_json(Path(artifact_files["tool_calls"]), episode.tool_calls)
        self._write_json(Path(artifact_files["perception_snapshots"]), episode.perception_snapshots)
        self._write_json(Path(artifact_files["world_model_transitions"]), episode.world_model_transitions)
        self._write_json(Path(artifact_files["executive_decisions"]), episode.executive_decisions)
        self._write_json(Path(artifact_files["incidents"]), episode.incidents)
        self._write_json(Path(artifact_files["incident_timeline"]), episode.incident_timeline)
        self._write_json(Path(artifact_files["commands"]), episode.commands)
        self._write_json(Path(artifact_files["acknowledgements"]), episode.acknowledgements)
        self._write_json(Path(artifact_files["telemetry"]), episode.telemetry)
        self._write_json(Path(artifact_files["episodic_memory"]), episode.episodic_memory)
        self._write_json(Path(artifact_files["semantic_memory"]), episode.semantic_memory)
        self._write_json(Path(artifact_files["profile_memory"]), episode.profile_memory)
        self._write_json(Path(artifact_files["relationship_memory"]), episode.relationship_memory)
        self._write_json(Path(artifact_files["procedural_memory"]), episode.procedural_memory)
        self._write_json(Path(artifact_files["grounding_sources"]), episode.grounding_sources)
        self._write_json(Path(artifact_files["asset_refs"]), episode.asset_refs)
        self._write_json(Path(artifact_files["annotations"]), episode.annotations)
        self._write_json(Path(artifact_files["scene_facts"]), episode.scene_facts)
        self._write_json(Path(artifact_files["memory_actions"]), episode.memory_actions)
        self._write_json(Path(artifact_files["memory_reviews"]), episode.memory_reviews)
        self._write_json(Path(artifact_files["memory_retrievals"]), episode.memory_retrievals)
        self._write_json(Path(artifact_files["teacher_annotations"]), episode.teacher_annotations)
        self._write_json(Path(artifact_files["teacher_supervision_summary"]), episode.teacher_supervision_summary)
        self._write_json(Path(artifact_files["benchmark_labels"]), episode.benchmark_labels)
        self._write_json(Path(artifact_files["dataset_memberships"]), episode.dataset_memberships)
        if extra_artifacts:
            for name, payload in extra_artifacts.items():
                self._write_json(Path(artifact_files[name]), payload)
        self._write_json(Path(artifact_files["manifest"]), manifest)
        return episode.model_copy(deep=True)

    def get(self, episode_id: str) -> EpisodeRecordV2 | None:
        path = self.export_dir / episode_id / self.EPISODE_FILE
        if not path.exists():
            return None
        try:
            payload = path.read_text(encoding="utf-8")
            try:
                record = EpisodeRecordV2.model_validate_json(payload)
                if record.schema_version != "blink_episode/v2":
                    raise ValueError("legacy_episode_schema")
                return record
            except ValidationError:
                from embodied_stack.shared.contracts.demo import EpisodeRecord as EpisodeRecordV1

                return self._upgrade_v1_record(EpisodeRecordV1.model_validate_json(payload))
            except ValueError:
                from embodied_stack.shared.contracts.demo import EpisodeRecord as EpisodeRecordV1

                return self._upgrade_v1_record(EpisodeRecordV1.model_validate_json(payload))
        except (OSError, ValueError, ValidationError) as exc:
            quarantine_invalid_file(path)
            logger.warning("Ignoring invalid episode artifact at %s.", path, exc_info=exc)
            return None

    def list(self) -> EpisodeListResponseV2:
        items: list[EpisodeSummaryV2] = []
        for summary_path in sorted(self.export_dir.glob(f"*/{self.SUMMARY_FILE}")):
            try:
                payload = summary_path.read_text(encoding="utf-8")
                try:
                    item = EpisodeSummaryV2.model_validate_json(payload)
                    if item.schema_version != "blink_episode/v2":
                        raise ValueError("legacy_episode_summary")
                    items.append(item)
                except ValidationError:
                    from embodied_stack.shared.contracts.demo import EpisodeSummary as EpisodeSummaryV1

                    items.append(self._upgrade_v1_summary(EpisodeSummaryV1.model_validate_json(payload)))
                except ValueError:
                    from embodied_stack.shared.contracts.demo import EpisodeSummary as EpisodeSummaryV1

                    items.append(self._upgrade_v1_summary(EpisodeSummaryV1.model_validate_json(payload)))
            except (OSError, ValueError, ValidationError) as exc:
                quarantine_invalid_file(summary_path)
                logger.warning("Skipping invalid episode summary at %s.", summary_path, exc_info=exc)
                continue
        items.sort(key=lambda item: item.exported_at, reverse=True)
        return EpisodeListResponseV2(items=items)

    def _build_summary(self, episode: EpisodeRecordV2) -> EpisodeSummaryV2:
        return EpisodeSummaryV2(
            episode_id=episode.episode_id,
            schema_version=episode.schema_version,
            source_type=episode.source_type,
            source_id=episode.source_id,
            exported_at=episode.exported_at,
            session_ids=episode.session_ids,
            scenario_names=episode.scenario_names,
            configured_dialogue_backend=episode.configured_dialogue_backend,
            observed_dialogue_backends=episode.observed_dialogue_backends,
            runtime_profile=episode.runtime_profile,
            deployment_target=episode.deployment_target,
            started_at=episode.started_at,
            completed_at=episode.completed_at,
            transcript_turn_count=len(episode.transcript),
            trace_count=len(episode.traces),
            tool_call_count=len(episode.tool_calls),
            perception_snapshot_count=len(episode.perception_snapshots),
            world_model_transition_count=len(episode.world_model_transitions),
            executive_decision_count=len(episode.executive_decisions),
            incident_count=len(episode.incidents),
            incident_timeline_count=len(episode.incident_timeline),
            command_count=len(episode.commands),
            acknowledgement_count=len(episode.acknowledgements),
            telemetry_count=len(episode.telemetry),
            episodic_memory_count=len(episode.episodic_memory),
            semantic_memory_count=len(episode.semantic_memory),
            profile_memory_count=len(episode.profile_memory),
            asset_ref_count=len(episode.asset_refs),
            annotation_count=len(episode.annotations),
            scene_fact_count=len(episode.scene_facts),
            memory_action_count=len(episode.memory_actions),
            memory_review_count=len(episode.memory_reviews),
            memory_retrieval_count=len(episode.memory_retrievals),
            teacher_annotation_count=len(episode.teacher_annotations),
            input_event_count=len(episode.input_events),
            benchmark_label_count=len(episode.benchmark_labels),
            dataset_membership_count=len(episode.dataset_memberships),
            run_count=len(episode.run_ids),
            redaction_profile=episode.redaction_profile,
            sensitive_content_flags=list(episode.sensitive_content_flags),
            redactions_applied=list(episode.redactions_applied),
            artifact_dir=episode.artifact_dir,
            artifact_files=dict(episode.artifact_files),
            derived_artifact_files=dict(episode.derived_artifact_files),
            notes=list(episode.notes),
            final_reply_text=episode.final_reply_text,
            outcome_label=episode.outcome_label,
        )

    def _manifest_from_episode(self, episode: EpisodeRecordV2) -> EpisodeManifestV2:
        return EpisodeManifestV2(
            episode_id=episode.episode_id,
            source_type=episode.source_type,
            source_id=episode.source_id,
            exported_at=episode.exported_at,
            session_ids=episode.session_ids,
            scenario_names=episode.scenario_names,
            artifact_files=dict(episode.artifact_files),
            derived_artifact_files=dict(episode.derived_artifact_files),
            redaction_profile=episode.redaction_profile,
            sensitive_content_flags=list(episode.sensitive_content_flags),
            redactions_applied=list(episode.redactions_applied),
            dataset_memberships=[item.model_copy(deep=True) for item in episode.dataset_memberships],
            benchmark_labels=list(episode.benchmark_labels),
            notes=list(episode.notes),
            outcome_label=episode.outcome_label,
            teacher_annotation_count=len(episode.teacher_annotations),
            memory_retrieval_count=len(episode.memory_retrievals),
        )

    def _teacher_supervision_summary(
        self,
        annotations: list[TeacherAnnotationRecord],
    ) -> TeacherSupervisionSummary:
        authors: list[str] = []
        primary_kinds = []
        benchmark_tags: list[str] = []
        outcome_labels: list[str] = []
        for annotation in annotations:
            if annotation.author not in authors:
                authors.append(annotation.author)
            if annotation.primary_kind not in primary_kinds:
                primary_kinds.append(annotation.primary_kind)
            for tag in annotation.benchmark_tags:
                if tag not in benchmark_tags:
                    benchmark_tags.append(tag)
            if annotation.outcome_label and annotation.outcome_label not in outcome_labels:
                outcome_labels.append(annotation.outcome_label)
        return TeacherSupervisionSummary(
            annotation_count=len(annotations),
            authors=authors,
            primary_kinds=primary_kinds,
            benchmark_tags=benchmark_tags,
            outcome_labels=outcome_labels,
        )

    def replace_teacher_annotations(
        self,
        episode_id: str,
        annotations: list[TeacherAnnotationRecord],
        *,
        outcome_label: str | None = None,
    ) -> None:
        episode = self.get(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        episode.teacher_annotations = [item.model_copy(deep=True) for item in annotations]
        episode.teacher_annotation_count = len(episode.teacher_annotations)
        episode.teacher_supervision_summary = self._teacher_supervision_summary(episode.teacher_annotations)
        if outcome_label is not None:
            episode.outcome_label = outcome_label
        artifact_dir = Path(episode.artifact_dir or self.export_dir / episode_id)
        teacher_path = artifact_dir / "teacher_annotations.json"
        summary_path = artifact_dir / self.SUMMARY_FILE
        episode_path = artifact_dir / self.EPISODE_FILE
        manifest_path = artifact_dir / self.MANIFEST_FILE
        supervision_path = artifact_dir / "teacher_supervision_summary.json"
        episode.artifact_files["teacher_annotations"] = str(teacher_path)
        episode.artifact_files["teacher_supervision_summary"] = str(supervision_path)
        self._write_json(teacher_path, episode.teacher_annotations)
        self._write_json(supervision_path, episode.teacher_supervision_summary)
        self._write_json(summary_path, self._build_summary(episode))
        self._write_json(episode_path, episode)
        self._write_json(manifest_path, self._manifest_from_episode(episode))

    def attach_derived_artifacts(
        self,
        episode_id: str,
        *,
        derived_artifact_files: dict[str, str],
        notes: list[str] | None = None,
        dataset_memberships: list[EpisodeDatasetMembership] | None = None,
    ) -> EpisodeRecordV2:
        episode = self.get(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        episode.derived_artifact_files.update({key: value for key, value in derived_artifact_files.items() if value})
        if dataset_memberships is not None:
            by_dataset_id = {item.dataset_id: item.model_copy(deep=True) for item in episode.dataset_memberships}
            for membership in dataset_memberships:
                by_dataset_id[membership.dataset_id] = membership.model_copy(deep=True)
            episode.dataset_memberships = list(by_dataset_id.values())
        if notes:
            for note in notes:
                if note not in episode.notes:
                    episode.notes.append(note)
        artifact_dir = Path(episode.artifact_dir or self.export_dir / episode_id)
        summary_path = artifact_dir / self.SUMMARY_FILE
        episode_path = artifact_dir / self.EPISODE_FILE
        manifest_path = artifact_dir / self.MANIFEST_FILE
        self._write_json(summary_path, self._build_summary(episode))
        self._write_json(episode_path, episode)
        self._write_json(manifest_path, self._manifest_from_episode(episode))
        return episode.model_copy(deep=True)

    def _upgrade_v1_summary(self, summary) -> EpisodeSummaryV2:
        return EpisodeSummaryV2(
            episode_id=summary.episode_id,
            schema_version="blink_episode/v2",
            source_type=summary.source_type,
            source_id=summary.source_id,
            exported_at=summary.exported_at,
            session_ids=list(summary.session_ids),
            scenario_names=list(summary.scenario_names),
            configured_dialogue_backend=summary.configured_dialogue_backend,
            observed_dialogue_backends=list(summary.observed_dialogue_backends),
            runtime_profile=summary.runtime_profile,
            deployment_target=summary.deployment_target,
            started_at=summary.started_at,
            completed_at=summary.completed_at,
            transcript_turn_count=summary.transcript_turn_count,
            trace_count=summary.trace_count,
            tool_call_count=summary.tool_call_count,
            perception_snapshot_count=summary.perception_snapshot_count,
            world_model_transition_count=summary.world_model_transition_count,
            executive_decision_count=summary.executive_decision_count,
            incident_count=summary.incident_count,
            incident_timeline_count=summary.incident_timeline_count,
            command_count=summary.command_count,
            acknowledgement_count=summary.acknowledgement_count,
            telemetry_count=summary.telemetry_count,
            episodic_memory_count=summary.episodic_memory_count,
            semantic_memory_count=summary.semantic_memory_count,
            profile_memory_count=summary.profile_memory_count,
            asset_ref_count=summary.asset_ref_count,
            annotation_count=summary.annotation_count,
            scene_fact_count=0,
            memory_action_count=0,
            memory_review_count=0,
            memory_retrieval_count=0,
            teacher_annotation_count=0,
            input_event_count=0,
            benchmark_label_count=0,
            dataset_membership_count=0,
            run_count=0,
            redaction_profile=ExportRedactionProfile.LOCAL_FULL,
            sensitive_content_flags=[],
            artifact_dir=summary.artifact_dir,
            artifact_files=dict(summary.artifact_files),
            redactions_applied=list(summary.redactions_applied),
            notes=list(summary.notes),
        )

    def _upgrade_v1_record(self, episode) -> EpisodeRecordV2:
        return EpisodeRecordV2(
            episode_id=episode.episode_id,
            schema_version="blink_episode/v2",
            source_type=episode.source_type,
            source_id=episode.source_id,
            exported_at=episode.exported_at,
            session_ids=list(episode.session_ids),
            scenario_names=list(episode.scenario_names),
            configured_dialogue_backend=episode.configured_dialogue_backend,
            observed_dialogue_backends=list(episode.observed_dialogue_backends),
            runtime_profile=episode.runtime_profile,
            deployment_target=episode.deployment_target,
            started_at=episode.started_at,
            completed_at=episode.completed_at,
            redactions_applied=list(episode.redactions_applied),
            artifact_dir=episode.artifact_dir,
            artifact_files=dict(episode.artifact_files),
            notes=list(episode.notes),
            sessions=[item.model_copy(deep=True) for item in episode.sessions],
            input_events=[trace.event.model_copy(deep=True) for trace in episode.traces],
            transcript=[item.model_copy(deep=True) for item in episode.transcript],
            traces=[item.model_copy(deep=True) for item in episode.traces],
            tool_calls=[item.model_copy(deep=True) for item in episode.tool_calls],
            perception_snapshots=[item.model_copy(deep=True) for item in episode.perception_snapshots],
            world_model_transitions=[item.model_copy(deep=True) for item in episode.world_model_transitions],
            executive_decisions=[item.model_copy(deep=True) for item in episode.executive_decisions],
            incidents=[item.model_copy(deep=True) for item in episode.incidents],
            incident_timeline=[item.model_copy(deep=True) for item in episode.incident_timeline],
            commands=[item.model_copy(deep=True) for item in episode.commands],
            acknowledgements=[item.model_copy(deep=True) for item in episode.acknowledgements],
            telemetry=[item.model_copy(deep=True) for item in episode.telemetry],
            episodic_memory=[item.model_copy(deep=True) for item in episode.episodic_memory],
            semantic_memory=[item.model_copy(deep=True) for item in episode.semantic_memory],
            profile_memory=[item.model_copy(deep=True) for item in episode.profile_memory],
            grounding_sources=[item.model_copy(deep=True) for item in episode.grounding_sources],
            final_world_state=episode.final_world_state.model_copy(deep=True) if episode.final_world_state else None,
            final_world_model=episode.final_world_model.model_copy(deep=True) if episode.final_world_model else None,
            asset_refs=[item.model_copy(deep=True) for item in episode.asset_refs],
            annotations=[item.model_copy(deep=True) for item in episode.annotations],
            teacher_supervision_summary=TeacherSupervisionSummary(),
            benchmark_labels=[],
            dataset_memberships=[],
            redaction_profile=ExportRedactionProfile.LOCAL_FULL,
            sensitive_content_flags=[],
            final_reply_text=next((trace.response.reply_text for trace in reversed(episode.traces) if trace.response.reply_text), None),
            body_action_types=list({command.command.command_type for command in episode.commands}),
            fallback_reasons=[reason for trace in episode.traces if trace.reasoning.fallback_reason for reason in [trace.reasoning.fallback_reason]],
        )

    def _write_json(self, path: Path, payload: Any) -> None:
        write_json_atomic(path, self._normalize_payload(payload))

    def _normalize_payload(self, payload: Any) -> Any:
        if isinstance(payload, BaseModel):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize_payload(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize_payload(value) for key, value in payload.items()}
        return payload


class BlinkEpisodeExporter:
    def __init__(
        self,
        *,
        settings: Settings,
        orchestrator: BrainOrchestrator,
        report_store: DemoReportStore,
        shift_report_store: ShiftReportStore,
        episode_store: EpisodeStore,
        edge_gateway: EdgeGateway | None = None,
    ) -> None:
        self.settings = settings
        self.orchestrator = orchestrator
        self.report_store = report_store
        self.shift_report_store = shift_report_store
        self.episode_store = episode_store
        self.edge_gateway = edge_gateway
        self.memory_layers = MemoryLayerService(orchestrator.memory)

    def _action_bundle_store(self) -> ActionBundleStore:
        return ActionBundleStore(self.settings.blink_action_plane_export_dir)

    def list_episodes(self) -> EpisodeListResponseV2:
        return self.episode_store.list()

    def get_episode(self, episode_id: str) -> EpisodeRecordV2 | None:
        return self.episode_store.get(episode_id)

    def export_run(self, request: EpisodeExportRunRequest) -> EpisodeRecordV2:
        run = self.report_store.get(request.run_id)
        if run is None:
            raise KeyError(request.run_id)

        traces = self._load_artifact_items(run, "traces", TraceRecord)
        sessions = self._load_artifact_items(run, "sessions", SessionRecord)
        perception_snapshots = self._load_artifact_items(run, "perception_snapshots", PerceptionSnapshotRecord)
        world_model_transitions = self._load_artifact_items(run, "world_model_transitions", WorldModelTransitionRecord)
        executive_decisions = self._load_artifact_items(run, "executive_decisions", ExecutiveDecisionRecord)
        incidents = self._load_artifact_items(run, "incidents", IncidentTicketRecord)
        incident_timeline = self._load_artifact_items(run, "incident_timeline", IncidentTimelineRecord)

        session_ids = self._ordered_session_ids_from_run(run)
        if not sessions:
            sessions = self._load_sessions_from_memory(session_ids)
        (
            episodic_memory,
            semantic_memory,
            profile_memory,
            relationship_memory,
            procedural_memory,
        ) = self._memory_layers_for_sessions(sessions)

        episode_sessions = [
            self._session_metadata(
                session,
                redact_operator_notes=request.redact_operator_notes,
                redact_session_memory=request.redact_session_memory,
            )
            for session in sessions
        ]
        transcript = self._transcript_entries(sessions)
        tool_calls = self._tool_calls_from_traces(traces)
        input_events = self._input_events_from_traces(traces)
        commands = self._commands_from_run_steps(run)
        acknowledgements = self._acks_from_run_steps(run)
        telemetry = self._telemetry_from_run(run)
        grounding_sources = self._dedupe_grounding_sources(
            [source for trace in traces for source in trace.reasoning.grounding_sources]
        )
        final_world_model = world_model_transitions[-1].after if world_model_transitions else self.orchestrator.get_world_model()
        asset_refs = self._asset_refs(
            perception_snapshots=perception_snapshots,
            traces=traces,
            include_asset_refs=request.include_asset_refs,
        )
        annotations = self._annotation_labels(
            sessions=sessions,
            traces=traces,
            executive_decisions=executive_decisions,
            grounding_sources=grounding_sources,
        )

        episode_id = str(uuid4())
        memory_actions = self._memory_actions_for_sessions(sessions)
        memory_reviews = self._memory_reviews_for_actions(memory_actions)
        run_ids = self._run_ids_from_traces(traces) or [run.run_id]
        memory_retrievals = self._memory_retrievals_for_export(
            session_ids=session_ids,
            user_ids=[session.user_id for session in sessions if session.user_id],
            trace_ids=[trace.trace_id for trace in traces],
            run_ids=run_ids,
        )
        latest_perception = perception_snapshots[-1] if perception_snapshots else None
        scene_facts = self._scene_facts_for_export(
            final_world_model=final_world_model,
            latest_perception=latest_perception,
        )
        teacher_annotations = self._teacher_annotations_for_export(
            episode_id=episode_id,
            session_ids=session_ids,
            traces=traces,
            actions=memory_actions,
            run_ids=run_ids,
        )
        teacher_supervision_summary = self.episode_store._teacher_supervision_summary(teacher_annotations)
        benchmark_labels = self._benchmark_labels(annotations=annotations, teacher_annotations=teacher_annotations)

        episode = EpisodeRecordV2(
            episode_id=episode_id,
            source_type=EpisodeSourceType.DEMO_RUN,
            source_id=run.run_id,
            session_ids=session_ids,
            scenario_names=run.scenario_names,
            configured_dialogue_backend=run.configured_dialogue_backend,
            observed_dialogue_backends=run.observed_dialogue_backends,
            runtime_profile=run.runtime_profile,
            deployment_target=run.deployment_target,
            started_at=min((step.started_at for step in run.steps), default=run.created_at),
            completed_at=run.completed_at,
            redactions_applied=self._redactions(request.redact_operator_notes, request.redact_session_memory),
            redaction_profile=request.redaction_profile,
            notes=["source:demo_run_report_bundle"],
            sessions=episode_sessions,
            input_events=input_events,
            transcript=transcript,
            traces=traces,
            tool_calls=tool_calls,
            perception_snapshots=perception_snapshots,
            world_model_transitions=world_model_transitions,
            executive_decisions=executive_decisions,
            incidents=incidents,
            incident_timeline=incident_timeline,
            commands=commands,
            acknowledgements=acknowledgements,
            telemetry=telemetry,
            episodic_memory=episodic_memory,
            semantic_memory=semantic_memory,
            profile_memory=profile_memory,
            relationship_memory=relationship_memory,
            procedural_memory=procedural_memory,
            grounding_sources=grounding_sources,
            final_world_state=run.final_world_state,
            final_world_model=final_world_model,
            asset_refs=asset_refs,
            annotations=annotations,
            scene_facts=scene_facts,
            chosen_skills=self._chosen_skills_from_traces(traces),
            chosen_subagents=self._chosen_subagents_from_traces(traces),
            run_ids=run_ids,
            memory_actions=memory_actions,
            memory_reviews=memory_reviews,
            memory_retrievals=memory_retrievals,
            teacher_annotations=teacher_annotations,
            teacher_supervision_summary=teacher_supervision_summary,
            benchmark_labels=benchmark_labels,
            dataset_memberships=[],
            final_reply_text=self._final_reply_text(traces),
            body_action_types=self._body_action_types(commands),
            fallback_reasons=self._fallback_reasons(traces),
            user_reaction_summary="; ".join(
                summary
                for summary in (session.conversation_summary for session in sessions)
                if summary
            )
            or None,
            outcome_label=self._outcome_label(traces, sessions),
        )
        return self._save_episode_with_action_links(episode, redaction_profile=request.redaction_profile)

    def export_shift_report(self, request: EpisodeExportShiftReportRequest) -> EpisodeRecordV2:
        report = self.shift_report_store.get(request.report_id)
        if report is None:
            raise KeyError(request.report_id)

        traces = self._load_artifact_items(report, "traces", TraceRecord)
        sessions = self._load_artifact_items(report, "sessions", SessionRecord)
        perception_snapshots = self._load_artifact_items(report, "perception_snapshots", PerceptionSnapshotRecord)
        world_model_transitions = self._load_artifact_items(report, "world_model_transitions", WorldModelTransitionRecord)
        executive_decisions = self._load_artifact_items(report, "executive_decisions", ExecutiveDecisionRecord)
        incidents = self._load_artifact_items(report, "incidents", IncidentTicketRecord)
        incident_timeline = self._load_artifact_items(report, "incident_timeline", IncidentTimelineRecord)

        if not sessions:
            sessions = self._load_sessions_from_memory(report.session_ids)
        (
            episodic_memory,
            semantic_memory,
            profile_memory,
            relationship_memory,
            procedural_memory,
        ) = self._memory_layers_for_sessions(sessions)

        episode_sessions = [
            self._session_metadata(
                session,
                redact_operator_notes=request.redact_operator_notes,
                redact_session_memory=request.redact_session_memory,
            )
            for session in sessions
        ]
        transcript = self._transcript_entries(sessions)
        tool_calls = self._tool_calls_from_traces(traces)
        input_events = self._input_events_from_traces(traces)
        commands = self._commands_from_shift_steps(report)
        acknowledgements = self._acks_from_shift_steps(report)
        telemetry = self._telemetry_from_shift_steps(report)
        grounding_sources = self._dedupe_grounding_sources(
            [source for trace in traces for source in trace.reasoning.grounding_sources]
        )
        final_world_model = world_model_transitions[-1].after if world_model_transitions else self.orchestrator.get_world_model()
        asset_refs = self._asset_refs(
            perception_snapshots=perception_snapshots,
            traces=traces,
            include_asset_refs=request.include_asset_refs,
        )
        annotations = self._annotation_labels(
            sessions=sessions,
            traces=traces,
            executive_decisions=executive_decisions,
            grounding_sources=grounding_sources,
        )

        episode_id = str(uuid4())
        memory_actions = self._memory_actions_for_sessions(sessions)
        memory_reviews = self._memory_reviews_for_actions(memory_actions)
        run_ids = self._run_ids_from_traces(traces)
        memory_retrievals = self._memory_retrievals_for_export(
            session_ids=report.session_ids,
            user_ids=[session.user_id for session in sessions if session.user_id],
            trace_ids=[trace.trace_id for trace in traces],
            run_ids=run_ids,
        )
        latest_perception = perception_snapshots[-1] if perception_snapshots else None
        scene_facts = self._scene_facts_for_export(
            final_world_model=final_world_model,
            latest_perception=latest_perception,
        )
        teacher_annotations = self._teacher_annotations_for_export(
            episode_id=episode_id,
            session_ids=report.session_ids,
            traces=traces,
            actions=memory_actions,
            run_ids=run_ids,
        )
        teacher_supervision_summary = self.episode_store._teacher_supervision_summary(teacher_annotations)
        benchmark_labels = self._benchmark_labels(annotations=annotations, teacher_annotations=teacher_annotations)

        episode = EpisodeRecordV2(
            episode_id=episode_id,
            source_type=EpisodeSourceType.SHIFT_REPORT,
            source_id=report.report_id,
            session_ids=report.session_ids,
            scenario_names=[report.simulation_name],
            configured_dialogue_backend=report.configured_dialogue_backend,
            observed_dialogue_backends=report.observed_dialogue_backends,
            runtime_profile=report.runtime_profile,
            deployment_target=report.deployment_target,
            started_at=report.metrics.shift_started_at or report.created_at,
            completed_at=report.metrics.shift_ended_at or report.completed_at,
            redactions_applied=self._redactions(request.redact_operator_notes, request.redact_session_memory),
            redaction_profile=request.redaction_profile,
            notes=["source:shift_report_bundle", f"simulation:{report.simulation_name}"],
            sessions=episode_sessions,
            input_events=input_events,
            transcript=transcript,
            traces=traces,
            tool_calls=tool_calls,
            perception_snapshots=perception_snapshots,
            world_model_transitions=world_model_transitions,
            executive_decisions=executive_decisions,
            incidents=incidents,
            incident_timeline=incident_timeline,
            commands=commands,
            acknowledgements=acknowledgements,
            telemetry=telemetry,
            episodic_memory=episodic_memory,
            semantic_memory=semantic_memory,
            profile_memory=profile_memory,
            relationship_memory=relationship_memory,
            procedural_memory=procedural_memory,
            grounding_sources=grounding_sources,
            final_world_state=report.final_world_state,
            final_world_model=final_world_model,
            asset_refs=asset_refs,
            annotations=annotations,
            scene_facts=scene_facts,
            chosen_skills=self._chosen_skills_from_traces(traces),
            chosen_subagents=self._chosen_subagents_from_traces(traces),
            run_ids=run_ids,
            memory_actions=memory_actions,
            memory_reviews=memory_reviews,
            memory_retrievals=memory_retrievals,
            teacher_annotations=teacher_annotations,
            teacher_supervision_summary=teacher_supervision_summary,
            benchmark_labels=benchmark_labels,
            dataset_memberships=[],
            final_reply_text=self._final_reply_text(traces),
            body_action_types=self._body_action_types(commands),
            fallback_reasons=self._fallback_reasons(traces),
            user_reaction_summary="; ".join(
                summary
                for summary in (session.conversation_summary for session in sessions)
                if summary
            )
            or None,
            outcome_label=self._outcome_label(traces, sessions),
        )
        return self._save_episode_with_action_links(episode, redaction_profile=request.redaction_profile)

    def export_session(
        self,
        request: EpisodeExportSessionRequest,
        *,
        extra_artifacts: dict[str, Any] | None = None,
    ) -> EpisodeRecordV2:
        session = self.orchestrator.get_session(request.session_id)
        if session is None:
            raise KeyError(request.session_id)

        traces = list(reversed(self.orchestrator.list_traces(session_id=request.session_id, limit=500).items))
        perception_snapshots = list(reversed(self.orchestrator.list_perception_history(session_id=request.session_id, limit=500).items))
        world_model_transitions = list(reversed(self.orchestrator.list_world_model_transitions(session_id=request.session_id, limit=500).items))
        executive_decisions = list(reversed(self.orchestrator.list_executive_decisions(session_id=request.session_id, limit=500).items))
        incidents = self.orchestrator.list_incidents(session_id=request.session_id, limit=200).items
        incident_timeline = list(reversed(self.orchestrator.list_incident_timeline(session_id=request.session_id, limit=500).items))
        run = self._latest_run_for_session(request.session_id)

        input_events = self._input_events_from_traces(traces)
        commands = self._commands_from_traces(traces, scenario_name=session.scenario_name)
        acknowledgements = self._acks_for_session(request.session_id, traces=traces, run=run)
        telemetry = self._telemetry_for_session(request.session_id, session=session, traces=traces, run=run)
        grounding_sources = self._dedupe_grounding_sources(
            [source for trace in traces for source in trace.reasoning.grounding_sources]
        )
        asset_refs = self._asset_refs(
            perception_snapshots=perception_snapshots,
            traces=traces,
            include_asset_refs=request.include_asset_refs,
        )
        annotations = self._annotation_labels(
            sessions=[session],
            traces=traces,
            executive_decisions=executive_decisions,
            grounding_sources=grounding_sources,
        )
        final_world_model = world_model_transitions[-1].after if world_model_transitions else self.orchestrator.get_world_model()
        started_at = min(
            [session.created_at, *(turn.timestamp for turn in session.transcript), *(trace.timestamp for trace in traces)],
            default=session.created_at,
        )
        completed_at = max(
            [session.updated_at, *(trace.timestamp for trace in traces)],
            default=session.updated_at,
        )
        notes = ["source:live_session_memory"]
        if run is None:
            notes.append("ack_and_telemetry_may_be_partial_without_matching_demo_run")
        (
            episodic_memory,
            semantic_memory,
            profile_memory,
            relationship_memory,
            procedural_memory,
        ) = self._memory_layers_for_sessions([session])

        episode_id = str(uuid4())
        memory_actions = self._memory_actions_for_sessions([session])
        memory_reviews = self._memory_reviews_for_actions(memory_actions)
        run_ids = self._run_ids_from_traces(traces)
        if run is not None and run.run_id not in run_ids:
            run_ids.append(run.run_id)
        memory_retrievals = self._memory_retrievals_for_export(
            session_ids=[session.session_id],
            user_ids=[session.user_id] if session.user_id else [],
            trace_ids=[trace.trace_id for trace in traces],
            run_ids=run_ids,
        )
        latest_perception = perception_snapshots[-1] if perception_snapshots else None
        scene_facts = self._scene_facts_for_export(
            final_world_model=final_world_model,
            latest_perception=latest_perception,
        )
        teacher_annotations = self._teacher_annotations_for_export(
            episode_id=episode_id,
            session_ids=[session.session_id],
            traces=traces,
            actions=memory_actions,
            run_ids=run_ids,
        )
        teacher_supervision_summary = self.episode_store._teacher_supervision_summary(teacher_annotations)
        benchmark_labels = self._benchmark_labels(annotations=annotations, teacher_annotations=teacher_annotations)

        episode = EpisodeRecordV2(
            episode_id=episode_id,
            source_type=EpisodeSourceType.SESSION,
            source_id=session.session_id,
            session_ids=[session.session_id],
            scenario_names=[session.scenario_name] if session.scenario_name else [],
            configured_dialogue_backend=self.settings.brain_dialogue_backend,
            observed_dialogue_backends=sorted({trace.reasoning.engine for trace in traces}),
            runtime_profile=self.settings.brain_runtime_profile,
            deployment_target=self.settings.brain_deployment_target,
            started_at=started_at,
            completed_at=completed_at,
            redactions_applied=self._redactions(request.redact_operator_notes, request.redact_session_memory),
            redaction_profile=request.redaction_profile,
            notes=notes,
            sessions=[
                self._session_metadata(
                    session,
                    redact_operator_notes=request.redact_operator_notes,
                    redact_session_memory=request.redact_session_memory,
                )
            ],
            input_events=input_events,
            transcript=self._transcript_entries([session]),
            traces=traces,
            tool_calls=self._tool_calls_from_traces(traces),
            perception_snapshots=perception_snapshots,
            world_model_transitions=world_model_transitions,
            executive_decisions=executive_decisions,
            incidents=incidents,
            incident_timeline=incident_timeline,
            commands=commands,
            acknowledgements=acknowledgements,
            telemetry=telemetry,
            episodic_memory=episodic_memory,
            semantic_memory=semantic_memory,
            profile_memory=profile_memory,
            relationship_memory=relationship_memory,
            procedural_memory=procedural_memory,
            grounding_sources=grounding_sources,
            final_world_state=self.orchestrator.get_world_state(),
            final_world_model=final_world_model,
            asset_refs=asset_refs,
            annotations=annotations,
            scene_facts=scene_facts,
            chosen_skills=self._chosen_skills_from_traces(traces),
            chosen_subagents=self._chosen_subagents_from_traces(traces),
            run_ids=run_ids,
            memory_actions=memory_actions,
            memory_reviews=memory_reviews,
            memory_retrievals=memory_retrievals,
            teacher_annotations=teacher_annotations,
            teacher_supervision_summary=teacher_supervision_summary,
            benchmark_labels=benchmark_labels,
            dataset_memberships=[],
            final_reply_text=self._final_reply_text(traces),
            body_action_types=self._body_action_types(commands),
            fallback_reasons=self._fallback_reasons(traces),
            user_reaction_summary=session.conversation_summary,
            outcome_label=self._outcome_label(traces, [session]),
        )
        return self._save_episode_with_action_links(
            episode,
            redaction_profile=request.redaction_profile,
            extra_artifacts=extra_artifacts,
        )

    def _save_episode_with_action_links(
        self,
        episode: EpisodeRecordV2,
        *,
        redaction_profile: ExportRedactionProfile,
        extra_artifacts: dict[str, Any] | None = None,
    ) -> EpisodeRecordV2:
        prepared = self._prepare_episode_for_export(episode, redaction_profile=redaction_profile)
        saved = self.episode_store.save(prepared, extra_artifacts=extra_artifacts)
        return self._attach_action_bundle_index(saved)

    def _attach_action_bundle_index(self, episode: EpisodeRecordV2) -> EpisodeRecordV2:
        if episode.artifact_dir is None:
            return episode
        store = self._action_bundle_store()
        related = store.find_related_bundles(
            session_ids=episode.session_ids,
            run_ids=episode.run_ids,
            started_at=episode.started_at,
            completed_at=episode.completed_at,
        )
        if not related:
            return episode
        artifact_dir = Path(episode.artifact_dir)
        index_path = artifact_dir / "linked_action_bundles.json"
        payload = {
            "episode_id": episode.episode_id,
            "bundle_ids": [item.bundle_id for item in related],
            "items": [
                {
                    "bundle_id": item.bundle_id,
                    "manifest_path": item.artifact_files.get("manifest"),
                    "root_kind": item.root_kind.value,
                    "requested_tool_name": item.requested_tool_name,
                    "requested_action_name": item.requested_action_name,
                    "requested_workflow_id": item.requested_workflow_id,
                    "session_id": item.session_id,
                    "run_id": item.run_id,
                    "workflow_run_id": item.workflow_run_id,
                    "linked_replays": [replay.artifact_files.get("manifest") for replay in store.list_replays(bundle_id=item.bundle_id)],
                }
                for item in related
            ],
        }
        write_json_atomic(index_path, payload)
        store.attach_episode_links(episode_id=episode.episode_id, bundle_ids=[item.bundle_id for item in related])
        return self.episode_store.attach_derived_artifacts(
            episode.episode_id,
            derived_artifact_files={"action_bundle_index": str(index_path)},
            notes=[f"action_bundles_linked:{len(related)}"],
        )

    def _finalize_episode_counts(self, episode: EpisodeRecordV2) -> EpisodeRecordV2:
        episode.input_event_count = len(episode.input_events)
        episode.transcript_turn_count = len(episode.transcript)
        episode.trace_count = len(episode.traces)
        episode.tool_call_count = len(episode.tool_calls)
        episode.perception_snapshot_count = len(episode.perception_snapshots)
        episode.world_model_transition_count = len(episode.world_model_transitions)
        episode.executive_decision_count = len(episode.executive_decisions)
        episode.incident_count = len(episode.incidents)
        episode.incident_timeline_count = len(episode.incident_timeline)
        episode.command_count = len(episode.commands)
        episode.acknowledgement_count = len(episode.acknowledgements)
        episode.telemetry_count = len(episode.telemetry)
        episode.episodic_memory_count = len(episode.episodic_memory)
        episode.semantic_memory_count = len(episode.semantic_memory)
        episode.profile_memory_count = len(episode.profile_memory)
        episode.relationship_memory_count = len(episode.relationship_memory)
        episode.procedural_memory_count = len(episode.procedural_memory)
        episode.asset_ref_count = len(episode.asset_refs)
        episode.annotation_count = len(episode.annotations)
        episode.scene_fact_count = len(episode.scene_facts)
        episode.memory_action_count = len(episode.memory_actions)
        episode.memory_review_count = len(episode.memory_reviews)
        episode.memory_retrieval_count = len(episode.memory_retrievals)
        episode.teacher_annotation_count = len(episode.teacher_annotations)
        episode.benchmark_label_count = len(episode.benchmark_labels)
        episode.dataset_membership_count = len(episode.dataset_memberships)
        episode.run_count = len(episode.run_ids)
        return episode

    def _prepare_episode_for_export(
        self,
        episode: EpisodeRecordV2,
        *,
        redaction_profile: ExportRedactionProfile,
    ) -> EpisodeRecordV2:
        prepared = apply_episode_redaction_profile(episode, profile=redaction_profile)
        prepared.redaction_profile = redaction_profile
        prepared.sensitive_content_flags = collect_sensitive_content_flags(prepared)
        return self._finalize_episode_counts(prepared)

    def _ordered_session_ids_from_run(self, run: DemoRunRecord) -> list[str]:
        session_ids: list[str] = []
        seen: set[str] = set()
        for step in run.steps:
            session_id = step.event.session_id
            if not session_id or session_id in seen:
                continue
            seen.add(session_id)
            session_ids.append(session_id)
        return session_ids

    def _load_sessions_from_memory(self, session_ids: list[str]) -> list[SessionRecord]:
        sessions: list[SessionRecord] = []
        for session_id in session_ids:
            session = self.orchestrator.get_session(session_id)
            if session is not None:
                sessions.append(session)
        return sessions

    def _memory_layers_for_sessions(
        self,
        sessions: list[SessionRecord],
    ) -> tuple[
        list[EpisodicMemoryRecord],
        list[SemanticMemoryRecord],
        list[UserMemoryRecord],
        list[RelationshipMemoryRecord],
        list[ProceduralMemoryRecord],
    ]:
        session_ids = [session.session_id for session in sessions]
        user_ids = [session.user_id for session in sessions if session.user_id]

        episodic_memory: list[EpisodicMemoryRecord] = []
        for session_id in session_ids:
            episodic_memory.extend(self.orchestrator.list_episodic_memory(session_id=session_id, limit=20).items)

        semantic_memory: list[SemanticMemoryRecord] = []
        for session_id in session_ids:
            semantic_memory.extend(self.orchestrator.list_semantic_memory(session_id=session_id, limit=30).items)

        profile_memory: list[UserMemoryRecord] = []
        relationship_memory: list[RelationshipMemoryRecord] = []
        procedural_memory: list[ProceduralMemoryRecord] = []
        seen_user_ids: set[str] = set()
        for user_id in user_ids:
            if user_id in seen_user_ids:
                continue
            seen_user_ids.add(user_id)
            record = self.orchestrator.memory.get_user_memory(user_id)
            if record is not None:
                profile_memory.append(record)
            relationship_record = self.orchestrator.memory.get_relationship_memory(user_id)
            if relationship_record is not None:
                relationship_memory.append(relationship_record)
            procedural_memory.extend(self.orchestrator.memory.list_procedural_memory(user_id=user_id, limit=30).items)

        episodic_memory = self._dedupe_memory_records(episodic_memory)
        semantic_memory = self._dedupe_memory_records(semantic_memory)
        relationship_memory = self._dedupe_memory_records(relationship_memory)
        procedural_memory = self._dedupe_memory_records(procedural_memory)
        profile_memory.sort(key=lambda item: item.updated_at, reverse=True)
        return episodic_memory, semantic_memory, profile_memory, relationship_memory, procedural_memory

    def _memory_actions_for_sessions(self, sessions: list[SessionRecord]) -> list:
        items: list = []
        seen: set[str] = set()
        for session in sessions:
            for action in self.memory_layers.list_actions(session_id=session.session_id, limit=500).items:
                if action.action_id in seen:
                    continue
                seen.add(action.action_id)
                items.append(action)
        items.sort(key=lambda item: item.created_at)
        return items

    def _memory_reviews_for_actions(self, actions: list) -> list:
        items: list = []
        seen: set[str] = set()
        for action in actions:
            for review in self.memory_layers.list_reviews(memory_id=action.memory_id, limit=100).items:
                if review.review_id in seen:
                    continue
                seen.add(review.review_id)
                items.append(review)
        items.sort(key=lambda item: item.created_at)
        return items

    def _memory_retrievals_for_export(
        self,
        *,
        session_ids: list[str],
        user_ids: list[str],
        trace_ids: list[str],
        run_ids: list[str],
    ) -> list:
        items: list = []
        seen: set[str] = set()
        for session_id in session_ids:
            for retrieval in self.orchestrator.list_memory_retrievals(session_id=session_id, limit=500).items:
                if retrieval.retrieval_id in seen:
                    continue
                seen.add(retrieval.retrieval_id)
                items.append(retrieval)
        for user_id in user_ids:
            for retrieval in self.orchestrator.list_memory_retrievals(user_id=user_id, limit=500).items:
                if retrieval.retrieval_id in seen:
                    continue
                seen.add(retrieval.retrieval_id)
                items.append(retrieval)
        for trace_id in trace_ids:
            for retrieval in self.orchestrator.list_memory_retrievals(trace_id=trace_id, limit=100).items:
                if retrieval.retrieval_id in seen:
                    continue
                seen.add(retrieval.retrieval_id)
                items.append(retrieval)
        for run_id in run_ids:
            for retrieval in self.orchestrator.list_memory_retrievals(run_id=run_id, limit=100).items:
                if retrieval.retrieval_id in seen:
                    continue
                seen.add(retrieval.retrieval_id)
                items.append(retrieval)
        items.sort(key=lambda item: item.created_at)
        return items

    def _teacher_annotations_for_export(
        self,
        *,
        episode_id: str,
        session_ids: list[str] | None = None,
        traces: list[TraceRecord],
        actions: list,
        run_ids: list[str] | None = None,
    ) -> list[TeacherAnnotationRecord]:
        annotations: list[TeacherAnnotationRecord] = []
        seen: set[str] = set()
        for item in self.memory_layers.list_teacher_annotations(episode_id=episode_id, limit=200).items:
            if item.annotation_id in seen:
                continue
            seen.add(item.annotation_id)
            annotations.append(item)
        for run_id in run_ids or []:
            for item in self.memory_layers.list_teacher_annotations(run_id=run_id, limit=50).items:
                if item.annotation_id in seen:
                    continue
                seen.add(item.annotation_id)
                annotations.append(item)
        for trace in traces:
            for item in self.memory_layers.list_teacher_annotations(trace_id=trace.trace_id, limit=50).items:
                if item.annotation_id in seen:
                    continue
                seen.add(item.annotation_id)
                annotations.append(item)
        for action in actions:
            for item in self.memory_layers.list_teacher_annotations(memory_id=action.memory_id, limit=50).items:
                if item.annotation_id in seen:
                    continue
                seen.add(item.annotation_id)
                annotations.append(item)
        related_bundles = self._action_bundle_store().find_related_bundles(
            session_ids=session_ids or [],
            run_ids=run_ids or [],
            started_at=min((trace.timestamp for trace in traces), default=None),
            completed_at=max((trace.timestamp for trace in traces), default=None),
        )
        for bundle in related_bundles:
            if bundle.root_action_id:
                for item in self.memory_layers.list_teacher_annotations(action_id=bundle.root_action_id, limit=50).items:
                    if item.annotation_id in seen:
                        continue
                    seen.add(item.annotation_id)
                    annotations.append(item)
            workflow_run_id = bundle.root_workflow_run_id or bundle.workflow_run_id
            if workflow_run_id:
                for item in self.memory_layers.list_teacher_annotations(workflow_run_id=workflow_run_id, limit=50).items:
                    if item.annotation_id in seen:
                        continue
                    seen.add(item.annotation_id)
                    annotations.append(item)
        annotations.sort(key=lambda item: item.created_at)
        return annotations

    def _input_events_from_traces(self, traces: list[TraceRecord]) -> list[RobotEvent]:
        events = [trace.event.model_copy(deep=True) for trace in traces]
        events.sort(key=lambda item: item.timestamp)
        return events

    def _benchmark_labels(
        self,
        *,
        annotations: list[EpisodeAnnotationLabel],
        teacher_annotations: list[TeacherAnnotationRecord],
    ) -> list[str]:
        labels: list[str] = []
        for item in annotations:
            label_name = item.label_name.value if hasattr(item.label_name, "value") else str(item.label_name)
            if label_name not in labels:
                labels.append(label_name)
        for annotation in teacher_annotations:
            if annotation.label and annotation.label not in labels:
                labels.append(annotation.label)
            for tag in annotation.benchmark_tags:
                if tag not in labels:
                    labels.append(tag)
        return labels

    def _scene_facts_for_export(
        self,
        *,
        final_world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> list[PerceptionFactRecord]:
        if latest_perception is None and final_world_model is None:
            return []
        return self.orchestrator.knowledge_tools.recent_perception_facts(
            query=None,
            world_model=final_world_model,
            latest_perception=latest_perception,
        )

    def _chosen_skills_from_traces(self, traces: list[TraceRecord]) -> list[str]:
        skills: list[str] = []
        for trace in traces:
            skill = trace.reasoning.active_skill.skill_name if trace.reasoning.active_skill is not None else None
            if skill and skill not in skills:
                skills.append(skill)
        return skills

    def _chosen_subagents_from_traces(self, traces: list[TraceRecord]) -> list[str]:
        roles: list[str] = []
        for trace in traces:
            role = trace.reasoning.active_subagent
            if role and role not in roles:
                roles.append(role)
        return roles

    def _run_ids_from_traces(self, traces: list[TraceRecord]) -> list[str]:
        run_ids: list[str] = []
        for trace in traces:
            run_id = trace.reasoning.run_id
            if run_id and run_id not in run_ids:
                run_ids.append(run_id)
        return run_ids

    def _final_reply_text(self, traces: list[TraceRecord]) -> str | None:
        for trace in reversed(traces):
            if trace.response.reply_text:
                return trace.response.reply_text
        return None

    def _body_action_types(self, commands: list[EpisodeCommandRecord]) -> list[CommandType]:
        results: list[CommandType] = []
        for item in commands:
            if item.command.command_type not in results:
                results.append(item.command.command_type)
        return results

    def _fallback_reasons(self, traces: list[TraceRecord]) -> list[str]:
        results: list[str] = []
        for trace in traces:
            reason = trace.reasoning.fallback_reason
            if reason and reason not in results:
                results.append(reason)
        return results

    def _outcome_label(self, traces: list[TraceRecord], sessions: list[SessionRecord]) -> str | None:
        if any(trace.outcome == TraceOutcome.SAFE_FALLBACK for trace in traces):
            return "safe_fallback"
        if any(session.status == SessionStatus.ESCALATION_PENDING for session in sessions):
            return "operator_handoff"
        if any(trace.reasoning.fallback_used for trace in traces):
            return "fallback_reply"
        if traces:
            return "completed"
        return None

    def _load_artifact_items(self, source, key: str, model: type[BaseModel]) -> list[Any]:
        artifact_path = source.artifact_files.get(key)
        if not artifact_path:
            return []
        path = Path(artifact_path)
        if not path.exists():
            return []
        payload = load_json_value_or_quarantine(path, quarantine_invalid=True)
        if payload is None:
            return []
        if isinstance(payload, dict) and "items" in payload and isinstance(payload["items"], list):
            payload = payload["items"]
        if not isinstance(payload, list):
            return []
        items: list[Any] = []
        for item in payload:
            try:
                items.append(model.model_validate(item))
            except ValidationError:
                continue
        return items

    def _dedupe_memory_records(self, items: list[Any]) -> list[Any]:
        results: list[Any] = []
        seen: set[str] = set()
        for item in items:
            memory_id = (
                getattr(item, "memory_id", None)
                or getattr(item, "relationship_id", None)
                or getattr(item, "procedure_id", None)
                or getattr(item, "user_id", None)
            )
            if memory_id is None or memory_id in seen:
                continue
            seen.add(memory_id)
            results.append(item)
        return results

    def _session_metadata(
        self,
        session: SessionRecord,
        *,
        redact_operator_notes: bool,
        redact_session_memory: bool,
    ) -> EpisodeSessionMetadata:
        operator_notes = [
            note.model_copy(update={"text": "[redacted]"}) if redact_operator_notes else note.model_copy(deep=True)
            for note in session.operator_notes
        ]
        session_memory = {"redacted": "[redacted]"} if redact_session_memory and session.session_memory else dict(session.session_memory)
        return EpisodeSessionMetadata(
            session_id=session.session_id,
            user_id=session.user_id,
            channel=session.channel,
            scenario_name=session.scenario_name,
            status=session.status,
            active_incident_ticket_id=session.active_incident_ticket_id,
            incident_status=session.incident_status,
            response_mode=session.response_mode,
            created_at=session.created_at,
            updated_at=session.updated_at,
            current_topic=session.current_topic,
            conversation_summary=session.conversation_summary,
            session_memory=session_memory,
            operator_notes=operator_notes,
        )

    def _transcript_entries(self, sessions: list[SessionRecord]) -> list[EpisodeTranscriptEntry]:
        entries = [
            EpisodeTranscriptEntry(session_id=session.session_id, turn=turn.model_copy(deep=True))
            for session in sessions
            for turn in session.transcript
        ]
        entries.sort(key=lambda item: item.turn.timestamp)
        return entries

    def _tool_calls_from_traces(self, traces: list[TraceRecord]) -> list[EpisodeToolCallRecord]:
        items: list[EpisodeToolCallRecord] = []
        for trace in traces:
            for tool in trace.reasoning.tool_invocations:
                items.append(
                    EpisodeToolCallRecord(
                        session_id=trace.session_id,
                        trace_id=trace.trace_id,
                        timestamp=trace.timestamp,
                        tool=tool.model_copy(deep=True),
                    )
                )
        return items

    def _commands_from_traces(self, traces: list[TraceRecord], *, scenario_name: str | None = None) -> list[EpisodeCommandRecord]:
        items: list[EpisodeCommandRecord] = []
        for trace in traces:
            for command in trace.response.commands:
                items.append(
                    EpisodeCommandRecord(
                        session_id=trace.session_id,
                        trace_id=trace.trace_id,
                        timestamp=trace.timestamp,
                        scenario_name=scenario_name,
                        command=command.model_copy(deep=True),
                    )
                )
        return items

    def _commands_from_run_steps(self, run: DemoRunRecord) -> list[EpisodeCommandRecord]:
        items: list[EpisodeCommandRecord] = []
        for step in run.steps:
            for command in step.response.commands:
                items.append(
                    EpisodeCommandRecord(
                        session_id=step.event.session_id,
                        trace_id=step.response.trace_id,
                        timestamp=step.completed_at or step.started_at,
                        scenario_name=step.scenario_name,
                        step_index=step.step_index,
                        command=command.model_copy(deep=True),
                    )
                )
        return items

    def _acks_from_run_steps(self, run: DemoRunRecord) -> list[EpisodeAcknowledgementRecord]:
        items: list[EpisodeAcknowledgementRecord] = []
        for step in run.steps:
            for ack in step.command_acks:
                items.append(
                    EpisodeAcknowledgementRecord(
                        session_id=step.event.session_id,
                        trace_id=step.response.trace_id,
                        timestamp=ack.timestamp,
                        scenario_name=step.scenario_name,
                        step_index=step.step_index,
                        ack=ack.model_copy(deep=True),
                    )
                )
        return items

    def _telemetry_from_run(self, run: DemoRunRecord) -> list[EpisodeTelemetryRecord]:
        items: list[EpisodeTelemetryRecord] = []
        for step in run.steps:
            items.append(
                EpisodeTelemetryRecord(
                    session_id=step.event.session_id,
                    trace_id=step.response.trace_id,
                    timestamp=step.completed_at or step.started_at,
                    source="demo_run_step",
                    note=f"{step.scenario_name}:{step.step_index}",
                    telemetry=step.telemetry.model_copy(deep=True),
                )
            )
        return items

    def _commands_from_shift_steps(self, report: ShiftReportRecord) -> list[EpisodeCommandRecord]:
        items: list[EpisodeCommandRecord] = []
        for index, step in enumerate(report.steps, start=1):
            if step.response is None:
                continue
            for command in step.response.commands:
                items.append(
                    EpisodeCommandRecord(
                        session_id=step.session_id,
                        trace_id=step.trace_id,
                        timestamp=step.completed_at or step.scheduled_at,
                        scenario_name=report.simulation_name,
                        step_index=index,
                        command=command.model_copy(deep=True),
                    )
                )
        return items

    def _acks_from_shift_steps(self, report: ShiftReportRecord) -> list[EpisodeAcknowledgementRecord]:
        items: list[EpisodeAcknowledgementRecord] = []
        for index, step in enumerate(report.steps, start=1):
            for ack in step.command_acks:
                items.append(
                    EpisodeAcknowledgementRecord(
                        session_id=step.session_id,
                        trace_id=step.trace_id,
                        timestamp=ack.timestamp,
                        scenario_name=report.simulation_name,
                        step_index=index,
                        ack=ack.model_copy(deep=True),
                    )
                )
        return items

    def _telemetry_from_shift_steps(self, report: ShiftReportRecord) -> list[EpisodeTelemetryRecord]:
        items: list[EpisodeTelemetryRecord] = []
        for step in report.steps:
            if step.telemetry is None:
                continue
            items.append(
                EpisodeTelemetryRecord(
                    session_id=step.session_id,
                    trace_id=step.trace_id,
                    timestamp=step.completed_at or step.scheduled_at,
                    source="shift_report_step",
                    note=step.label,
                    telemetry=step.telemetry.model_copy(deep=True),
                )
            )
        return items

    def _acks_for_session(
        self,
        session_id: str,
        *,
        traces: list[TraceRecord],
        run: DemoRunRecord | None,
    ) -> list[EpisodeAcknowledgementRecord]:
        if run is not None:
            return [
                record
                for record in self._acks_from_run_steps(run)
                if record.session_id == session_id
            ]

        command_ids = {command.command_id for trace in traces for command in trace.response.commands}
        history = self._command_history()
        return [
            EpisodeAcknowledgementRecord(
                session_id=session_id,
                trace_id=self._trace_id_for_command_id(traces, entry.command.command_id),
                timestamp=entry.ack.timestamp,
                ack=entry.ack.model_copy(deep=True),
            )
            for entry in history.items
            if entry.command.command_id in command_ids
        ]

    def _telemetry_for_session(
        self,
        session_id: str,
        *,
        session: SessionRecord,
        traces: list[TraceRecord],
        run: DemoRunRecord | None,
    ) -> list[EpisodeTelemetryRecord]:
        if run is not None:
            return [
                record
                for record in self._telemetry_from_run(run)
                if record.session_id == session_id
            ]

        started_at = min([session.created_at, *(trace.timestamp for trace in traces)], default=session.created_at)
        completed_at = max([session.updated_at, *(trace.timestamp for trace in traces)], default=session.updated_at)
        return [
            EpisodeTelemetryRecord(
                session_id=session_id,
                timestamp=entry.timestamp,
                source=entry.source,
                note=entry.note,
                telemetry=entry.telemetry.model_copy(deep=True),
            )
            for entry in self._telemetry_log().items
            if started_at <= entry.timestamp <= completed_at
        ]

    def _command_history(self) -> CommandHistoryResponse:
        if self.edge_gateway is None:
            return CommandHistoryResponse()
        return self.edge_gateway.get_command_history()

    def _telemetry_log(self) -> TelemetryLogResponse:
        if self.edge_gateway is None:
            return TelemetryLogResponse()
        return self.edge_gateway.get_telemetry_log()

    def _trace_id_for_command_id(self, traces: list[TraceRecord], command_id: str) -> str | None:
        for trace in traces:
            if any(command.command_id == command_id for command in trace.response.commands):
                return trace.trace_id
        return None

    def _latest_run_for_session(self, session_id: str) -> DemoRunRecord | None:
        for run in self.report_store.list().items:
            if any(step.event.session_id == session_id for step in run.steps):
                return run
        return None

    def _dedupe_grounding_sources(self, items: list[GroundingSourceRecord]) -> list[GroundingSourceRecord]:
        seen: set[tuple[str, str, str | None, str | None]] = set()
        results: list[GroundingSourceRecord] = []
        for item in items:
            key = (item.source_type.value, item.label, item.source_ref, item.detail)
            if key in seen:
                continue
            seen.add(key)
            results.append(item.model_copy(deep=True))
        return results

    def _asset_refs(
        self,
        *,
        perception_snapshots: list[PerceptionSnapshotRecord],
        traces: list[TraceRecord],
        include_asset_refs: bool,
    ) -> list[EpisodeAssetReference]:
        if not include_asset_refs:
            return []

        refs: list[EpisodeAssetReference] = []
        seen: set[tuple[str | None, str | None, str | None]] = set()
        for snapshot in perception_snapshots:
            source_frame = snapshot.source_frame
            path = source_frame.fixture_path or source_frame.file_name
            key = (snapshot.snapshot_id, path, source_frame.frame_id)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                EpisodeAssetReference(
                    asset_kind=self._classify_asset_kind(source_frame.source_kind, source_frame.file_name, source_frame.clip_duration_ms),
                    session_id=snapshot.session_id,
                    snapshot_id=snapshot.snapshot_id,
                    source_kind=source_frame.source_kind,
                    path=path,
                    label=source_frame.source_label or source_frame.file_name,
                    mime_type=source_frame.mime_type,
                    captured_at=source_frame.captured_at,
                    received_at=source_frame.received_at,
                    metadata={
                        "frame_id": source_frame.frame_id,
                        "clip_offset_ms": source_frame.clip_offset_ms,
                        "clip_duration_ms": source_frame.clip_duration_ms,
                        "width_px": source_frame.width_px,
                        "height_px": source_frame.height_px,
                    },
                )
            )

        for trace in traces:
            payload = trace.event.payload
            for key in ("audio_asset_path", "audio_path", "audio_file"):
                path = payload.get(key)
                if not isinstance(path, str) or not path:
                    continue
                ref_key = (trace.trace_id, path, key)
                if ref_key in seen:
                    continue
                seen.add(ref_key)
                refs.append(
                    EpisodeAssetReference(
                        asset_kind=EpisodeAssetKind.AUDIO_CLIP,
                        session_id=trace.session_id,
                        trace_id=trace.trace_id,
                        source_kind="voice_input",
                        path=path,
                        label=Path(path).name,
                        metadata={"metadata_key": key},
                    )
                )
        return refs

    def _classify_asset_kind(
        self,
        source_kind: str,
        file_name: str | None,
        clip_duration_ms: float | None,
    ) -> EpisodeAssetKind:
        normalized = source_kind.lower().strip()
        if clip_duration_ms is not None or "video" in normalized or normalized.endswith("_clip"):
            return EpisodeAssetKind.VIDEO_CLIP
        if normalized in {"browser_snapshot", "image_fixture", "multimodal_llm", "manual_annotations", "stub"}:
            return EpisodeAssetKind.IMAGE_FRAME
        if file_name and Path(file_name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return EpisodeAssetKind.IMAGE_FRAME
        return EpisodeAssetKind.OTHER

    def _annotation_labels(
        self,
        *,
        sessions: list[SessionRecord],
        traces: list[TraceRecord],
        executive_decisions: list[ExecutiveDecisionRecord],
        grounding_sources: list[GroundingSourceRecord],
    ) -> list[EpisodeAnnotationLabel]:
        reply_text = " ".join(trace.response.reply_text or "" for trace in traces).lower()
        decision_types = {decision.decision_type for decision in executive_decisions}
        session_statuses = {session.status for session in sessions}
        evidence_trace_ids = [trace.trace_id for trace in traces]
        grounding_evidence = [trace.trace_id for trace in traces if trace.reasoning.grounding_sources]
        limited_awareness = any(source.source_type == GroundingSourceType.LIMITED_AWARENESS for source in grounding_sources)
        structured_grounding = any(
            source.source_type in {
                GroundingSourceType.TOOL,
                GroundingSourceType.VENUE,
                GroundingSourceType.PERCEPTION,
                GroundingSourceType.PERCEPTION_FACT,
                GroundingSourceType.WORLD_MODEL,
                GroundingSourceType.USER_MEMORY,
                GroundingSourceType.PROFILE_MEMORY,
                GroundingSourceType.EPISODIC_MEMORY,
                GroundingSourceType.SEMANTIC_MEMORY,
            }
            for source in grounding_sources
        )
        safe_fallback = any(trace.outcome in {TraceOutcome.SAFE_FALLBACK, TraceOutcome.FALLBACK_REPLY} for trace in traces)
        greeted = (
            ExecutiveDecisionType.AUTO_GREET in decision_types
            or "welcome" in reply_text
            or "hello" in reply_text
            or "hi." in reply_text
        )
        escalated = ExecutiveDecisionType.ESCALATE_TO_HUMAN in decision_types or SessionStatus.ESCALATION_PENDING in session_statuses

        return [
            EpisodeAnnotationLabel(
                label_name=EpisodeLabelName.SUCCESSFUL_GROUNDING,
                suggested_value="pass" if structured_grounding and not limited_awareness else "review",
                confidence=0.85 if structured_grounding else 0.45,
                evidence_refs=grounding_evidence or evidence_trace_ids,
                note="Structured venue, perception, tool, or memory grounding was available.",
            ),
            EpisodeAnnotationLabel(
                label_name=EpisodeLabelName.FAILED_GROUNDING,
                suggested_value="pass" if limited_awareness else "not_applicable",
                confidence=0.8 if limited_awareness else 0.6,
                evidence_refs=grounding_evidence or evidence_trace_ids,
                note="Use this label when the system correctly admitted insufficient perception or venue knowledge.",
            ),
            EpisodeAnnotationLabel(
                label_name=EpisodeLabelName.GREETING_QUALITY,
                suggested_value="pass" if greeted else "not_applicable",
                confidence=0.75 if greeted else 0.7,
                evidence_refs=evidence_trace_ids,
                note="Auto-greet or explicit greeting language was observed.",
            ),
            EpisodeAnnotationLabel(
                label_name=EpisodeLabelName.ESCALATION_CORRECTNESS,
                suggested_value="pass" if escalated else "not_applicable",
                confidence=0.8 if escalated else 0.7,
                evidence_refs=[decision.decision_id for decision in executive_decisions] or evidence_trace_ids,
                note="Human handoff was explicitly requested by policy or reflected in session status.",
            ),
            EpisodeAnnotationLabel(
                label_name=EpisodeLabelName.SAFE_FALLBACK_CORRECTNESS,
                suggested_value="pass" if safe_fallback else "not_applicable",
                confidence=0.85 if safe_fallback else 0.7,
                evidence_refs=evidence_trace_ids,
                note="A safe fallback or honest degraded reply was visible in trace outcomes.",
            ),
        ]

    def _redactions(self, redact_operator_notes: bool, redact_session_memory: bool) -> list[str]:
        redactions: list[str] = []
        if redact_operator_notes:
            redactions.append("operator_notes")
        if redact_session_memory:
            redactions.append("session_memory")
        return redactions


def build_exporter(
    *,
    settings: Settings | None = None,
    orchestrator: BrainOrchestrator | None = None,
    report_store: DemoReportStore | None = None,
    shift_report_store: ShiftReportStore | None = None,
    episode_store: EpisodeStore | None = None,
    edge_gateway: EdgeGateway | None = None,
) -> BlinkEpisodeExporter:
    resolved_settings = settings or get_settings()
    return BlinkEpisodeExporter(
        settings=resolved_settings,
        orchestrator=orchestrator or BrainOrchestrator(settings=resolved_settings, store_path=resolved_settings.brain_store_path),
        report_store=report_store or DemoReportStore(resolved_settings.demo_report_dir),
        shift_report_store=shift_report_store or ShiftReportStore(resolved_settings.shift_report_dir),
        episode_store=episode_store or EpisodeStore(resolved_settings.episode_export_dir),
        edge_gateway=edge_gateway,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or inspect Blink-AI multimodal episodes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--output-dir", default=None)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("episode_id")
    show_parser.add_argument("--output-dir", default=None)

    export_run_parser = subparsers.add_parser("export-run")
    export_run_parser.add_argument("run_id")
    export_run_parser.add_argument("--output-dir", default=None)
    export_run_parser.add_argument("--redact-operator-notes", action="store_true")
    export_run_parser.add_argument("--redact-session-memory", action="store_true")

    export_shift_parser = subparsers.add_parser("export-shift-report")
    export_shift_parser.add_argument("report_id")
    export_shift_parser.add_argument("--output-dir", default=None)
    export_shift_parser.add_argument("--redact-operator-notes", action="store_true")
    export_shift_parser.add_argument("--redact-session-memory", action="store_true")

    export_session_parser = subparsers.add_parser("export-session")
    export_session_parser.add_argument("session_id")
    export_session_parser.add_argument("--output-dir", default=None)
    export_session_parser.add_argument("--redact-operator-notes", action="store_true")
    export_session_parser.add_argument("--redact-session-memory", action="store_true")

    args = parser.parse_args()
    settings = get_settings()
    episode_store = EpisodeStore(args.output_dir or settings.episode_export_dir)
    exporter = build_exporter(settings=settings, episode_store=episode_store)

    if args.command == "list":
        print(json.dumps(exporter.list_episodes().model_dump(mode="json"), indent=2))
        return

    if args.command == "show":
        episode = exporter.get_episode(args.episode_id)
        if episode is None:
            raise SystemExit(f"episode_not_found:{args.episode_id}")
        print(json.dumps(episode.model_dump(mode="json"), indent=2))
        return

    if args.command == "export-run":
        episode = exporter.export_run(
            EpisodeExportRunRequest(
                run_id=args.run_id,
                redact_operator_notes=args.redact_operator_notes,
                redact_session_memory=args.redact_session_memory,
            )
        )
        print(json.dumps(episode.model_dump(mode="json"), indent=2))
        return

    if args.command == "export-shift-report":
        episode = exporter.export_shift_report(
            EpisodeExportShiftReportRequest(
                report_id=args.report_id,
                redact_operator_notes=args.redact_operator_notes,
                redact_session_memory=args.redact_session_memory,
            )
        )
        print(json.dumps(episode.model_dump(mode="json"), indent=2))
        return

    if args.command == "export-session":
        episode = exporter.export_session(
            EpisodeExportSessionRequest(
                session_id=args.session_id,
                redact_operator_notes=args.redact_operator_notes,
                redact_session_memory=args.redact_session_memory,
            )
        )
        print(json.dumps(episode.model_dump(mode="json"), indent=2))
        return


if __name__ == "__main__":
    main()
