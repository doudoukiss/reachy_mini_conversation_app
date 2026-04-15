import json
from pathlib import Path

from embodied_stack.demo.episodes import EpisodeStore
from embodied_stack.shared.contracts.demo import EpisodeRecord as EpisodeRecordV1
from embodied_stack.shared.contracts.demo import EpisodeSummary as EpisodeSummaryV1
from embodied_stack.shared.contracts import EpisodeSourceType


def test_export_session_episode_includes_multimodal_state_and_stage3_artifacts(brain_client):
    scene = brain_client.post(
        "/api/operator/investor-scenes/read_visible_sign_and_answer/run",
        json={"session_id": "episode-session", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert scene.status_code == 200

    follow_up = brain_client.post(
        "/api/operator/text-turn",
        json={
            "session_id": "episode-session",
            "input_text": "What events are happening this week?",
            "voice_mode": "stub_demo",
            "speak_reply": False,
        },
    )
    assert follow_up.status_code == 200

    note = brain_client.post(
        "/api/sessions/episode-session/operator-notes",
        json={"text": "Prefer the quiet route if the lobby is crowded.", "author": "operator"},
    )
    assert note.status_code == 200

    exported = brain_client.post(
        "/api/operator/episodes/export-session",
        json={
            "session_id": "episode-session",
            "redact_operator_notes": True,
            "redact_session_memory": True,
            "include_asset_refs": True,
        },
    )
    assert exported.status_code == 200
    body = exported.json()

    assert body["schema_version"] == "blink_episode/v2"
    assert body["source_type"] == "session"
    assert body["source_id"] == "episode-session"
    assert body["session_ids"] == ["episode-session"]
    assert "action_bundle_index" in body["derived_artifact_files"]
    assert "input_events" in body
    assert body["transcript"]
    assert body["tool_calls"]
    assert body["perception_snapshots"]
    assert body["world_model_transitions"]
    assert body["executive_decisions"]
    assert "incidents" in body
    assert "incident_timeline" in body
    assert body["commands"]
    assert body["acknowledgements"]
    assert body["telemetry"]
    assert body["episodic_memory"]
    assert body["semantic_memory"]
    assert "profile_memory" in body
    assert "relationship_memory" in body
    assert "procedural_memory" in body
    assert body["grounding_sources"]
    assert body["annotations"]
    assert "scene_facts" in body
    assert "chosen_skills" in body
    assert "chosen_subagents" in body
    assert "run_ids" in body
    assert "memory_actions" in body
    assert "memory_reviews" in body
    assert "memory_retrievals" in body
    assert "teacher_annotations" in body
    assert "teacher_supervision_summary" in body
    assert "benchmark_labels" in body
    assert "dataset_memberships" in body
    assert "outcome_label" in body
    assert body["redaction_profile"] == "local_full"
    assert "sensitive_content_flags" in body
    assert "operator_notes" in body["redactions_applied"]
    assert "session_memory" in body["redactions_applied"]
    assert body["sessions"][0]["operator_notes"][-1]["text"] == "[redacted]"
    assert body["sessions"][0]["session_memory"] == {"redacted": "[redacted]"}
    assert any(item["asset_kind"] in {"image_frame", "video_clip"} for item in body["asset_refs"])
    assert Path(body["artifact_files"]["episode"]).exists()
    assert Path(body["artifact_files"]["annotations"]).exists()
    assert Path(body["artifact_files"]["transcript"]).exists()
    assert Path(body["artifact_files"]["incidents"]).exists()
    assert Path(body["artifact_files"]["incident_timeline"]).exists()
    assert Path(body["artifact_files"]["episodic_memory"]).exists()
    assert Path(body["artifact_files"]["semantic_memory"]).exists()
    assert Path(body["artifact_files"]["profile_memory"]).exists()
    assert Path(body["artifact_files"]["relationship_memory"]).exists()
    assert Path(body["artifact_files"]["procedural_memory"]).exists()
    assert Path(body["artifact_files"]["scene_facts"]).exists()
    assert Path(body["artifact_files"]["memory_actions"]).exists()
    assert Path(body["artifact_files"]["memory_reviews"]).exists()
    assert Path(body["artifact_files"]["teacher_annotations"]).exists()
    assert Path(body["artifact_files"]["input_events"]).exists()
    assert Path(body["artifact_files"]["memory_retrievals"]).exists()
    assert Path(body["artifact_files"]["teacher_supervision_summary"]).exists()
    assert Path(body["artifact_files"]["benchmark_labels"]).exists()
    assert Path(body["artifact_files"]["dataset_memberships"]).exists()
    assert Path(body["artifact_files"]["runtime_snapshot"]).exists()
    action_bundle_index = Path(body["derived_artifact_files"]["action_bundle_index"])
    assert action_bundle_index.exists()
    action_bundle_entries = json.loads(action_bundle_index.read_text(encoding="utf-8"))
    assert action_bundle_entries["episode_id"] == body["episode_id"]
    assert isinstance(action_bundle_entries["bundle_ids"], list)
    assert isinstance(action_bundle_entries["items"], list)
    runtime_snapshot = json.loads(Path(body["artifact_files"]["runtime_snapshot"]).read_text(encoding="utf-8"))
    assert runtime_snapshot["runtime"]["memory_status"]["status"] in {"session_only", "grounded"}
    assert "perception_freshness" in runtime_snapshot["runtime"]
    assert "fallback_state" in runtime_snapshot["runtime"]

    listed = brain_client.get("/api/operator/episodes")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["episode_id"] == body["episode_id"]

    detail = brain_client.get(f"/api/operator/episodes/{body['episode_id']}")
    assert detail.status_code == 200
    assert detail.json()["episode_id"] == body["episode_id"]


def test_export_demo_run_episode_uses_report_bundle(brain_client):
    run = brain_client.post(
        "/api/demo-runs",
        json={"scenario_names": ["welcome_and_wayfinding", "safe_fallback_demo"]},
    )
    assert run.status_code == 200
    run_body = run.json()

    exported = brain_client.post(
        "/api/operator/episodes/export-demo-run",
        json={"run_id": run_body["run_id"], "include_asset_refs": True},
    )
    assert exported.status_code == 200
    body = exported.json()

    assert body["source_type"] == "demo_run"
    assert body["source_id"] == run_body["run_id"]
    assert body["scenario_names"] == ["welcome_and_wayfinding", "safe_fallback_demo"]
    assert body["derived_artifact_files"] == {}
    assert len(body["sessions"]) == 2
    assert body["commands"]
    assert body["acknowledgements"]
    assert body["telemetry"]
    assert "episodic_memory" in body
    assert "semantic_memory" in body
    assert "profile_memory" in body
    assert "relationship_memory" in body
    assert "procedural_memory" in body
    assert "incidents" in body
    assert "incident_timeline" in body
    assert body["annotations"]
    assert any(item["label_name"] == "safe_fallback_correctness" for item in body["annotations"])
    assert Path(body["artifact_files"]["episode"]).exists()
    assert Path(body["artifact_files"]["sessions"]).exists()
    assert Path(body["artifact_files"]["telemetry"]).exists()
    assert Path(body["artifact_files"]["manifest"]).exists()
    assert body["schema_version"] == "blink_episode/v2"
    assert "memory_actions" in body
    assert "teacher_annotations" in body
    assert "memory_retrievals" in body
    assert "teacher_supervision_summary" in body
    assert "benchmark_labels" in body


def test_episode_store_reads_v1_artifacts_with_v2_upgrade(tmp_path):
    store = EpisodeStore(tmp_path)
    episode_dir = tmp_path / "legacy-episode"
    episode_dir.mkdir(parents=True, exist_ok=True)

    summary = EpisodeSummaryV1(
        episode_id="legacy-episode",
        source_type=EpisodeSourceType.SESSION,
        source_id="legacy-session",
    )
    episode = EpisodeRecordV1(
        episode_id="legacy-episode",
        source_type=EpisodeSourceType.SESSION,
        source_id="legacy-session",
    )

    (episode_dir / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    (episode_dir / "episode.json").write_text(episode.model_dump_json(indent=2), encoding="utf-8")

    listed = store.list()
    loaded = store.get("legacy-episode")

    assert listed.items[0].schema_version == "blink_episode/v2"
    assert loaded is not None
    assert loaded.schema_version == "blink_episode/v2"
    assert loaded.source_id == "legacy-session"
