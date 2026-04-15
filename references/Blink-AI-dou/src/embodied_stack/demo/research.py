from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter, defaultdict
from pathlib import Path

from embodied_stack.action_plane.bundles import ActionBundleStore
from embodied_stack.brain.memory import apply_episode_redaction_profile
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.episodes import BlinkEpisodeExporter, build_exporter
from embodied_stack.persistence import load_json_value_or_quarantine, quarantine_invalid_file, write_json_atomic
from embodied_stack.shared.contracts import (
    CommandType,
    DatasetEpisodeEntry,
    DatasetExportRequest,
    DatasetManifestListResponse,
    DatasetManifestV1,
    DatasetQualityMetric,
    DatasetSplitName,
    DatasetSplitRecord,
    EpisodeDatasetMembership,
    EpisodeRecordV2,
    ExportRedactionProfile,
    GroundingSourceType,
    PlannerInputRecord,
    PlannerOutputRecord,
    ResearchBundleManifest,
    ResearchExportFormat,
    RedactionState,
)

STRICT_REPLAY_POLICY_VERSION = "blink_strict_replay/v2"
STRICT_REPLAY_ACCEPTABLE_FIELDS = [
    "timestamps",
    "uuids",
    "artifact_paths",
    "note_ordering",
    "latency_only",
]


def _planner_meta_from_notes(notes: list[str]) -> tuple[str, str]:
    planner_id = "agent_os_current"
    planner_profile = "default"
    for note in notes:
        if note.startswith("planner_id:"):
            planner_id = note.split(":", 1)[1] or planner_id
        elif note.startswith("planner_profile:"):
            planner_profile = note.split(":", 1)[1] or planner_profile
    return planner_id, planner_profile


def source_world_model_for_trace(episode: EpisodeRecordV2, trace) -> object | None:
    matching = next((item for item in episode.world_model_transitions if item.trace_id == trace.trace_id), None)
    if matching is not None:
        return matching.before
    session_matches = [
        item
        for item in episode.world_model_transitions
        if item.session_id == trace.session_id and item.created_at <= trace.timestamp
    ]
    if session_matches:
        session_matches.sort(key=lambda item: item.created_at)
        return session_matches[-1].after
    return None


def source_perception_for_trace(episode: EpisodeRecordV2, trace) -> object | None:
    session_matches = [
        item
        for item in episode.perception_snapshots
        if item.created_at <= trace.timestamp and (item.session_id == trace.session_id or item.session_id is None)
    ]
    if session_matches:
        session_matches.sort(key=lambda item: item.created_at)
        return session_matches[-1]
    return None


def _tool_chain_for_trace(trace) -> list[str]:
    if trace.reasoning.tool_chain:
        return list(trace.reasoning.tool_chain)
    return [item.tool_name for item in trace.reasoning.typed_tool_calls]


def _normalized_scene_facts_for_trace(episode: EpisodeRecordV2 | None, trace) -> list[dict[str, object]]:
    scene_fact_map = {item.fact_id: item for item in episode.scene_facts} if episode is not None else {}
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    candidates = list(trace.reasoning.grounded_scene_references) or list(trace.reasoning.grounding_sources)
    for item in candidates:
        key = item.fact_id or item.source_ref or item.label
        if not key or key in seen:
            continue
        seen.add(key)
        fact = scene_fact_map.get(item.fact_id or "")
        if fact is not None:
            normalized.append(
                {
                    "fact_id": fact.fact_id,
                    "label": fact.label,
                    "fact_type": fact.fact_type,
                    "detail": fact.detail,
                    "claim_kind": fact.claim_kind.value if fact.claim_kind is not None else None,
                    "freshness": fact.freshness.value if fact.freshness is not None else None,
                    "confidence": fact.confidence,
                    "grounding_eligible": fact.grounding_eligible,
                    "source_ref": item.source_ref,
                }
            )
            continue
        normalized.append(
            {
                "fact_id": item.fact_id,
                "label": item.label,
                "detail": item.detail,
                "claim_kind": item.claim_kind.value if item.claim_kind is not None else None,
                "freshness": item.freshness.value if item.freshness is not None else None,
                "confidence": item.confidence,
                "source_ref": item.source_ref,
            }
        )
    return normalized


def _memory_candidates_for_trace(episode: EpisodeRecordV2 | None, trace) -> list[dict[str, object]]:
    if episode is None:
        return []
    matched = [
        item
        for item in episode.memory_retrievals
        if item.trace_id == trace.trace_id or (trace.reasoning.run_id and item.run_id == trace.reasoning.run_id)
    ]
    candidates: list[dict[str, object]] = []
    for retrieval in matched:
        for index, candidate in enumerate(retrieval.selected_candidates, start=1):
            candidates.append(
                {
                    "retrieval_id": retrieval.retrieval_id,
                    "backend": retrieval.backend.value,
                    "memory_id": candidate.memory_id,
                    "layer": candidate.layer.value if candidate.layer is not None else None,
                    "summary": candidate.summary,
                    "ranking_reason": candidate.reason,
                    "score": candidate.score,
                    "selected": True,
                    "rank": index,
                }
            )
        for index, candidate in enumerate(retrieval.rejected_candidates, start=1):
            candidates.append(
                {
                    "retrieval_id": retrieval.retrieval_id,
                    "backend": retrieval.backend.value,
                    "memory_id": candidate.memory_id,
                    "layer": candidate.layer.value if candidate.layer is not None else None,
                    "summary": candidate.summary,
                    "ranking_reason": candidate.reason,
                    "score": candidate.score,
                    "selected": False,
                    "rank": index,
                }
            )
    return candidates


