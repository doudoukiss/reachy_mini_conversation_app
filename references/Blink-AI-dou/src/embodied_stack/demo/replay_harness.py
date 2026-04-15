from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.episodes import BlinkEpisodeExporter, build_exporter
from embodied_stack.demo.research import (
    STRICT_REPLAY_ACCEPTABLE_FIELDS,
    STRICT_REPLAY_POLICY_VERSION,
    environment_fingerprint_for_settings,
    planner_output_from_trace,
    source_perception_for_trace,
    source_world_model_for_trace,
    strict_replay_policy_notes,
)
from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.contracts import (
    BenchmarkComparisonMode,
    BodyDriverMode,
    GroundingSourceType,
    PlannerCatalogResponse,
    PlannerDescriptor,
    PlannerDiffRecord,
    PlannerInputRecord,
    PlannerOutputRecord,
    PlannerReplayMode,
    PlannerReplayRecord,
    PlannerReplayRequest,
    PlannerReplayStepRecord,
    RobotMode,
)


@dataclass
class ReplayStore:
    export_dir: str | Path

    RUN_FILE = "replay.json"
    STEPS_FILE = "steps.json"
    DIVERGENCE_SUMMARY_FILE = "divergence_summary.json"

    def __post_init__(self) -> None:
        self.export_dir = Path(self.export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: PlannerReplayRecord) -> PlannerReplayRecord:
        replay_dir = self.export_dir / record.replay_id
        replay_dir.mkdir(parents=True, exist_ok=True)
        record.artifact_dir = str(replay_dir)
        record.artifact_files = {
            "replay": str(replay_dir / self.RUN_FILE),
            "steps": str(replay_dir / self.STEPS_FILE),
            "divergence_summary": str(replay_dir / self.DIVERGENCE_SUMMARY_FILE),
        }
        self._write_json(Path(record.artifact_files["replay"]), record)
        self._write_json(Path(record.artifact_files["steps"]), record.steps)
        self._write_json(Path(record.artifact_files["divergence_summary"]), record.divergence_summary)
        return record.model_copy(deep=True)

    def get(self, replay_id: str) -> PlannerReplayRecord | None:
        path = self.export_dir / replay_id / self.RUN_FILE
        if not path.exists():
            return None
        return load_json_model_or_quarantine(path, PlannerReplayRecord, quarantine_invalid=True)

    def _write_json(self, path: Path, payload: object) -> None:
        if hasattr(payload, "model_dump"):
            serialized = payload.model_dump(mode="json")  # type: ignore[union-attr]
        elif isinstance(payload, list):
            serialized = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in payload]
        else:
            serialized = payload
        write_json_atomic(path, serialized)


