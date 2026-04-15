from __future__ import annotations

from pathlib import Path

from embodied_stack.demo.benchmarks import BenchmarkRunner
from embodied_stack.demo.episodes import build_exporter
from embodied_stack.demo.replay_harness import EpisodeReplayHarness
from embodied_stack.demo.research import (
    DatasetManifestBuilder,
    ResearchBundleExporter,
    deterministic_split_for_episode,
)
from embodied_stack.shared.contracts import (
    BenchmarkComparisonMode,
    BenchmarkFamily,
    BenchmarkRunRequest,
    DatasetExportRequest,
    ExportRedactionProfile,
    PlannerReplayMode,
    PlannerReplayRequest,
    ResearchExportFormat,
)


def _export_reference_episode(brain_client) -> dict:
    scene = brain_client.post(
        "/api/operator/investor-scenes/read_visible_sign_and_answer/run",
        json={"session_id": "research-bridge", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert scene.status_code == 200

    follow_up = brain_client.post(
        "/api/operator/text-turn",
        json={
            "session_id": "research-bridge",
            "input_text": "Can you also remind me what you observed?",
            "voice_mode": "stub_demo",
            "speak_reply": False,
        },
    )
    assert follow_up.status_code == 200

    exported = brain_client.post(
        "/api/operator/episodes/export-session",
        json={"session_id": "research-bridge", "include_asset_refs": True},
    )
    assert exported.status_code == 200
    return exported.json()


def test_research_bundle_export_attaches_artifacts_and_stable_split(settings, orchestrator, demo_coordinator, brain_client):
    episode = _export_reference_episode(brain_client)
    planners = brain_client.get("/api/operator/planners")
    assert planners.status_code == 200
    planner_items = planners.json()["items"]
    assert any(item["planner_id"] == "agent_os_current" for item in planner_items)
    assert any(item["strict_replay_policy_version"] == "blink_strict_replay/v2" for item in planner_items)
    assert any(item["capability_tags"] for item in planner_items)

    exporter = build_exporter(
        settings=settings,
        orchestrator=orchestrator,
        report_store=demo_coordinator.report_store,
        edge_gateway=demo_coordinator.edge_gateway,
    )
    research_exporter = ResearchBundleExporter.from_settings(settings=settings, episode_exporter=exporter)

    manifest = research_exporter.export_episode(
        episode["episode_id"],
        formats=[ResearchExportFormat.NATIVE, ResearchExportFormat.LEROBOT_LIKE, ResearchExportFormat.OPENX_LIKE],
    )

    assert manifest.schema_version == "blink_research_bundle/v1"
    assert manifest.exporter_version == "blink_research_bridge/v2"
    assert manifest.redaction_profile == ExportRedactionProfile.RESEARCH_REDACTED
    assert manifest.provenance["environment_fingerprint"]["redaction_profile"] == "research_redacted"
    assert Path(manifest.artifact_files["manifest"]).exists()
    assert Path(manifest.artifact_files["planner_inputs"]).exists()
    assert Path(manifest.artifact_files["planner_outputs"]).exists()
    assert Path(manifest.artifact_files["split"]).exists()
    assert Path(manifest.artifact_files["memory_retrievals"]).exists()
    assert Path(manifest.artifact_files["teacher_corrections"]).exists()
    assert Path(manifest.adapter_exports["lerobot_like"]).exists()
    assert Path(manifest.adapter_exports["openx_like"]).exists()
    assert manifest.adapter_export_status["lerobot_like"]["status"] == "experimental_repo_native"
    assert manifest.adapter_export_status["openx_like"]["status"] == "experimental_repo_native"

    loaded = exporter.get_episode(episode["episode_id"])
    assert loaded is not None
    assert loaded.derived_artifact_files["research_bundle_manifest"] == manifest.artifact_files["manifest"]
    assert loaded.derived_artifact_files["research_lerobot_like"] == manifest.adapter_exports["lerobot_like"]
    assert loaded.derived_artifact_files["research_openx_like"] == manifest.adapter_exports["openx_like"]

    split_a = deterministic_split_for_episode(loaded)
    split_b = deterministic_split_for_episode(loaded)
    assert split_a.group_key == split_b.group_key
    assert split_a.split_name == split_b.split_name
    assert split_a.leakage_group_key

    dataset_builder = DatasetManifestBuilder.from_settings(settings=settings, episode_exporter=exporter)
    dataset_manifest = dataset_builder.export_dataset(
        request=DatasetExportRequest(
            name="stage_d_dataset",
            episode_ids=[episode["episode_id"]],
            redaction_profile=ExportRedactionProfile.RESEARCH_REDACTED,
        )
    )
    assert dataset_manifest.schema_version == "blink_dataset_manifest/v1"
    assert dataset_manifest.episode_count == 1
    assert Path(dataset_manifest.artifact_files["manifest"]).exists()
    assert dataset_manifest.entries[0].dataset_membership is not None


def test_episode_replay_and_benchmark_runner_keep_source_episode_isolated(
    settings,
    orchestrator,
    demo_coordinator,
    brain_client,
):
    episode = _export_reference_episode(brain_client)
    exporter = build_exporter(
        settings=settings,
        orchestrator=orchestrator,
        report_store=demo_coordinator.report_store,
        edge_gateway=demo_coordinator.edge_gateway,
    )
    original = exporter.get_episode(episode["episode_id"])
    assert original is not None
    original_payload = original.model_dump(mode="json")

    harness = EpisodeReplayHarness.from_settings(settings=settings, episode_exporter=exporter)
    agent_os_replay = harness.replay_episode(
        PlannerReplayRequest(
            episode_id=episode["episode_id"],
            planner_id="agent_os_current",
            planner_profile="default",
            replay_mode=PlannerReplayMode.STRICT,
            comparison_mode=BenchmarkComparisonMode.EPISODE_VS_REPLAY,
        )
    )
    baseline_replay = harness.replay_episode(
        PlannerReplayRequest(
            episode_id=episode["episode_id"],
            planner_id="deterministic_baseline",
            planner_profile="default",
            replay_mode=PlannerReplayMode.STRICT,
            comparison_mode=BenchmarkComparisonMode.EPISODE_VS_REPLAY,
        )
    )

    assert agent_os_replay.step_count == original.trace_count
    assert agent_os_replay.strict_replay_policy_version == "blink_strict_replay/v2"
    assert Path(agent_os_replay.artifact_files["replay"]).exists()
    assert Path(agent_os_replay.artifact_files["steps"]).exists()
    assert Path(agent_os_replay.artifact_files["divergence_summary"]).exists()
    assert agent_os_replay.environment_fingerprint["planner_id"] == "agent_os_current"
    assert baseline_replay.planner_id == "deterministic_baseline"
    assert baseline_replay.artifact_dir != original.artifact_dir

    reloaded = exporter.get_episode(episode["episode_id"])
    assert reloaded is not None
    assert reloaded.model_dump(mode="json") == original_payload

    runner = BenchmarkRunner.from_settings(settings=settings, episode_exporter=exporter)
    benchmark = runner.run(
        request=BenchmarkRunRequest(
            episode_id=episode["episode_id"],
            planner_id="agent_os_current",
            planner_profile="default",
            comparison_planners=["deterministic_baseline"],
            comparison_mode=BenchmarkComparisonMode.EPISODE_VS_REPLAY,
            replay_mode=PlannerReplayMode.STRICT,
            families=[
                BenchmarkFamily.EPISODE_EXPORT_VALIDITY,
                BenchmarkFamily.REPLAY_DETERMINISM,
                BenchmarkFamily.PLANNER_COMPARISON_QUALITY,
            ],
        )
    )

    assert benchmark.replay_id
    assert benchmark.artifact_files["research_manifest"]
    assert benchmark.evidence_pack_id
    assert benchmark.evidence_pack_manifest
    assert benchmark.planner_comparison_summary
    assert any(item.family == BenchmarkFamily.EXPORT_DATASET_HYGIENE for item in benchmark.results)
    assert any(item.family == BenchmarkFamily.PLANNER_COMPARISON_QUALITY for item in benchmark.results)

    evidence_list = brain_client.get("/api/operator/benchmarks/evidence")
    assert evidence_list.status_code == 200
    assert any(item["pack_id"] == benchmark.evidence_pack_id for item in evidence_list.json()["items"])

    evidence_detail = brain_client.get(f"/api/operator/benchmarks/evidence/{benchmark.evidence_pack_id}")
    assert evidence_detail.status_code == 200
    payload = evidence_detail.json()
    assert payload["benchmark_run_id"] == benchmark.run_id
    assert Path(payload["artifact_files"]["manifest"]).exists()