def _planner_input_envelope(trace, episode: EpisodeRecordV2) -> dict[str, object]:
    return {
        "event_type": trace.event.event_type,
        "active_playbook": trace.reasoning.active_playbook,
        "active_subagent": trace.reasoning.active_subagent,
        "tool_chain": _tool_chain_for_trace(trace),
        "memory_update_keys": sorted(trace.reasoning.memory_updates),
        "grounding_source_types": [item.source_type.value for item in trace.reasoning.grounding_sources],
        "scene_fact_count": len(_normalized_scene_facts_for_trace(episode, trace)),
        "retrieval_count": len(_memory_candidates_for_trace(episode, trace)),
    }


def _embodiment_output_envelope(commands: list[object]) -> dict[str, object]:
    semantic_actions: list[dict[str, object]] = []
    for command in commands:
        semantic_name = (
            command.payload.get("canonical_name")
            or command.payload.get("expression")
            or command.payload.get("gesture")
            or command.payload.get("animation")
            or command.payload.get("gaze_target")
            or command.payload.get("mode")
        )
        semantic_actions.append(
            {
                "command_type": command.command_type.value,
                "semantic_name": semantic_name,
                "payload": dict(command.payload),
            }
        )
    return {
        "command_types": [command.command_type.value for command in commands],
        "semantic_actions": semantic_actions,
        "safe_idle_compatible": any(command.command_type == CommandType.SAFE_IDLE for command in commands) or not commands,
    }


def environment_fingerprint_for_settings(
    settings: Settings,
    *,
    planner_id: str | None = None,
    planner_profile: str | None = None,
    redaction_profile: ExportRedactionProfile | None = None,
) -> dict[str, object]:
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "planner_id": planner_id or settings.blink_planner_id,
        "planner_profile": planner_profile or settings.blink_planner_profile,
        "runtime_mode": settings.blink_runtime_mode.value if hasattr(settings.blink_runtime_mode, "value") else str(settings.blink_runtime_mode),
        "body_driver": settings.blink_body_driver.value if hasattr(settings.blink_body_driver, "value") else str(settings.blink_body_driver),
        "strict_replay_policy_version": STRICT_REPLAY_POLICY_VERSION,
        "redaction_profile": redaction_profile.value if redaction_profile is not None else None,
    }


def strict_replay_policy_notes() -> list[str]:
    return [
        "strict replay compares normalized scene facts, tool selection, retrieval winners, fallback classification, and embodiment semantics",
        "timestamps, uuids, artifact paths, note ordering, and latency-only drift are acceptable metadata differences",
        "reply paraphrase drift without tool or command changes is review-required in observational mode and failing in strict mode",
    ]


def planner_input_from_trace(episode: EpisodeRecordV2, trace, *, replay_mode=None) -> PlannerInputRecord:
    session_snapshot = next((item for item in episode.sessions if item.session_id == trace.session_id), None)
    return PlannerInputRecord(
        source_trace_id=trace.trace_id,
        session_id=trace.session_id,
        user_id=trace.user_id,
        input_text=str(trace.event.payload.get("text")) if isinstance(trace.event.payload, dict) and trace.event.payload.get("text") else None,
        event=trace.event,
        session_snapshot=session_snapshot,
        world_model=source_world_model_for_trace(episode, trace),
        latest_perception=source_perception_for_trace(episode, trace),
        tool_invocations=list(trace.reasoning.tool_invocations),
        memory_updates=dict(trace.reasoning.memory_updates),
        strict_replay_policy_version=STRICT_REPLAY_POLICY_VERSION,
        normalized_scene_facts=_normalized_scene_facts_for_trace(episode, trace),
        selected_tool_chain=_tool_chain_for_trace(trace),
        retrieved_memory_candidates=_memory_candidates_for_trace(episode, trace),
        planner_input_envelope=_planner_input_envelope(trace, episode),
        replay_mode=replay_mode,
    )