@dataclass
class EpisodeReplayHarness:
    settings: Settings
    episode_exporter: BlinkEpisodeExporter
    store: ReplayStore

    @classmethod
    def from_settings(cls, *, settings: Settings, episode_exporter: BlinkEpisodeExporter) -> "EpisodeReplayHarness":
        return cls(
            settings=settings,
            episode_exporter=episode_exporter,
            store=ReplayStore(settings.replay_export_dir),
        )

    def list_planners(self) -> PlannerCatalogResponse:
        return self.episode_exporter.orchestrator.list_planners()

    def get_replay(self, replay_id: str) -> PlannerReplayRecord | None:
        return self.store.get(replay_id)

    def replay_episode(self, request: PlannerReplayRequest) -> PlannerReplayRecord:
        episode = self.episode_exporter.get_episode(request.episode_id)
        if episode is None:
            raise KeyError(request.episode_id)
        descriptor = self._descriptor(request.planner_id, request.planner_profile)
        if request.replay_mode == PlannerReplayMode.STRICT and not descriptor.supports_strict_mode:
            raise ValueError(f"planner_does_not_support_strict:{request.planner_id}:{request.planner_profile}")

        with TemporaryDirectory() as tmp_dir:
            scratch = self._scratch_orchestrator(
                Path(tmp_dir),
                planner_id=request.planner_id,
                planner_profile=request.planner_profile,
            )
            self._seed_sessions(scratch, episode)
            steps: list[PlannerReplayStepRecord] = []
            pending_perception = sorted(
                episode.perception_snapshots,
                key=lambda item: item.created_at,
            )
            perception_cursor = 0

            for step_index, source_trace in enumerate(sorted(episode.traces, key=lambda item: item.timestamp), start=1):
                while perception_cursor < len(pending_perception) and pending_perception[perception_cursor].created_at <= source_trace.timestamp:
                    scratch.memory.upsert_perception_snapshot(pending_perception[perception_cursor].model_copy(deep=True))
                    perception_cursor += 1

                world_model_before = source_world_model_for_trace(episode, source_trace)
                if world_model_before is not None:
                    scratch.memory.replace_world_model(world_model_before.model_copy(deep=True))

                session = scratch.memory.get_session(source_trace.session_id)
                if session is None:
                    self._seed_sessions(scratch, episode)
                    session = scratch.memory.get_session(source_trace.session_id)
                if session is None:
                    raise KeyError(source_trace.session_id)

                latest_perception = source_perception_for_trace(episode, source_trace)
                source_output = planner_output_from_trace(source_trace, episode=episode)
                text = str(source_trace.event.payload.get("text")) if isinstance(source_trace.event.payload, dict) and source_trace.event.payload.get("text") else ""
                user_memory = scratch._get_or_create_user_memory(session)
                tool_invocations = (
                    scratch.knowledge_tools.lookup(
                        text,
                        session=session,
                        user_memory=user_memory,
                        world_state=scratch.memory.get_world_state(),
                        world_model=scratch.memory.get_world_model(),
                        latest_perception=latest_perception,
                    )
                    if source_trace.event.event_type == "speech_transcript"
                    else []
                )
                memory_updates = scratch.interaction.extract_memory_updates(text=text) if text else {}
                for tool in tool_invocations:
                    memory_updates.update(tool.memory_updates)
                planner_input = PlannerInputRecord(
                    source_trace_id=source_trace.trace_id,
                    session_id=session.session_id,
                    user_id=session.user_id,
                    input_text=text or None,
                    event=source_trace.event.model_copy(deep=True),
                    session_snapshot=session.model_copy(deep=True),
                    world_model=scratch.memory.get_world_model(),
                    latest_perception=latest_perception.model_copy(deep=True) if latest_perception is not None else None,
                    tool_invocations=[item.model_copy(deep=True) for item in tool_invocations],
                    memory_updates=dict(memory_updates),
                    strict_replay_policy_version=STRICT_REPLAY_POLICY_VERSION,
                    normalized_scene_facts=source_output.normalized_scene_facts_used,
                    selected_tool_chain=source_output.selected_tool_chain,
                    retrieved_memory_candidates=source_output.retrieved_memory_candidates,
                    planner_input_envelope={
                        "event_type": source_trace.event.event_type,
                        "active_playbook": source_trace.reasoning.active_playbook,
                        "active_subagent": source_trace.reasoning.active_subagent,
                        "memory_update_keys": sorted(memory_updates),
                    },
                    replay_mode=request.replay_mode,
                )

                replay_response = scratch.handle_event(source_trace.event.model_copy(deep=True))
                replay_trace = scratch.memory.get_trace(replay_response.trace_id) if replay_response.trace_id is not None else None
                replay_output = (
                    planner_output_from_trace(replay_trace)
                    if replay_trace is not None
                    else PlannerOutputRecord(
                        planner_id=request.planner_id,
                        planner_profile=request.planner_profile,
                        engine_name=request.planner_id,
                        reply_text=replay_response.reply_text,
                        intent="unknown",
                        strict_replay_policy_version=STRICT_REPLAY_POLICY_VERSION,
                        selected_tool_chain=[],
                        planner_output_envelope={},
                        embodiment_output_envelope={},
                        commands=list(replay_response.commands),
                        notes=["trace_missing_from_replay"],
                    )
                )
                replay_output = replay_output.model_copy(
                    update={"planner_id": request.planner_id, "planner_profile": request.planner_profile}
                )
                diffs = self._diffs(
                    source_output=source_output,
                    source_trace=source_trace,
                    replay_output=replay_output,
                    replay_trace=replay_trace,
                    replay_response=replay_response,
                )
                divergence_summary = self._divergence_summary(diffs)
                matched = divergence_summary.get("review_required", 0) == 0 and divergence_summary.get("failing", 0) == 0
                steps.append(
                    PlannerReplayStepRecord(
                        step_index=step_index,
                        source_trace_id=source_trace.trace_id,
                        session_id=source_trace.session_id,
                        event=source_trace.event.model_copy(deep=True),
                        source_response=source_trace.response.model_copy(deep=True),
                        planner_input=planner_input,
                        planner_output=replay_output,
                        replay_response=replay_response.model_copy(deep=True),
                        diffs=diffs,
                        matched=matched,
                        match_score=(sum(1 for item in diffs if item.matched) / len(diffs)) if diffs else 1.0,
                        divergence_summary=divergence_summary,
                        normalized_envelope_refs={
                            "source_trace_id": source_trace.trace_id,
                            "replay_trace_id": replay_trace.trace_id if replay_trace is not None else "",
                        },
                        note=f"source_trace:{source_trace.trace_id}",
                    )
                )

        divergence_summary = {
            "matched": sum(1 for item in steps if item.matched),
            "acceptable": sum(step.divergence_summary.get("acceptable", 0) for step in steps),
            "review_required": sum(step.divergence_summary.get("review_required", 0) for step in steps),
            "failing": sum(step.divergence_summary.get("failing", 0) for step in steps),
        }
        record = PlannerReplayRecord(
            episode_id=episode.episode_id,
            planner_id=request.planner_id,
            planner_profile=request.planner_profile,
            replay_mode=request.replay_mode,
            comparison_mode=request.comparison_mode,
            deterministic=descriptor.deterministic and request.replay_mode == PlannerReplayMode.STRICT,
            strict_replay_policy_version=STRICT_REPLAY_POLICY_VERSION,
            replay_policy_notes=strict_replay_policy_notes(),
            acceptable_divergence_fields=list(STRICT_REPLAY_ACCEPTABLE_FIELDS),
            environment_fingerprint=environment_fingerprint_for_settings(
                self.settings,
                planner_id=request.planner_id,
                planner_profile=request.planner_profile,
            ),
            source_episode_ref=f"{episode.source_type.value}:{episode.source_id}",
            source_episode_artifact_dir=episode.artifact_dir,
            step_count=len(steps),
            matched_step_count=sum(1 for item in steps if item.matched),
            match_ratio=(sum(1 for item in steps if item.matched) / len(steps)) if steps else 1.0,
            divergence_summary=divergence_summary,
            normalized_envelope_refs={
                "source_episode_manifest": episode.artifact_files.get("manifest", ""),
                "source_episode_summary": episode.artifact_files.get("summary", ""),
            },
            steps=steps,
            notes=[f"source_episode:{episode.episode_id}", f"planner:{request.planner_id}:{request.planner_profile}"],
        )
        record.completed_at = record.started_at
        return self.store.save(record)

    def _descriptor(self, planner_id: str, planner_profile: str) -> PlannerDescriptor:
        descriptors = self.list_planners().items
        for descriptor in descriptors:
            if descriptor.planner_id == planner_id:
                if planner_profile in descriptor.available_profiles or planner_profile == descriptor.default_profile:
                    return descriptor.model_copy(deep=True)
        raise KeyError(planner_id)

    def _scratch_orchestrator(self, root: Path, *, planner_id: str, planner_profile: str) -> BrainOrchestrator:
        settings = self.settings.model_copy(
            update={
                "brain_store_path": str(root / "brain_store.json"),
                "demo_report_dir": str(root / "demo_runs"),
                "shift_report_dir": str(root / "shift_reports"),
                "episode_export_dir": str(root / "episodes"),
                "perception_frame_dir": str(root / "perception_frames"),
                "blink_runtime_mode": RobotMode.DESKTOP_VIRTUAL_BODY,
                "blink_body_driver": BodyDriverMode.VIRTUAL,
                "blink_planner_id": planner_id,
                "blink_planner_profile": planner_profile,
                "shift_background_tick_enabled": False,
            }
        )
        return BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)

    def _seed_sessions(self, orchestrator: BrainOrchestrator, episode) -> None:
        for session in episode.sessions:
            orchestrator.memory.upsert_session(
                orchestrator.memory.ensure_session(
                    session.session_id,
                    user_id=session.user_id,
                    channel=session.channel,
                    scenario_name=session.scenario_name,
                    response_mode=session.response_mode,
                ).model_copy(
                    update={
                        "operator_notes": [item.model_copy(deep=True) for item in session.operator_notes],
                        "status": session.status,
                        "active_incident_ticket_id": session.active_incident_ticket_id,
                        "incident_status": session.incident_status,
                    }
                )
            )

    def _diffs(
        self,
        *,
        source_output: PlannerOutputRecord,
        source_trace,
        replay_output: PlannerOutputRecord,
        replay_trace,
        replay_response,
    ) -> list[PlannerDiffRecord]:
        source_command_types = [command.command_type.value for command in source_output.commands]
        replay_command_types = [command.command_type.value for command in replay_response.commands]
        source_tool_names = [item.tool_name for item in source_output.typed_tool_calls]
        replay_tool_names = [item.tool_name for item in replay_output.typed_tool_calls]
        source_memory_winners = self._retrieval_winner_keys(source_output, trace=source_trace)
        replay_memory_winners = self._retrieval_winner_keys(replay_output, trace=replay_trace)
        source_scene_refs = self._scene_fact_refs(source_output)
        replay_scene_refs = self._scene_fact_refs(replay_output)
        return [
            self._diff_record(
                "reply_text",
                source_output.reply_text or "",
                replay_response.reply_text or "",
                review_required=(
                    (source_output.reply_text or "") != (replay_response.reply_text or "")
                    and source_tool_names == replay_tool_names
                    and source_command_types == replay_command_types
                ),
                review_reason="reply_text_paraphrase_drift",
                failing_reason="reply_text_mismatch",
            ),
            self._diff_record(
                "intent",
                source_output.intent,
                replay_output.intent,
                failing_reason="intent_changed",
            ),
            self._diff_record(
                "active_skill",
                source_output.active_skill,
                replay_output.active_skill,
                failing_reason="active_skill_changed",
            ),
            self._diff_record(
                "active_playbook",
                source_output.active_playbook,
                replay_output.active_playbook,
                failing_reason="active_playbook_changed",
            ),
            self._diff_record(
                "active_playbook_variant",
                source_output.active_playbook_variant,
                replay_output.active_playbook_variant,
                failing_reason="active_playbook_variant_changed",
            ),
            self._diff_record(
                "active_subagent",
                source_output.active_subagent,
                replay_output.active_subagent,
                failing_reason="active_subagent_changed",
            ),
            self._diff_record(
                "command_types",
                source_command_types,
                replay_command_types,
                failing_reason="embodiment_command_types_changed",
            ),
            self._diff_record(
                "typed_tool_names",
                source_tool_names,
                replay_tool_names,
                review_required=set(source_tool_names) == set(replay_tool_names) and source_tool_names != replay_tool_names,
                review_reason="tool_order_shift",
                failing_reason="tool_selection_changed",
            ),
            self._diff_record(
                "selected_tool_chain",
                source_output.selected_tool_chain,
                replay_output.selected_tool_chain,
                review_required=(
                    set(source_output.selected_tool_chain) == set(replay_output.selected_tool_chain)
                    and source_output.selected_tool_chain != replay_output.selected_tool_chain
                ),
                review_reason="tool_chain_rank_shift",
                failing_reason="tool_chain_changed",
            ),
            self._diff_record(
                "retrieval_winners",
                source_memory_winners,
                replay_memory_winners,
                review_required=set(source_memory_winners) == set(replay_memory_winners) and source_memory_winners != replay_memory_winners,
                review_reason="retrieval_rank_shift",
                failing_reason="retrieval_winners_changed",
            ),
            self._diff_record(
                "fallback_used",
                source_output.fallback_used,
                replay_output.fallback_used,
                failing_reason="fallback_used_changed",
            ),
            self._diff_record(
                "fallback_classification",
                source_output.fallback_classification,
                replay_output.fallback_classification,
                failing_reason="fallback_classification_changed",
            ),
            self._diff_record(
                "grounded_scene_fact_refs",
                source_scene_refs,
                replay_scene_refs,
                failing_reason="grounded_scene_facts_changed",
            ),
            self._diff_record(
                "embodiment_output_envelope",
                source_output.embodiment_output_envelope,
                replay_output.embodiment_output_envelope,
                failing_reason="embodiment_semantics_changed",
            ),
        ]

    @staticmethod
    def _scene_fact_refs(output: PlannerOutputRecord) -> list[str]:
        refs = [
            str(item.get("fact_id") or item.get("source_ref") or item.get("label") or "")
            for item in output.normalized_scene_facts_used
        ]
        return [item for item in refs if item]

    @staticmethod
    def _retrieval_winner_keys(output: PlannerOutputRecord, *, trace=None) -> list[str]:
        winners = [
            str(item.get("memory_id") or item.get("summary") or "")
            for item in output.retrieved_memory_candidates
            if item.get("selected")
        ]
        if winners:
            return [item for item in winners if item]
        memory_source_types = {
            GroundingSourceType.USER_MEMORY,
            GroundingSourceType.PROFILE_MEMORY,
            GroundingSourceType.EPISODIC_MEMORY,
            GroundingSourceType.SEMANTIC_MEMORY,
        }
        refs: list[str] = []
        if trace is None:
            return refs
        for source in trace.reasoning.grounding_sources:
            if source.source_type not in memory_source_types:
                continue
            ref = source.source_ref or source.fact_id or source.label
            if ref:
                refs.append(ref)
        return refs

    @staticmethod
    def _diff_record(
        field_name: str,
        source_value,
        replay_value,
        *,
        review_required: bool = False,
        review_reason: str | None = None,
        failing_reason: str | None = None,
    ) -> PlannerDiffRecord:
        matched = source_value == replay_value
        if matched:
            return PlannerDiffRecord(field_name=field_name, matched=True, source_value=source_value, replay_value=replay_value)
        if review_required:
            return PlannerDiffRecord(
                field_name=field_name,
                matched=False,
                source_value=source_value,
                replay_value=replay_value,
                reason_code=review_reason,
                divergence_class="review_required",
                severity=1,
                acceptable_in_strict=False,
            )
        return PlannerDiffRecord(
            field_name=field_name,
            matched=False,
            source_value=source_value,
            replay_value=replay_value,
            reason_code=failing_reason,
            divergence_class="failing",
            severity=2,
            acceptable_in_strict=False,
        )

    @staticmethod
    def _divergence_summary(diffs: list[PlannerDiffRecord]) -> dict[str, int]:
        summary = {"matched": 0, "acceptable": 0, "review_required": 0, "failing": 0}
        for item in diffs:
            if item.matched:
                summary["matched"] += 1
            else:
                summary[item.divergence_class] = summary.get(item.divergence_class, 0) + 1
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay exported episodes against registered Blink planners.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-planners")

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("replay_id")

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("episode_id")
    replay_parser.add_argument("--planner-id", default="agent_os_current")
    replay_parser.add_argument("--planner-profile", default="default")
    replay_parser.add_argument("--replay-mode", choices=["strict", "observational"], default="strict")
    replay_parser.add_argument(
        "--comparison-mode",
        choices=["episode_only", "replay_only", "episode_vs_replay"],
        default="episode_vs_replay",
    )

    args = parser.parse_args()
    settings = get_settings()
    episode_exporter = build_exporter(settings=settings)
    harness = EpisodeReplayHarness.from_settings(settings=settings, episode_exporter=episode_exporter)

    if args.command == "list-planners":
        print(json.dumps(harness.list_planners().model_dump(mode="json"), indent=2))
        return
    if args.command == "show":
        replay = harness.get_replay(args.replay_id)
        if replay is None:
            raise SystemExit(f"replay_not_found:{args.replay_id}")
        print(json.dumps(replay.model_dump(mode="json"), indent=2))
        return
    if args.command == "replay":
        replay = harness.replay_episode(
            PlannerReplayRequest(
                episode_id=args.episode_id,
                planner_id=args.planner_id,
                planner_profile=args.planner_profile,
                replay_mode=PlannerReplayMode(args.replay_mode),
                comparison_mode=BenchmarkComparisonMode(args.comparison_mode),
            )
        )
        print(json.dumps(replay.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
