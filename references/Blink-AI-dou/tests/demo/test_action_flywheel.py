from __future__ import annotations

import json
from pathlib import Path

from embodied_stack.demo.benchmarks import BenchmarkRunner
from embodied_stack.demo.episodes import build_exporter
from embodied_stack.demo.research import ResearchBundleExporter
from embodied_stack.shared.contracts import (
    BenchmarkFamily,
    BenchmarkRunRequest,
    ExportRedactionProfile,
    ResearchExportFormat,
)


def _prepare_bundle_backed_episode(brain_client, session_id: str) -> dict:
    turn = brain_client.post(
        "/api/operator/text-turn",
        json={
            "session_id": session_id,
            "input_text": "Please remember that I need to follow up tomorrow.",
            "voice_mode": "stub_demo",
            "speak_reply": False,
        },
    )
    assert turn.status_code == 200

    workflow = brain_client.post(
        "/api/operator/action-plane/workflows/start",
        json={
            "workflow_id": "capture_note_and_reminder",
            "session_id": session_id,
            "inputs": {
                "note_title": "Tomorrow follow up",
                "note_content": "Need to follow up tomorrow.",
                "reminder_text": "Follow up tomorrow",
            },
            "note": "action flywheel test",
        },
    )
    assert workflow.status_code == 200
    assert workflow.json()["status"] == "completed"

    exported = brain_client.post(
        "/api/operator/episodes/export-session",
        json={
            "session_id": session_id,
            "redaction_profile": "local_full",
            "include_asset_refs": True,
        },
    )
    assert exported.status_code == 200
    return exported.json()


def test_action_bundle_operator_endpoints_roundtrip(brain_client):
    episode = _prepare_bundle_backed_episode(brain_client, "action-flywheel-operator")
    bundle_index_path = Path(episode["derived_artifact_files"]["action_bundle_index"])
    assert bundle_index_path.exists()
    bundle_index = json.loads(bundle_index_path.read_text(encoding="utf-8"))
    assert bundle_index["bundle_ids"]

    bundles = brain_client.get(
        "/api/operator/action-plane/bundles",
        params={"session_id": "action-flywheel-operator", "limit": 10},
    )
    assert bundles.status_code == 200
    items = bundles.json()["items"]
    assert items
    bundle_id = items[0]["bundle_id"]

    detail = brain_client.get(f"/api/operator/action-plane/bundles/{bundle_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["manifest"]["bundle_id"] == bundle_id
    assert len(detail_body["connector_calls"]) >= 2
    assert detail_body["replays"] == []

    review = brain_client.post(
        f"/api/operator/action-plane/bundles/{bundle_id}/teacher-review",
        json={
            "review_value": "needs_revision",
            "author": "operator_console",
            "note": "Action follow-up needed.",
            "action_feedback_labels": ["missing_follow_up"],
            "benchmark_tags": ["action_trace_completeness"],
        },
    )
    assert review.status_code == 200
    assert review.json()["scope"] in {"action", "workflow_run"}
    assert review.json()["primary_kind"] == "action"

    replay = brain_client.post(
        "/api/operator/action-plane/replays",
        json={"bundle_id": bundle_id},
    )
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["bundle_id"] == bundle_id
    assert replay_body["status"] == "completed"
    assert replay_body["replayed_action_count"] >= 2
    assert Path(replay_body["artifact_files"]["manifest"]).exists()

    detail_after = brain_client.get(f"/api/operator/action-plane/bundles/{bundle_id}")
    assert detail_after.status_code == 200
    detail_after_body = detail_after.json()
    assert detail_after_body["teacher_annotations"]
    assert detail_after_body["replays"]


def test_action_bundle_research_and_benchmark_linkage(
    settings,
    orchestrator,
    demo_coordinator,
    brain_client,
):
    episode = _prepare_bundle_backed_episode(brain_client, "action-flywheel-research")
    bundle_list = brain_client.get(
        "/api/operator/action-plane/bundles",
        params={"session_id": "action-flywheel-research", "limit": 10},
    )
    assert bundle_list.status_code == 200
    bundle_id = bundle_list.json()["items"][0]["bundle_id"]
    review = brain_client.post(
        f"/api/operator/action-plane/bundles/{bundle_id}/teacher-review",
        json={
            "review_value": "good",
            "author": "operator_console",
            "note": "Workflow trace looked complete.",
            "action_feedback_labels": ["wrong_explanation"],
        },
    )
    assert review.status_code == 200

    exporter = build_exporter(
        settings=settings,
        orchestrator=orchestrator,
        report_store=demo_coordinator.report_store,
        edge_gateway=demo_coordinator.edge_gateway,
    )
    research_exporter = ResearchBundleExporter.from_settings(settings=settings, episode_exporter=exporter)
    manifest = research_exporter.export_episode(
        episode["episode_id"],
        formats=[ResearchExportFormat.NATIVE],
        redaction_profile=ExportRedactionProfile.RESEARCH_REDACTED,
    )

    assert manifest.linked_action_bundles
    assert Path(manifest.artifact_files["action_bundles"]).exists()
    assert Path(manifest.artifact_files["action_replays"]).exists()
    assert any(metric.name == "linked_action_bundle_count" for metric in manifest.action_quality_metrics)

    reloaded = exporter.get_episode(episode["episode_id"])
    assert reloaded is not None
    assert reloaded.derived_artifact_files["action_bundle_index"]
    assert any(annotation.scope.value in {"action", "workflow_run"} for annotation in reloaded.teacher_annotations)

    runner = BenchmarkRunner.from_settings(settings=settings, episode_exporter=exporter)
    benchmark = runner.run(
        BenchmarkRunRequest(
            episode_id=episode["episode_id"],
            families=[
                BenchmarkFamily.ACTION_TRACE_COMPLETENESS,
                BenchmarkFamily.ACTION_IDEMPOTENCY,
                BenchmarkFamily.CONNECTOR_SAFETY_POLICY,
            ],
        )
    )

    assert any(item.family == BenchmarkFamily.ACTION_TRACE_COMPLETENESS for item in benchmark.results)
    assert benchmark.evidence_pack_manifest
    evidence_manifest_path = Path(benchmark.evidence_pack_manifest)
    assert evidence_manifest_path.exists()
    evidence_payload = json.loads(evidence_manifest_path.read_text(encoding="utf-8"))
    assert Path(evidence_payload["artifact_files"]["action_bundles"]).exists()
    assert Path(evidence_payload["artifact_files"]["action_replays"]).exists()