def planner_output_from_trace(trace, *, episode: EpisodeRecordV2 | None = None) -> PlannerOutputRecord:
    planner_id, planner_profile = _planner_meta_from_notes(trace.reasoning.notes)
    normalized_scene_facts = _normalized_scene_facts_for_trace(episode, trace)
    tool_chain = _tool_chain_for_trace(trace)
    return PlannerOutputRecord(
        planner_id=planner_id,
        planner_profile=planner_profile,
        engine_name=trace.reasoning.engine,
        reply_text=trace.response.reply_text,
        intent=trace.reasoning.intent,
        active_skill=trace.reasoning.active_skill.skill_name if trace.reasoning.active_skill is not None else None,
        active_playbook=trace.reasoning.active_playbook,
        active_playbook_variant=trace.reasoning.active_playbook_variant,
        active_subagent=trace.reasoning.active_subagent,
        fallback_used=trace.reasoning.fallback_used,
        fallback_reason=trace.reasoning.fallback_reason,
        fallback_classification=(
            trace.reasoning.fallback_classification.value
            if trace.reasoning.fallback_classification is not None
            else None
        ),
        strict_replay_policy_version=STRICT_REPLAY_POLICY_VERSION,
        typed_tool_calls=list(trace.reasoning.typed_tool_calls),
        selected_tool_chain=tool_chain,
        retrieved_memory_candidates=_memory_candidates_for_trace(episode, trace),
        normalized_scene_facts_used=normalized_scene_facts,
        planner_output_envelope={
            "intent": trace.reasoning.intent,
            "active_playbook": trace.reasoning.active_playbook,
            "active_playbook_variant": trace.reasoning.active_playbook_variant,
            "active_subagent": trace.reasoning.active_subagent,
            "tool_chain": tool_chain,
            "fallback_classification": (
                trace.reasoning.fallback_classification.value
                if trace.reasoning.fallback_classification is not None
                else None
            ),
            "grounded_scene_fact_ids": [item.get("fact_id") for item in normalized_scene_facts if item.get("fact_id")],
        },
        embodiment_output_envelope=_embodiment_output_envelope(list(trace.response.commands)),
        commands=list(trace.response.commands),
        run_id=trace.reasoning.run_id,
        notes=list(trace.reasoning.notes),
    )


def leakage_group_key_for_episode(episode: EpisodeRecordV2) -> str:
    session_lineage = "|".join(sorted(episode.session_ids))
    user_ids = sorted(
        {
            value
            for value in [*(session.user_id for session in episode.sessions), *(trace.user_id for trace in episode.traces)]
            if value
        }
    )
    replay_lineage = "|".join(sorted(episode.run_ids))
    teacher_lineage = "|".join(
        sorted(
            {
                value
                for annotation in episode.teacher_annotations
                for value in (
                    annotation.memory_id,
                    annotation.trace_id,
                    annotation.run_id,
                    annotation.scope_id,
                    (
                        annotation.memory_feedback.merge_into_memory_id
                        if annotation.memory_feedback is not None
                        else None
                    ),
                )
                if value
            }
        )
    )
    action_index = _action_bundle_index_payload(episode)
    action_bundle_lineage = "|".join(
        sorted(
            {
                str(item.get("bundle_id"))
                for item in action_index.get("items", [])
                if isinstance(item, dict) and item.get("bundle_id")
            }
        )
    )
    action_replay_lineage = "|".join(
        sorted(
            {
                str(path)
                for item in action_index.get("items", [])
                if isinstance(item, dict)
                for path in item.get("linked_replays", [])
                if path
            }
        )
    )
    workflow_lineage = "|".join(
        sorted(
            {
                str(item.get("workflow_run_id"))
                for item in action_index.get("items", [])
                if isinstance(item, dict) and item.get("workflow_run_id")
            }
        )
    )
    return (
        f"sessions:{session_lineage};"
        f"users:{'|'.join(user_ids)};"
        f"runs:{replay_lineage};"
        f"teacher:{teacher_lineage};"
        f"action_bundles:{action_bundle_lineage};"
        f"action_replays:{action_replay_lineage};"
        f"workflow_runs:{workflow_lineage}"
    )


def _action_bundle_index_payload(episode: EpisodeRecordV2) -> dict[str, object]:
    path = episode.derived_artifact_files.get("action_bundle_index")
    if not path:
        return {}
    payload = load_json_value_or_quarantine(Path(path))
    return payload if isinstance(payload, dict) else {}


def deterministic_split_for_episode(episode: EpisodeRecordV2) -> DatasetSplitRecord:
    leakage_group_key = leakage_group_key_for_episode(episode)
    group_key = f"{episode.source_type.value}:{episode.source_id}:{leakage_group_key}"
    digest = hashlib.sha1(leakage_group_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 80:
        split_name = DatasetSplitName.TRAIN
    elif bucket < 90:
        split_name = DatasetSplitName.VALIDATION
    else:
        split_name = DatasetSplitName.TEST
    return DatasetSplitRecord(
        split_name=split_name,
        group_key=group_key,
        leakage_group_key=leakage_group_key,
        source_episode_id=episode.episode_id,
        source_ref=f"{episode.source_type.value}:{episode.source_id}",
        note="Stable hash-based grouping keeps related sessions, replay lineage, and teacher-linked corrections in the same split.",
    )


class DatasetManifestStore:
    MANIFEST_FILE = "manifest.json"

    def __init__(self, export_dir: str | Path) -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def save(self, manifest: DatasetManifestV1) -> DatasetManifestV1:
        dataset_dir = self.export_dir / manifest.dataset_id
        dataset_dir.mkdir(parents=True, exist_ok=True)
        artifact_files = {
            "manifest": str(dataset_dir / self.MANIFEST_FILE),
            "entries": str(dataset_dir / "entries.json"),
            "quality_metrics": str(dataset_dir / "quality_metrics.json"),
        }
        manifest.artifact_dir = str(dataset_dir)
        manifest.artifact_files = artifact_files
        manifest.episode_count = len(manifest.entries)
        self._write_json(Path(artifact_files["entries"]), manifest.entries)
        self._write_json(Path(artifact_files["quality_metrics"]), manifest.quality_metrics)
        self._write_json(Path(artifact_files["manifest"]), manifest)
        return manifest.model_copy(deep=True)

    def get(self, dataset_id: str) -> DatasetManifestV1 | None:
        path = self.export_dir / dataset_id / self.MANIFEST_FILE
        if not path.exists():
            return None
        payload = load_json_value_or_quarantine(path, quarantine_invalid=True)
        if payload is None:
            return None
        try:
            return DatasetManifestV1.model_validate(payload)
        except Exception:
            quarantine_invalid_file(path)
            return None

    def list(self) -> DatasetManifestListResponse:
        items: list[DatasetManifestV1] = []
        for manifest_path in sorted(self.export_dir.glob(f"*/{self.MANIFEST_FILE}")):
            payload = load_json_value_or_quarantine(manifest_path, quarantine_invalid=True)
            if payload is None:
                continue
            try:
                items.append(DatasetManifestV1.model_validate(payload))
            except Exception:
                quarantine_invalid_file(manifest_path)
                continue
        items.sort(key=lambda item: item.exported_at, reverse=True)
        return DatasetManifestListResponse(items=items)

    def _write_json(self, path: Path, payload: object) -> None:
        if hasattr(payload, "model_dump"):
            serialized = payload.model_dump(mode="json")  # type: ignore[union-attr]
        elif isinstance(payload, list):
            serialized = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in payload
            ]
        else:
            serialized = payload
        write_json_atomic(path, serialized)


class ResearchBundleExporter:
    def __init__(self, *, settings: Settings, episode_exporter: BlinkEpisodeExporter) -> None:
        self.settings = settings
        self.episode_exporter = episode_exporter

    @classmethod
    def from_settings(cls, *, settings: Settings, episode_exporter: BlinkEpisodeExporter) -> "ResearchBundleExporter":
        return cls(settings=settings, episode_exporter=episode_exporter)

    def export_episode(
        self,
        episode_id: str,
        *,
        formats: list[ResearchExportFormat] | None = None,
        redaction_profile: ExportRedactionProfile = ExportRedactionProfile.RESEARCH_REDACTED,
    ) -> ResearchBundleManifest:
        source_episode = self.episode_exporter.get_episode(episode_id)
        if source_episode is None:
            raise KeyError(episode_id)
        source_episode = self._ensure_action_bundle_index(source_episode)

        episode = apply_episode_redaction_profile(source_episode, profile=redaction_profile)
        requested_formats = formats or [ResearchExportFormat.NATIVE]
        split = deterministic_split_for_episode(source_episode)
        bundle_dir = (
            Path(source_episode.artifact_dir or Path(self.settings.episode_export_dir) / source_episode.episode_id)
            / "research_bundle"
            / redaction_profile.value
        )
        bundle_dir.mkdir(parents=True, exist_ok=True)

        planner_inputs = [planner_input_from_trace(episode, trace) for trace in episode.traces]
        planner_outputs = [planner_output_from_trace(trace, episode=episode) for trace in episode.traces]
        observations = self._observations(episode)
        raw_inputs = list(episode.input_events)
        playbook_runtime = self._playbook_runtime(episode)
        memory_reads = [
            item
            for item in episode.grounding_sources
            if item.source_type
            in {
                GroundingSourceType.USER_MEMORY,
                GroundingSourceType.PROFILE_MEMORY,
                GroundingSourceType.EPISODIC_MEMORY,
                GroundingSourceType.SEMANTIC_MEMORY,
            }
        ]
        body_actions = [
            item
            for item in episode.commands
            if item.command.command_type
            in {
                CommandType.SET_EXPRESSION,
                CommandType.SET_GAZE,
                CommandType.PERFORM_GESTURE,
                CommandType.PERFORM_ANIMATION,
                CommandType.SAFE_IDLE,
            }
        ]
        human_feedback = {
            "annotations": [item.model_dump(mode="json") for item in episode.annotations],
            "teacher_annotations": [item.model_dump(mode="json") for item in episode.teacher_annotations],
            "teacher_supervision_summary": episode.teacher_supervision_summary.model_dump(mode="json"),
        }
        labels = {
            "outcome_label": episode.outcome_label,
            "annotations": [item.model_dump(mode="json") for item in episode.annotations],
            "benchmark_labels": list(episode.benchmark_labels),
            "fallback_reasons": list(episode.fallback_reasons),
        }
        final_reply = {
            "final_reply_text": episode.final_reply_text,
            "body_action_types": [
                value.value if hasattr(value, "value") else str(value) for value in episode.body_action_types
            ],
            "fallback_reasons": list(episode.fallback_reasons),
        }
        quality_metrics = self._quality_metrics(episode)
        action_index = _action_bundle_index_payload(source_episode)
        linked_action_bundles = [
            str(item.get("manifest_path"))
            for item in action_index.get("items", [])
            if isinstance(item, dict) and item.get("manifest_path")
        ]
        linked_action_replays = [
            str(path)
            for item in action_index.get("items", [])
            if isinstance(item, dict)
            for path in item.get("linked_replays", [])
            if path
        ]
        action_quality_metrics = self._action_quality_metrics(source_episode, action_index=action_index)

        artifact_files = {
            "manifest": str(bundle_dir / "manifest.json"),
            "observations": str(bundle_dir / "observations.json"),
            "raw_inputs": str(bundle_dir / "raw_inputs.json"),
            "scene_facts": str(bundle_dir / "scene_facts.json"),
            "world_model_deltas": str(bundle_dir / "world_model_deltas.json"),
            "planner_inputs": str(bundle_dir / "planner_inputs.json"),
            "planner_outputs": str(bundle_dir / "planner_outputs.json"),
            "playbook_runtime": str(bundle_dir / "playbook_runtime.json"),
            "tool_traces": str(bundle_dir / "tool_traces.json"),
            "memory_reads": str(bundle_dir / "memory_reads.json"),
            "memory_retrievals": str(bundle_dir / "memory_retrievals.json"),
            "memory_writes": str(bundle_dir / "memory_writes.json"),
            "memory_reviews": str(bundle_dir / "memory_reviews.json"),
            "body_actions": str(bundle_dir / "body_actions.json"),
            "final_reply": str(bundle_dir / "final_reply.json"),
            "teacher_corrections": str(bundle_dir / "teacher_corrections.json"),
            "human_feedback": str(bundle_dir / "human_feedback.json"),
            "labels": str(bundle_dir / "labels.json"),
            "benchmark_labels": str(bundle_dir / "benchmark_labels.json"),
            "split": str(bundle_dir / "split.json"),
            "action_bundles": str(bundle_dir / "action_bundles.json"),
            "action_replays": str(bundle_dir / "action_replays.json"),
            "action_quality": str(bundle_dir / "action_quality.json"),
        }

        manifest = ResearchBundleManifest(
            episode_id=source_episode.episode_id,
            source_episode_schema_version=source_episode.schema_version,
            split=split,
            redaction_profile=redaction_profile,
            redaction_state=(
                RedactionState.RAW
                if redaction_profile == ExportRedactionProfile.LOCAL_FULL
                else RedactionState.REDACTED
            ),
            sensitive_content_flags=list(episode.sensitive_content_flags),
            dataset_memberships=[item.model_copy(deep=True) for item in source_episode.dataset_memberships],
            artifact_dir=str(bundle_dir),
            artifact_files=artifact_files,
            linked_action_bundles=linked_action_bundles,
            linked_action_replays=linked_action_replays,
            provenance={
                "source_episode_ref": f"{source_episode.source_type.value}:{source_episode.source_id}",
                "source_episode_artifact_dir": source_episode.artifact_dir,
                "planner_ids": sorted({item.planner_id for item in planner_outputs}),
                "planner_profiles": sorted({item.planner_profile for item in planner_outputs}),
                "environment_fingerprint": environment_fingerprint_for_settings(
                    self.settings,
                    redaction_profile=redaction_profile,
                ),
            },
            quality_metrics=quality_metrics,
            action_quality_metrics=action_quality_metrics,
            notes=[
                f"source_type:{source_episode.source_type.value}",
                f"source_id:{source_episode.source_id}",
                f"redaction_profile:{redaction_profile.value}",
            ],
        )

        self._write_json(Path(artifact_files["observations"]), observations)
        self._write_json(Path(artifact_files["raw_inputs"]), raw_inputs)
        self._write_json(Path(artifact_files["scene_facts"]), episode.scene_facts)
        self._write_json(Path(artifact_files["world_model_deltas"]), episode.world_model_transitions)
        self._write_json(Path(artifact_files["planner_inputs"]), planner_inputs)
        self._write_json(Path(artifact_files["planner_outputs"]), planner_outputs)
        self._write_json(Path(artifact_files["playbook_runtime"]), playbook_runtime)
        self._write_json(Path(artifact_files["tool_traces"]), episode.tool_calls)
        self._write_json(Path(artifact_files["memory_reads"]), memory_reads)
        self._write_json(Path(artifact_files["memory_retrievals"]), episode.memory_retrievals)
        self._write_json(Path(artifact_files["memory_writes"]), episode.memory_actions)
        self._write_json(Path(artifact_files["memory_reviews"]), episode.memory_reviews)
        self._write_json(Path(artifact_files["body_actions"]), body_actions)
        self._write_json(Path(artifact_files["final_reply"]), final_reply)
        self._write_json(Path(artifact_files["teacher_corrections"]), episode.teacher_annotations)
        self._write_json(Path(artifact_files["human_feedback"]), human_feedback)
        self._write_json(Path(artifact_files["labels"]), labels)
        self._write_json(Path(artifact_files["benchmark_labels"]), episode.benchmark_labels)
        self._write_json(Path(artifact_files["split"]), split)
        self._write_json(Path(artifact_files["action_bundles"]), linked_action_bundles)
        self._write_json(Path(artifact_files["action_replays"]), linked_action_replays)
        self._write_json(Path(artifact_files["action_quality"]), action_quality_metrics)

        adapter_exports: dict[str, str] = {}
        if ResearchExportFormat.LEROBOT_LIKE in requested_formats:
            lerobot_path = bundle_dir / "lerobot_like.json"
            self._write_json(
                lerobot_path,
                {
                    "schema_version": "lerobot_like/v0",
                    "adapter_status": "experimental_repo_native",
                    "episode_id": source_episode.episode_id,
                    "observations": observations,
                    "actions": [item.model_dump(mode="json") for item in body_actions],
                    "labels": labels,
                },
            )
            adapter_exports["lerobot_like"] = str(lerobot_path)
            manifest.adapter_export_status["lerobot_like"] = {
                "status": "experimental_repo_native",
                "validated_outside_repo": False,
                "artifact_path": str(lerobot_path),
            }
        if ResearchExportFormat.OPENX_LIKE in requested_formats:
            openx_path = bundle_dir / "openx_like.json"
            self._write_json(
                openx_path,
                {
                    "schema_version": "openx_like/v0",
                    "adapter_status": "experimental_repo_native",
                    "episode_id": source_episode.episode_id,
                    "trajectory": {
                        "observations": observations,
                        "planner_outputs": [item.model_dump(mode="json") for item in planner_outputs],
                        "body_actions": [item.model_dump(mode="json") for item in body_actions],
                    },
                    "split": split.model_dump(mode="json"),
                },
            )
            adapter_exports["openx_like"] = str(openx_path)
            manifest.adapter_export_status["openx_like"] = {
                "status": "experimental_repo_native",
                "validated_outside_repo": False,
                "artifact_path": str(openx_path),
            }
        manifest.adapter_exports = adapter_exports
        self._write_json(Path(artifact_files["manifest"]), manifest)

        self.episode_exporter.episode_store.attach_derived_artifacts(
            source_episode.episode_id,
            derived_artifact_files={
                "research_bundle_manifest": artifact_files["manifest"],
                "research_observations": artifact_files["observations"],
                "research_raw_inputs": artifact_files["raw_inputs"],
                "research_scene_facts": artifact_files["scene_facts"],
                "research_world_model_deltas": artifact_files["world_model_deltas"],
                "research_planner_inputs": artifact_files["planner_inputs"],
                "research_planner_outputs": artifact_files["planner_outputs"],
                "research_playbook_runtime": artifact_files["playbook_runtime"],
                "research_tool_traces": artifact_files["tool_traces"],
                "research_memory_reads": artifact_files["memory_reads"],
                "research_memory_retrievals": artifact_files["memory_retrievals"],
                "research_memory_writes": artifact_files["memory_writes"],
                "research_memory_reviews": artifact_files["memory_reviews"],
                "research_body_actions": artifact_files["body_actions"],
                "research_final_reply": artifact_files["final_reply"],
                "research_teacher_corrections": artifact_files["teacher_corrections"],
                "research_human_feedback": artifact_files["human_feedback"],
                "research_labels": artifact_files["labels"],
                "research_benchmark_labels": artifact_files["benchmark_labels"],
                "research_split": artifact_files["split"],
                "research_action_bundles": artifact_files["action_bundles"],
                "research_action_replays": artifact_files["action_replays"],
                "research_action_quality": artifact_files["action_quality"],
                **{f"research_{name}": path for name, path in adapter_exports.items()},
            },
            notes=[f"research_bundle_exported:{redaction_profile.value}"],
        )
        return manifest

    def _ensure_action_bundle_index(self, episode: EpisodeRecordV2) -> EpisodeRecordV2:
        if episode.artifact_dir is None:
            return episode
        if episode.derived_artifact_files.get("action_bundle_index"):
            return episode
        store = ActionBundleStore(self.settings.blink_action_plane_export_dir)
        related = store.find_related_bundles(
            session_ids=episode.session_ids,
            run_ids=episode.run_ids,
            started_at=episode.started_at,
            completed_at=episode.completed_at,
        )
        if not related:
            return episode
        index_path = Path(episode.artifact_dir) / "linked_action_bundles.json"
        payload = {
            "episode_id": episode.episode_id,
            "bundle_ids": [item.bundle_id for item in related],
            "items": [
                {
                    "bundle_id": item.bundle_id,
                    "manifest_path": item.artifact_files.get("manifest"),
                    "root_kind": item.root_kind.value,
                    "workflow_run_id": item.workflow_run_id,
                    "linked_replays": [replay.artifact_files.get("manifest") for replay in store.list_replays(bundle_id=item.bundle_id)],
                }
                for item in related
            ],
        }
        write_json_atomic(index_path, payload)
        store.attach_episode_links(episode_id=episode.episode_id, bundle_ids=[item.bundle_id for item in related])
        return self.episode_exporter.episode_store.attach_derived_artifacts(
            episode.episode_id,
            derived_artifact_files={"action_bundle_index": str(index_path)},
            notes=[f"action_bundles_linked:{len(related)}"],
        )

    def _action_quality_metrics(
        self,
        episode: EpisodeRecordV2,
        *,
        action_index: dict[str, object],
    ) -> list[DatasetQualityMetric]:
        items = [item for item in action_index.get("items", []) if isinstance(item, dict)]
        replay_count = sum(len(item.get("linked_replays", [])) for item in items)
        return [
            DatasetQualityMetric(
                name="linked_action_bundle_count",
                value=float(len(items)),
                note=f"episode={episode.episode_id}",
            ),
            DatasetQualityMetric(
                name="linked_action_replay_count",
                value=float(replay_count),
                note=f"episode={episode.episode_id}",
            ),
        ]

    def _observations(self, episode: EpisodeRecordV2) -> list[dict[str, object]]:
        observations: list[dict[str, object]] = []
        for entry in episode.transcript:
            observations.append(
                {
                    "kind": "conversation_turn",
                    "session_id": entry.session_id,
                    "timestamp": entry.turn.timestamp.isoformat(),
                    "event_type": entry.turn.event_type,
                    "source": entry.turn.source,
                    "participant_id": entry.turn.participant_id,
                    "user_text": entry.turn.user_text,
                    "reply_text": entry.turn.reply_text,
                    "intent": entry.turn.intent,
                    "trace_id": entry.turn.trace_id,
                }
            )
        for snapshot in episode.perception_snapshots:
            observations.append(
                {
                    "kind": "perception_snapshot",
                    "session_id": snapshot.session_id,
                    "timestamp": snapshot.created_at.isoformat(),
                    "provider_mode": snapshot.provider_mode.value,
                    "tier": snapshot.tier.value,
                    "trigger_reason": snapshot.trigger_reason,
                    "scene_summary": snapshot.scene_summary,
                    "limited_awareness": snapshot.limited_awareness,
                    "source_kind": snapshot.source_frame.source_kind,
                }
            )
        observations.sort(key=lambda item: str(item.get("timestamp") or ""))
        return observations

    def _playbook_runtime(self, episode: EpisodeRecordV2) -> list[dict[str, object]]:
        return [
            {
                "trace_id": trace.trace_id,
                "session_id": trace.session_id,
                "run_id": trace.reasoning.run_id,
                "active_skill": (
                    trace.reasoning.active_skill.skill_name
                    if trace.reasoning.active_skill is not None
                    else None
                ),
                "active_playbook": trace.reasoning.active_playbook,
                "active_playbook_variant": trace.reasoning.active_playbook_variant,
                "active_subagent": trace.reasoning.active_subagent,
                "tool_chain": list(trace.reasoning.tool_chain),
            }
            for trace in episode.traces
        ]

    def _quality_metrics(self, episode: EpisodeRecordV2) -> list[DatasetQualityMetric]:
        trace_count = max(1, len(episode.traces))
        return [
            DatasetQualityMetric(
                name="retrieval_coverage",
                value=min(1.0, len(episode.memory_retrievals) / trace_count),
                note=f"retrievals={len(episode.memory_retrievals)} traces={len(episode.traces)}",
            ),
            DatasetQualityMetric(
                name="teacher_supervision_coverage",
                value=min(1.0, len(episode.teacher_annotations) / trace_count),
                note=f"teacher_annotations={len(episode.teacher_annotations)}",
            ),
            DatasetQualityMetric(
                name="memory_action_density",
                value=min(1.0, len(episode.memory_actions) / trace_count),
                note=f"memory_actions={len(episode.memory_actions)}",
            ),
        ]

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(payload, "model_dump"):
            serialized = payload.model_dump(mode="json")  # type: ignore[union-attr]
        elif isinstance(payload, list):
            serialized = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in payload
            ]
        else:
            serialized = payload
        write_json_atomic(path, serialized)


class DatasetManifestBuilder:
    def __init__(
        self,
        *,
        settings: Settings,
        episode_exporter: BlinkEpisodeExporter,
        research_exporter: ResearchBundleExporter,
        store: DatasetManifestStore,
    ) -> None:
        self.settings = settings
        self.episode_exporter = episode_exporter
        self.research_exporter = research_exporter
        self.store = store

    @classmethod
    def from_settings(
        cls,
        *,
        settings: Settings,
        episode_exporter: BlinkEpisodeExporter,
    ) -> "DatasetManifestBuilder":
        return cls(
            settings=settings,
            episode_exporter=episode_exporter,
            research_exporter=ResearchBundleExporter.from_settings(
                settings=settings,
                episode_exporter=episode_exporter,
            ),
            store=DatasetManifestStore(Path(settings.episode_export_dir).resolve().parent / "datasets"),
        )

    def export_dataset(self, request: DatasetExportRequest) -> DatasetManifestV1:
        episode_ids = list(request.episode_ids)
        if not episode_ids:
            episode_ids = [item.episode_id for item in self.episode_exporter.list_episodes().items]

        manifest = DatasetManifestV1(
            name=request.name,
            redaction_profile=request.redaction_profile,
            notes=list(request.notes),
        )
        entries: list[DatasetEpisodeEntry] = []
        leakage_groups: defaultdict[str, set[str]] = defaultdict(set)

        for episode_id in episode_ids:
            episode = self.episode_exporter.get_episode(episode_id)
            if episode is None:
                raise KeyError(episode_id)
            research_manifest = self.research_exporter.export_episode(
                episode_id,
                formats=[ResearchExportFormat.NATIVE],
                redaction_profile=request.redaction_profile,
            )
            split = deterministic_split_for_episode(episode)
            quality_metrics = self.research_exporter._quality_metrics(episode)
            entry = DatasetEpisodeEntry(
                episode_id=episode.episode_id,
                source_ref=f"{episode.source_type.value}:{episode.source_id}",
                split=split,
                research_bundle_manifest=research_manifest.artifact_files.get("manifest"),
                redaction_profile=request.redaction_profile,
                benchmark_labels=list(episode.benchmark_labels),
                sensitive_content_flags=list(episode.sensitive_content_flags),
                quality_metrics=quality_metrics,
                notes=[f"research_manifest:{research_manifest.bundle_id}"],
            )
            membership = EpisodeDatasetMembership(
                dataset_id=manifest.dataset_id,
                split_name=split.split_name.value,
                entry_id=entry.entry_id,
            )
            entry.dataset_membership = membership
            entries.append(entry)
            leakage_groups[split.leakage_group_key or split.group_key].add(split.split_name.value)

        conflicting = {
            key: values
            for key, values in leakage_groups.items()
            if len(values) > 1
        }
        if conflicting:
            raise ValueError(f"dataset_leakage_detected:{sorted(conflicting)}")

        split_counts = Counter(entry.split.split_name.value for entry in entries)
        manifest.entries = entries
        manifest.split_counts = dict(split_counts)
        manifest.episode_count = len(entries)
        manifest.quality_metrics = [
            DatasetQualityMetric(name="episode_count", value=float(len(entries))),
            DatasetQualityMetric(
                name="retrieval_trace_count",
                value=float(sum(1 for entry in entries if any(metric.name == "retrieval_coverage" and metric.value > 0.0 for metric in entry.quality_metrics))),
            ),
            DatasetQualityMetric(
                name="teacher_supervision_episode_count",
                value=float(sum(1 for entry in entries if any(metric.name == "teacher_supervision_coverage" and metric.value > 0.0 for metric in entry.quality_metrics))),
            ),
        ]
        saved = self.store.save(manifest)

        for entry in entries:
            if entry.dataset_membership is None:
                continue
            self.episode_exporter.episode_store.attach_derived_artifacts(
                entry.episode_id,
                derived_artifact_files={
                    f"dataset_manifest_{saved.dataset_id}": saved.artifact_files.get("manifest") or "",
                },
                notes=[f"dataset_manifest_exported:{saved.dataset_id}"],
                dataset_memberships=[entry.dataset_membership],
            )
        return saved

    def list_datasets(self) -> DatasetManifestListResponse:
        return self.store.list()

    def get_dataset(self, dataset_id: str) -> DatasetManifestV1 | None:
        return self.store.get(dataset_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Stage 5 research bundles from Blink episodes.")
    subparsers = parser.add_subparsers(dest="command")

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("episode_id")
    export_parser.add_argument(
        "--formats",
        default="native",
        help="Comma-separated research export formats: native,lerobot_like,openx_like",
    )
    export_parser.add_argument(
        "--redaction-profile",
        default=ExportRedactionProfile.RESEARCH_REDACTED.value,
        help="Redaction profile: local_full, local_operator, research_redacted",
    )

    args = parser.parse_args()
    settings = get_settings()
    exporter = build_exporter(settings=settings)
    research_exporter = ResearchBundleExporter.from_settings(settings=settings, episode_exporter=exporter)

    if args.command is None:
        dataset_builder = DatasetManifestBuilder.from_settings(settings=settings, episode_exporter=exporter)
        print(
            json.dumps(
                {
                    "episode_count": len(exporter.list_episodes().items),
                    "dataset_manifest_count": len(dataset_builder.list_datasets().items),
                    "default_redaction_profile": ExportRedactionProfile.RESEARCH_REDACTED.value,
                },
                indent=2,
            )
        )
        return

    if args.command == "export":
        format_names = [item.strip() for item in str(args.formats).split(",") if item.strip()]
        formats = [ResearchExportFormat(item) for item in format_names]
        manifest = research_exporter.export_episode(
            args.episode_id,
            formats=formats,
            redaction_profile=ExportRedactionProfile(args.redaction_profile),
        )
        print(json.dumps(manifest.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
