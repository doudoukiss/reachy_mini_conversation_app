from __future__ import annotations

import json
from pathlib import Path

import pytest

from embodied_stack.brain.app import create_app as create_brain_app
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.body.expressive_motifs import resolve_expressive_motif
from embodied_stack.body.semantics import lookup_action_descriptor
from embodied_stack.config import Settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.demo.performance_show import (
    ACTION_INTENSITY_LIMITS,
    LIVE_SAFE_ACTIONS,
    PerformanceReportStore,
    PerformanceShowRunner,
    SHOW_DEFINITION_PATHS,
    _normalized_motion_outcome,
    _margin_thresholds_for_action,
    benchmark_show_narration,
    load_show_definition,
    select_show_definition,
    validate_show_definition,
)
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway
from embodied_stack.shared.models import (
    BodyActionResult,
    BodyExpressiveSequenceRequest,
    BodyStagedSequenceRequest,
    BodyDriverMode,
    CompanionContextMode,
    DemoRunStatus,
    ExpressiveMotifReference,
    ExpressiveSequenceStep,
    PerformanceCue,
    PerformanceCueKind,
    PerformanceMotionBeat,
    PerformanceMotionOutcome,
    PrimitiveSequenceStep,
    PerformanceProofBackendMode,
    PerformanceRunRequest,
    PerformanceRunResult,
    PerformanceSegment,
    PerformanceShowDefinition,
    RobotMode,
    StagedSequenceAccent,
    StagedSequenceStage,
    VoiceRuntimeMode,
)


def _build_operator_console(tmp_path: Path, **overrides):
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        episode_export_dir=str(tmp_path / "episodes"),
        perception_frame_dir=str(tmp_path / "perception_frames"),
        performance_report_dir=str(tmp_path / "performance_runs"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        shift_background_tick_enabled=False,
        operator_auth_token="test-operator-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_context_mode=CompanionContextMode.VENUE_DEMO,
        ollama_base_url="http://127.0.0.1:9",
        ollama_timeout_seconds=0.1,
        **overrides,
    )
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)
    coordinator = DemoCoordinator(
        orchestrator=orchestrator,
        edge_gateway=build_inprocess_embodiment_gateway(settings),
        report_dir=settings.demo_report_dir,
    )
    app = create_brain_app(settings=settings, orchestrator=orchestrator, demo_coordinator=coordinator)
    return app.state.operator_console, settings


def _build_grounded_runtime_smoke_definition() -> PerformanceShowDefinition:
    return PerformanceShowDefinition(
        show_name="grounded_runtime_smoke",
        title="Grounded Runtime Smoke",
        version="v1",
        session_id="grounded-runtime-smoke",
        defaults={"proof_backend_mode": "deterministic_show"},
        segments=[
            PerformanceSegment(
                segment_id="grounded_perception",
                title="Grounded perception",
                investor_claim="Grounded proof cues should support deterministic fallback handling.",
                target_duration_seconds=15,
                cues=[
                    PerformanceCue(
                        cue_id="grounded_caption",
                        cue_kind=PerformanceCueKind.CAPTION,
                        text="Grounded perception",
                    ),
                    PerformanceCue(
                        cue_id="grounded_prompt",
                        cue_kind=PerformanceCueKind.PROMPT,
                        text="Ground the next cue in a deterministic scene.",
                    ),
                    PerformanceCue(
                        cue_id="grounded_scene",
                        cue_kind=PerformanceCueKind.RUN_SCENE,
                        scene_name="attentive_listening",
                        fallback_text="Fallback grounded scene narration.",
                    ),
                    PerformanceCue(
                        cue_id="grounded_pause",
                        cue_kind=PerformanceCueKind.PAUSE,
                        target_duration_ms=250,
                    ),
                ],
            ),
            PerformanceSegment(
                segment_id="arrival",
                title="Arrival",
                investor_claim="Narration behavior should still support localization and preview-safe motion tracks.",
                target_duration_seconds=15,
                cues=[
                    PerformanceCue(
                        cue_id="arrival_caption",
                        cue_kind=PerformanceCueKind.CAPTION,
                        text="Arrival",
                    ),
                    PerformanceCue(
                        cue_id="arrival_line_1",
                        cue_kind=PerformanceCueKind.NARRATE,
                        text="I am Blink.",
                        localized_text={"zh-cn": "我是 Blink。"},
                        motion_track=[
                            PerformanceMotionBeat(offset_ms=0, action="look_forward", intensity=1.0),
                            PerformanceMotionBeat(offset_ms=300, action="friendly", intensity=1.0),
                        ],
                    ),
                    PerformanceCue(
                        cue_id="arrival_pause",
                        cue_kind=PerformanceCueKind.PAUSE,
                        target_duration_ms=250,
                    ),
                ],
            ),
        ],
    )


def _build_primitive_sequence_smoke_definition() -> PerformanceShowDefinition:
    return PerformanceShowDefinition(
        show_name="primitive_sequence_smoke",
        title="Primitive Sequence Smoke",
        version="v1",
        session_id="primitive-sequence-smoke",
        defaults={"proof_backend_mode": "deterministic_show"},
        segments=[
            PerformanceSegment(
                segment_id="sequence_segment",
                title="Sequence segment",
                investor_claim="Primitive sequences should route through one gateway call.",
                target_duration_seconds=5,
                cues=[
                    PerformanceCue(
                        cue_id="sequence_caption",
                        cue_kind=PerformanceCueKind.CAPTION,
                        text="Primitive sequence smoke",
                    ),
                    PerformanceCue(
                        cue_id="sequence_run",
                        cue_kind=PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE,
                        primitive_sequence=[
                            PrimitiveSequenceStep(action="neutral_settle_slow", intensity=1.0),
                            PrimitiveSequenceStep(action="head_turn_left_slow", intensity=1.0),
                            PrimitiveSequenceStep(action="blink_both_slow", intensity=1.0),
                            PrimitiveSequenceStep(action="brows_raise_both_slow", intensity=1.0),
                        ],
                    ),
                    PerformanceCue(
                        cue_id="sequence_pause",
                        cue_kind=PerformanceCueKind.PAUSE,
                        target_duration_ms=250,
                    ),
                ],
            ),
        ],
    )


def test_maintained_investor_show_surface_exposes_v3_through_v8_only() -> None:
    available = set(SHOW_DEFINITION_PATHS)

    assert "investor_expressive_motion_v8" in available
    assert "investor_head_motion_v3" in available
    assert "investor_eye_motion_v4" in available
    assert "investor_lid_motion_v5" in available
    assert "investor_brow_motion_v6" in available
    assert "investor_neck_motion_v7" in available
    assert "investor_ten_minute_v1" not in available
    assert "investor_ten_minute_v2" not in available


def test_v8_asset_loads_and_uses_catalog_backed_expressive_motifs() -> None:
    definition = load_show_definition("investor_expressive_motion_v8")

    assert sum(segment.target_duration_seconds for segment in definition.segments) == 216
    assert definition.show_name == "investor_expressive_motion_v8"
    assert definition.session_id == "investor-expressive-motion-v8"
    assert definition.defaults.proof_backend_mode == PerformanceProofBackendMode.DETERMINISTIC_SHOW
    assert all(
        cue.cue_kind in {PerformanceCueKind.CAPTION, PerformanceCueKind.BODY_EXPRESSIVE_MOTIF, PerformanceCueKind.PAUSE}
        for segment in definition.segments
        for cue in segment.cues
    )
    body_cues = [
        cue
        for segment in definition.segments
        for cue in segment.cues
        if cue.cue_kind == PerformanceCueKind.BODY_EXPRESSIVE_MOTIF
    ]
    assert len(body_cues) == 12
    for cue in body_cues:
        assert cue.expressive_motif is not None
        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
        assert motif is not None
        for step in motif.steps:
            if step.action_name is None:
                continue
            descriptor = lookup_action_descriptor(step.action_name)
            assert descriptor is not None
            assert step.action_name in LIVE_SAFE_ACTIONS
            if step.intensity is not None:
                assert step.intensity <= ACTION_INTENSITY_LIMITS[step.action_name]


def test_body_primitive_sequence_cue_validates_and_requires_steps() -> None:
    cue = PerformanceCue(
        cue_id="sequence",
        cue_kind=PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE,
        primitive_sequence=[{"action": "head_turn_left_slow", "intensity": 1.0}],
    )

    assert cue.primitive_sequence[0].action == "head_turn_left_slow"

    with pytest.raises(ValueError, match="body_primitive_sequence_cue_requires_steps"):
        PerformanceCue(
            cue_id="invalid_sequence",
            cue_kind=PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE,
        )


def test_validate_show_definition_accepts_custom_primitive_sequence_show() -> None:
    definition = _build_primitive_sequence_smoke_definition()

    validate_show_definition(definition)


def test_servo_range_showcase_asset_loads_as_short_body_first_demo() -> None:
    definition = load_show_definition("robot_head_servo_range_showcase_v1")

    total_duration_seconds = sum(segment.target_duration_seconds for segment in definition.segments)
    assert definition.show_name == "robot_head_servo_range_showcase_v1"
    assert total_duration_seconds == 115
    assert len(definition.segments) == 1
    cue = next(
        item
        for item in definition.segments[0].cues
        if item.cue_kind == PerformanceCueKind.BODY_RANGE_DEMO
    )
    assert cue.cue_kind == PerformanceCueKind.BODY_RANGE_DEMO
    assert cue.payload["sequence_name"] == "servo_range_showcase_v1"
    assert cue.payload["preset_name"] == "servo_range_showcase_joint_envelope_v1"


def test_investor_head_motion_v3_asset_loads_as_atomic_head_yaw_proof() -> None:
    definition = load_show_definition("investor_head_motion_v3")

    total_duration_seconds = sum(segment.target_duration_seconds for segment in definition.segments)
    assert definition.show_name == "investor_head_motion_v3"
    assert definition.session_id == "investor-head-motion-v3"
    assert total_duration_seconds == 48
    assert len(definition.segments) == 1
    cues = definition.segments[0].cues
    assert [cue.cue_kind for cue in cues] == [
        PerformanceCueKind.CAPTION,
        PerformanceCueKind.BODY_RANGE_DEMO,
        PerformanceCueKind.PAUSE,
    ]
    body_cue = cues[1]
    assert body_cue.payload["sequence_name"] == "investor_head_yaw_v3"
    assert body_cue.payload["preset_name"] == "servo_range_showcase_joint_envelope_v1"
    assert all(not cue.motion_track for cue in cues)
    assert all(cue.cue_kind != PerformanceCueKind.BODY_SEMANTIC_SMOKE for cue in cues)


@pytest.mark.parametrize(
    ("show_name", "session_id", "expected_sequence_names"),
    [
        ("investor_eye_motion_v4", "investor-eye-motion-v4", ["investor_eye_yaw_v4", "investor_eye_pitch_v4"]),
        (
            "investor_lid_motion_v5",
            "investor-lid-motion-v5",
            [
                "investor_both_lids_v5",
                "investor_left_eye_lids_v5",
                "investor_right_eye_lids_v5",
                "investor_blink_v5",
            ],
        ),
        (
            "investor_brow_motion_v6",
            "investor-brow-motion-v6",
            [
                "investor_brows_both_v6",
                "investor_brow_left_v6",
                "investor_brow_right_v6",
            ],
        ),
        (
            "investor_neck_motion_v7",
            "investor-neck-motion-v7",
            ["investor_neck_tilt_v7", "investor_neck_pitch_v7"],
        ),
    ],
)
def test_post_v3_family_show_assets_load_as_atomic_range_demo_series(
    show_name: str,
    session_id: str,
    expected_sequence_names: list[str],
) -> None:
    definition = load_show_definition(show_name)

    assert definition.show_name == show_name
    assert definition.session_id == session_id
    assert len(definition.segments) == len(expected_sequence_names)
    body_cues = []
    for segment in definition.segments:
        cues = segment.cues
        assert [cue.cue_kind for cue in cues] == [
            PerformanceCueKind.CAPTION,
            PerformanceCueKind.BODY_RANGE_DEMO,
            PerformanceCueKind.PAUSE,
        ]
        assert all(not cue.motion_track for cue in cues)
        assert all(cue.cue_kind != PerformanceCueKind.BODY_SEMANTIC_SMOKE for cue in cues)
        body_cues.append(cues[1])

    assert [cue.payload["sequence_name"] for cue in body_cues] == expected_sequence_names

    for cue in body_cues:
        if cue.payload["sequence_name"] in {
            "investor_both_lids_v5",
            "investor_left_eye_lids_v5",
            "investor_right_eye_lids_v5",
            "investor_blink_v5",
            "investor_brows_both_v6",
            "investor_brow_left_v6",
            "investor_brow_right_v6",
        }:
            assert cue.payload["preset_name"] == "investor_show_joint_envelope_v1"
        elif cue.payload["sequence_name"] in {
            "investor_neck_tilt_v7",
            "investor_neck_pitch_v7",
        }:
            assert cue.payload["preset_name"] == "investor_neck_protective_joint_envelope_v1"
        else:
            assert cue.payload["preset_name"] == "servo_range_showcase_joint_envelope_v1"


def test_investor_expressive_motion_v8_asset_loads_as_motif_atomic_series() -> None:
    definition = load_show_definition("investor_expressive_motion_v8")

    assert definition.show_name == "investor_expressive_motion_v8"
    assert definition.session_id == "investor-expressive-motion-v8"
    assert sum(segment.target_duration_seconds for segment in definition.segments) == 216
    assert len(definition.segments) == 12

    expected_motifs = {
        "attentive_notice_right_run": "attentive_notice_right",
        "attentive_notice_left_run": "attentive_notice_left",
        "guarded_close_right_run": "guarded_close_right",
        "guarded_close_left_run": "guarded_close_left",
        "curious_lift_run": "curious_lift",
        "reflective_lower_run": "reflective_lower",
        "skeptical_tilt_right_run": "skeptical_tilt_right",
        "empathetic_tilt_left_run": "empathetic_tilt_left",
        "playful_peek_right_run": "playful_peek_right",
        "playful_peek_left_run": "playful_peek_left",
        "bright_reengage_run": "bright_reengage",
        "doubtful_side_glance_run": "doubtful_side_glance",
    }

    body_cues = []
    for segment in definition.segments:
        cues = segment.cues
        assert [cue.cue_kind for cue in cues] == [
            PerformanceCueKind.CAPTION,
            PerformanceCueKind.BODY_EXPRESSIVE_MOTIF,
            PerformanceCueKind.PAUSE,
        ]
        assert all(not cue.motion_track for cue in cues)
        assert all(cue.text is None for cue in cues if cue.cue_kind != PerformanceCueKind.CAPTION)
        assert segment.target_duration_seconds == 18
        assert cues[2].target_duration_ms == 5500
        body_cues.append(cues[1])

    for cue in body_cues:
        assert cue.expressive_motif is not None
        assert cue.expressive_motif.motif_name == expected_motifs[cue.cue_id]
        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
        assert motif is not None
        assert motif.steps[0].step_kind == "structural_set"
        assert motif.steps[-1].step_kind == "return_to_neutral"
        assert motif.steps[0].action_name is not None
        assert not motif.steps[0].action_name.endswith("_fast")
        assert all(
            step.action_name is None or not step.action_name.endswith("_fast")
            for step in motif.steps
        )
        assert all(step.step_kind != "return_to_neutral" for step in motif.steps[:-1])
        assert any(step.step_kind == "expressive_set" for step in motif.steps)


def test_body_staged_sequence_request_validates_stage_order_and_allowed_families() -> None:
    request = BodyStagedSequenceRequest(
        sequence_name="v8_test",
        stages=[
            StagedSequenceStage(stage_kind="structural", action="head_turn_right_slow", intensity=0.8),
            StagedSequenceStage(
                stage_kind="expressive",
                accents=[StagedSequenceAccent(action="eyes_right_slow", intensity=0.8)],
            ),
            StagedSequenceStage(stage_kind="return", move_ms=1800, hold_ms=1200),
        ],
    )

    assert [stage.stage_kind for stage in request.stages] == ["structural", "expressive", "return"]

    with pytest.raises(ValueError, match="staged_sequence_structural_action_not_allowed:eyes_right_slow"):
        BodyStagedSequenceRequest(
            stages=[
                StagedSequenceStage(stage_kind="structural", action="eyes_right_slow", intensity=0.8),
                StagedSequenceStage(
                    stage_kind="expressive",
                    accents=[StagedSequenceAccent(action="eyes_right_slow", intensity=0.8)],
                ),
                StagedSequenceStage(stage_kind="return", move_ms=1800, hold_ms=1200),
            ]
        )


def test_body_expressive_motif_request_validates_step_order_and_allowed_families() -> None:
    request = BodyExpressiveSequenceRequest(
        motif=ExpressiveMotifReference(motif_name="guarded_close_right"),
        sequence_name="guarded_close_right_run",
    )

    assert request.motif is not None
    assert request.motif.motif_name == "guarded_close_right"

    manual = BodyExpressiveSequenceRequest(
        steps=[
            ExpressiveSequenceStep(step_kind="structural_set", action="head_turn_right_slow", intensity=1.0),
            ExpressiveSequenceStep(step_kind="expressive_set", action="close_both_eyes_slow", intensity=1.0),
            ExpressiveSequenceStep(step_kind="expressive_release", release_groups=["lids"], move_ms=900, hold_ms=300),
            ExpressiveSequenceStep(step_kind="return_to_neutral", move_ms=2200, hold_ms=0),
        ],
        sequence_name="manual_guarded_close_right",
    )

    assert [step.step_kind for step in manual.steps] == [
        "structural_set",
        "expressive_set",
        "expressive_release",
        "return_to_neutral",
    ]

    with pytest.raises(ValueError, match="expressive_sequence_structural_action_not_allowed:eyes_right_slow"):
        BodyExpressiveSequenceRequest(
            steps=[
                ExpressiveSequenceStep(step_kind="structural_set", action="eyes_right_slow", intensity=1.0),
                ExpressiveSequenceStep(step_kind="return_to_neutral", move_ms=2200, hold_ms=0),
            ]
        )

def test_servo_range_showcase_uses_zero_margin_thresholds_for_hard_limit_sweep() -> None:
    thresholds = _margin_thresholds_for_action(
        action="body_range_demo:servo_range_showcase_v1",
        narration_linked=False,
    )

    assert all(value == 0.0 for value in thresholds.values())


def test_guarded_close_right_motif_preserves_hold_and_release_order() -> None:
    motif = resolve_expressive_motif("guarded_close_right")

    assert motif is not None
    assert [step.step_kind for step in motif.steps] == [
        "structural_set",
        "expressive_set",
        "expressive_set",
        "expressive_release",
        "expressive_release",
        "return_to_neutral",
    ]
    assert [step.action_name for step in motif.steps[:3]] == [
        "head_turn_right_slow",
        "close_both_eyes_slow",
        "brows_lower_both_slow",
    ]


def test_performance_runner_warns_but_allows_live_investor_body_start_when_idle_power_preflight_fails(
    tmp_path: Path, monkeypatch
) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )
    definition = load_show_definition("investor_expressive_motion_v8")
    request = PerformanceRunRequest(
        cue_ids=["guarded_close_right_run"],
        narration_enabled=False,
        background=False,
    )
    calls: list[str] = []

    monkeypatch.setattr(
        runner,
        "_body_state_payload",
        lambda force_refresh=False: {
            "transport_mode": "live_serial",
            "transport_confirmed_live": True,
        },
    )
    monkeypatch.setattr(
        operator_console,
        "run_body_power_preflight",
        lambda: BodyActionResult(
            ok=False,
            status="blocked",
            detail="unhealthy_idle_low_voltage:head_yaw,eye_yaw",
            payload={
                "power_health_classification": "unhealthy_idle",
                "preflight_passed": False,
                "preflight_failure_reason": "unhealthy_idle_low_voltage:head_yaw,eye_yaw",
                "idle_voltage_snapshot": {
                    "head_yaw": {"voltage_raw": 35, "error_bits": ["input_voltage"]},
                    "eye_yaw": {"voltage_raw": 36, "error_bits": ["input_voltage"]},
                },
            },
        ),
    )

    def _expressive_motif(*args, **kwargs):
        calls.append("run_body_expressive_motif")
        return BodyActionResult(
            ok=True,
            status="ok",
            payload={
                "latest_command_audit": {
                    "outcome_status": "sent",
                    "reason_code": "ok",
                    "transport_mode": "live_serial",
                    "transport_status": {"mode": "live_serial", "confirmed_live": True},
                    "compiled_targets": {"head_yaw": 2100},
                    "before_readback": {"head_yaw": 2047},
                    "after_readback": {"head_yaw": 2100},
                    "preflight_passed": False,
                    "preflight_failure_reason": "unhealthy_idle_low_voltage:head_yaw,eye_yaw",
                    "power_health_classification": "unhealthy_idle",
                }
            },
        )

    monkeypatch.setattr(operator_console, "run_body_expressive_motif", _expressive_motif)

    run = runner.run(definition, request=request, run_id="preflight-warning")

    assert run.preflight_passed is False
    assert run.power_health_classification == "unhealthy_idle"
    assert run.preview_only is False
    assert calls == ["run_body_expressive_motif"]
    assert any(note.startswith("body_preflight_warning:") for note in run.notes)
    cue_result = next(
        cue
        for segment in run.segment_results
        for cue in segment.cue_results
        if cue.cue_id == "guarded_close_right_run"
    )
    assert cue_result.motion_outcome == PerformanceMotionOutcome.LIVE_APPLIED
    assert cue_result.motion_margin_record is not None
    assert cue_result.motion_margin_record.preflight_passed is False
    assert cue_result.motion_margin_record.preflight_failure_reason == "unhealthy_idle_low_voltage:head_yaw,eye_yaw"


def test_performance_runner_writes_preshow_neutral_before_first_live_show_cue(
    tmp_path: Path, monkeypatch
) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )
    definition = load_show_definition("investor_expressive_motion_v8")
    request = PerformanceRunRequest(
        cue_ids=["guarded_close_right_run"],
        narration_enabled=False,
        background=False,
    )
    calls: list[str] = []

    monkeypatch.setattr("embodied_stack.demo.performance_show.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        runner,
        "_body_state_payload",
        lambda force_refresh=False: {
            "transport_mode": "live_serial",
            "transport_confirmed_live": True,
        },
    )

    def _preflight():
        calls.append("preflight")
        return BodyActionResult(
            ok=True,
            status="ok",
            payload={
                "power_health_classification": "healthy",
                "preflight_passed": True,
                "preflight_failure_reason": None,
                "idle_voltage_snapshot": {},
            },
        )

    def _neutral():
        calls.append("neutral")
        return BodyActionResult(
            ok=True,
            status="ok",
            detail=None,
        )

    def _expressive_motif(*args, **kwargs):
        calls.append("run_body_expressive_motif")
        return BodyActionResult(
            ok=True,
            status="ok",
            payload={
                "latest_command_audit": {
                    "outcome_status": "sent",
                    "reason_code": "ok",
                    "transport_mode": "live_serial",
                    "transport_status": {"mode": "live_serial", "confirmed_live": True},
                    "compiled_targets": {"head_yaw": 2100},
                    "before_readback": {"head_yaw": 2047},
                    "after_readback": {"head_yaw": 2100},
                    "preflight_passed": True,
                    "power_health_classification": "healthy",
                }
            },
        )

    monkeypatch.setattr(operator_console, "run_body_power_preflight", _preflight)
    monkeypatch.setattr(operator_console, "write_body_neutral", _neutral)
    monkeypatch.setattr(operator_console, "run_body_expressive_motif", _expressive_motif)

    run = runner.run(definition, request=request, run_id="preshow-neutral")

    assert calls == ["preflight", "neutral", "run_body_expressive_motif"]
    assert "body_preshow_neutral:ok" in run.notes
    cue_result = next(
        cue
        for segment in run.segment_results
        for cue in segment.cue_results
        if cue.cue_id == "guarded_close_right_run"
    )
    assert cue_result.motion_outcome == PerformanceMotionOutcome.LIVE_APPLIED


def test_performance_runner_routes_custom_body_primitive_sequence_through_single_gateway_call(
    tmp_path: Path, monkeypatch
) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )
    definition = _build_primitive_sequence_smoke_definition()
    request = PerformanceRunRequest(
        cue_ids=["sequence_run"],
        narration_enabled=False,
        background=False,
    )
    calls: list[list[str]] = []

    monkeypatch.setattr("embodied_stack.demo.performance_show.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        runner,
        "_body_state_payload",
        lambda force_refresh=False: {
            "transport_mode": "live_serial",
            "transport_confirmed_live": True,
        },
    )
    monkeypatch.setattr(
        operator_console,
        "run_body_power_preflight",
        lambda: BodyActionResult(
            ok=True,
            status="ok",
            payload={
                "power_health_classification": "healthy",
                "preflight_passed": True,
                "preflight_failure_reason": None,
                "idle_voltage_snapshot": {},
            },
        ),
    )
    monkeypatch.setattr(
        operator_console,
        "write_body_neutral",
        lambda: BodyActionResult(ok=True, status="ok", detail=None),
    )

    def _primitive_sequence(request):
        calls.append([step.action for step in request.steps])
        return BodyActionResult(
            ok=True,
            status="ok",
            payload={
                "payload": {
                    "sequence_name": request.sequence_name,
                    "primitive_steps": [step.action for step in request.steps],
                    "sequence_step_count": len(request.steps),
                    "returned_to_neutral": True,
                    "preview_only": False,
                    "live_requested": True,
                },
                "latest_command_audit": {
                    "outcome_status": "sent",
                    "reason_code": "ok",
                    "transport_mode": "live_serial",
                    "transport_status": {"mode": "live_serial", "confirmed_live": True},
                    "compiled_targets": {"head_yaw": 2100},
                    "before_readback": {"head_yaw": 2047},
                    "after_readback": {"head_yaw": 2100},
                    "sequence_step_count": len(request.steps),
                    "primitive_steps": [step.action for step in request.steps],
                    "returned_to_neutral": True,
                    "grounding": "primitive_sequence",
                    "preflight_passed": True,
                    "power_health_classification": "healthy",
                },
            },
        )

    monkeypatch.setattr(operator_console, "run_body_primitive_sequence", _primitive_sequence)
    monkeypatch.setattr(
        operator_console,
        "run_body_semantic_smoke",
        lambda *_args, **_kwargs: pytest.fail("primitive_sequence_should_not_use_body_semantic_smoke"),
    )

    run = runner.run(definition, request=request, run_id="primitive-sequence")

    assert calls == [["neutral_settle_slow", "head_turn_left_slow", "blink_both_slow", "brows_raise_both_slow"]]
    cue_result = run.segment_results[0].cue_results[0]
    assert cue_result.motion_outcome == PerformanceMotionOutcome.LIVE_APPLIED
    assert cue_result.payload["sequence_step_count"] == 4
    assert cue_result.payload["returned_to_neutral"] is True


def test_performance_runner_runs_body_expressive_motif_in_single_call(
    tmp_path: Path, monkeypatch
) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )
    definition = load_show_definition("investor_expressive_motion_v8")
    request = PerformanceRunRequest(
        cue_ids=["guarded_close_right_run"],
        narration_enabled=False,
        background=False,
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        runner,
        "_body_state_payload",
        lambda force_refresh=False: {
            "transport_mode": "live_serial",
            "transport_confirmed_live": True,
        },
    )
    monkeypatch.setattr(
        operator_console,
        "write_body_neutral",
        lambda: BodyActionResult(ok=True, status="ok", detail=None),
    )

    def _expressive_motif(request: BodyExpressiveSequenceRequest):
        calls.append(
            {
                "sequence_name": request.sequence_name,
                "motif_name": request.motif.motif_name if request.motif is not None else None,
            }
        )
        motif = resolve_expressive_motif(request.motif.motif_name if request.motif is not None else "")
        assert motif is not None
        return BodyActionResult(
            ok=True,
            status="ok",
            payload={
                "payload": {
                    "sequence_name": request.sequence_name,
                    "motif_name": request.motif.motif_name if request.motif is not None else None,
                    "structural_action": motif.steps[0].action_name,
                    "expressive_steps": [
                        step.action_name
                        for step in motif.steps
                        if step.action_name is not None and step.step_kind == "expressive_set"
                    ],
                    "step_kinds": [step.step_kind for step in motif.steps],
                    "sequence_step_count": len(motif.steps),
                    "returned_to_neutral": True,
                    "preview_only": False,
                    "live_requested": True,
                },
                "latest_command_audit": {
                    "outcome_status": "sent",
                    "reason_code": "ok",
                    "transport_mode": "live_serial",
                    "transport_status": {"mode": "live_serial", "confirmed_live": True},
                    "compiled_targets": {"head_yaw": 2100, "eye_yaw": 2070},
                    "before_readback": {"head_yaw": 2047},
                    "after_readback": {"head_yaw": 2100},
                    "grounding": "expressive_motif",
                    "motif_name": request.motif.motif_name if request.motif is not None else None,
                    "structural_action": motif.steps[0].action_name,
                    "expressive_steps": [
                        step.action_name
                        for step in motif.steps
                        if step.action_name is not None and step.step_kind == "expressive_set"
                    ],
                    "step_kinds": [step.step_kind for step in motif.steps],
                    "sequence_step_count": len(motif.steps),
                    "returned_to_neutral": True,
                },
            },
        )

    monkeypatch.setattr(operator_console, "run_body_expressive_motif", _expressive_motif)

    run = runner.run(definition, request=request, run_id="v8-expressive-motif")

    assert calls == [
        {
            "sequence_name": "guarded_close_right_run",
            "motif_name": "guarded_close_right",
        }
    ]
    cue_result = run.segment_results[0].cue_results[0]
    assert cue_result.motion_outcome == PerformanceMotionOutcome.LIVE_APPLIED
    assert cue_result.payload["structural_action"] == "head_turn_right_slow"
    assert cue_result.payload["motif_name"] == "guarded_close_right"
    assert cue_result.payload["sequence_step_count"] == 6
    assert cue_result.payload["returned_to_neutral"] is True


def test_normalized_motion_outcome_keeps_executed_live_write_live_when_transport_state_drops_afterward() -> None:
    outcome = _normalized_motion_outcome(
        audit={
            "outcome_status": "sent_with_readback_warning",
            "reason_code": "timeout",
            "executed_frame_count": 4,
            "compiled_targets": {"head_yaw": 2130},
            "transport_mode": "live_serial",
            "transport_status": {"mode": "live_serial", "confirmed_live": False},
        },
        body_state={
            "transport_mode": "live_serial",
            "transport_confirmed_live": False,
        },
    )

    assert outcome == PerformanceMotionOutcome.LIVE_APPLIED


def test_performance_runner_continues_motion_after_confirmed_power_fault(tmp_path: Path, monkeypatch) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )
    run = PerformanceRunResult(
        run_id="test-run",
        show_name="investor_expressive_motion_v8",
        session_id="investor-expressive-motion-v8",
    )

    class _FakeStatus:
        value = "speaking"

    class _FakeRuntime:
        def get_state(self, _session_id: str):
            return type("_State", (), {"status": _FakeStatus()})()

    calls: list[str] = []

    def _fake_run_body_motion_beat(beat, narration_linked=False):
        calls.append(beat.action)
        if len(calls) == 1:
            return {
                "action": beat.action,
                "success": True,
                "status": "ok",
                "detail": None,
                "preview_only": False,
                "body_projection_outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
                "motion_outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
                "motion_margin_record": {
                    "action": beat.action,
                    "outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
                    "safety_gate_passed": False,
                    "peak_calibrated_target": {},
                    "latest_readback": {},
                    "min_remaining_margin_percent_by_joint": {},
                    "min_remaining_margin_percent_by_group": {},
                    "max_remaining_margin_percent_by_group": {},
                    "threshold_percent_by_group": {},
                    "health_flags": ["confirmed_power_fault"],
                    "error_joints": [],
                    "abnormal_load_joints": [],
                    "fault_classification": "confirmed_power_fault",
                    "suspect_voltage_event": True,
                    "readback_implausible": True,
                    "confirmation_read_performed": True,
                    "confirmation_result": "confirmed_repeated_voltage_and_divergence",
                    "transport_mode": "live_serial",
                    "transport_confirmed_live": True,
                    "live_readback_checked": True,
                },
                "actuator_coverage": {"head_yaw": True},
                "degraded": True,
                "raw_result": {},
            }
        return {
            "action": beat.action,
            "success": True,
            "status": "ok",
            "detail": None,
            "preview_only": False,
            "body_projection_outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
            "motion_outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
            "motion_margin_record": {
                "action": beat.action,
                "outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
                "safety_gate_passed": True,
                "peak_calibrated_target": {},
                "latest_readback": {},
                "min_remaining_margin_percent_by_joint": {},
                "min_remaining_margin_percent_by_group": {},
                "max_remaining_margin_percent_by_group": {},
                "threshold_percent_by_group": {},
                "health_flags": [],
                "error_joints": [],
                "abnormal_load_joints": [],
                "transport_mode": "live_serial",
                "transport_confirmed_live": True,
                "live_readback_checked": True,
            },
            "actuator_coverage": {"brows": True},
            "degraded": False,
            "raw_result": {},
        }

    monkeypatch.setattr(runner, "_run_body_motion_beat", _fake_run_body_motion_beat)

    results, _elapsed = runner._perform_motion_track(
        run=run,
        runtime=_FakeRuntime(),
        motion_track=[
            PerformanceMotionBeat(offset_ms=0, action="look_forward"),
            PerformanceMotionBeat(offset_ms=120, action="double_blink", coverage_tags=["upper_lids", "lower_lids"]),
        ],
    )

    assert calls == ["look_forward", "double_blink"]
    assert run.body_fault_latched_preview_only is False
    assert run.body_fault_trigger_cue_id == "look_forward"
    assert results[1]["preview_only"] is False
    assert results[1]["motion_outcome"] == PerformanceMotionOutcome.LIVE_APPLIED.value
    assert results[0]["motion_margin_record"]["fault_classification"] == "confirmed_power_fault"


def test_performance_runner_continues_motion_after_suspicious_settle_check(tmp_path: Path, monkeypatch) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )
    run = PerformanceRunResult(
        run_id="test-run",
        show_name="investor_expressive_motion_v8",
        session_id="investor-expressive-motion-v8",
        pending_body_settle_reason=PerformanceCueKind.BODY_SAFE_IDLE.value,
    )

    class _FakeStatus:
        value = "speaking"

    class _FakeRuntime:
        def get_state(self, _session_id: str):
            return type("_State", (), {"status": _FakeStatus()})()

    calls: list[str] = []

    monkeypatch.setattr("embodied_stack.demo.performance_show.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        runner,
        "_body_state_payload",
        lambda force_refresh=False: {
            "transport_mode": "live_serial",
            "transport_confirmed_live": True,
            "latest_command_audit": {"fault_classification": "suspect_voltage_event"},
        },
    )

    def _body_motion(beat, narration_linked=False):
        calls.append(beat.action)
        return {
            "action": beat.action,
            "success": True,
            "status": "ok",
            "detail": None,
            "preview_only": False,
            "body_projection_outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
            "motion_outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
            "motion_margin_record": {
                "action": beat.action,
                "outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
                "safety_gate_passed": True,
                "peak_calibrated_target": {},
                "latest_readback": {},
                "min_remaining_margin_percent_by_joint": {},
                "min_remaining_margin_percent_by_group": {},
                "max_remaining_margin_percent_by_group": {},
                "threshold_percent_by_group": {},
                "health_flags": [],
                "error_joints": [],
                "abnormal_load_joints": [],
                "transport_mode": "live_serial",
                "transport_confirmed_live": True,
                "live_readback_checked": True,
            },
            "actuator_coverage": {"head_yaw": True},
            "degraded": False,
            "raw_result": {},
        }

    monkeypatch.setattr(runner, "_run_body_motion_beat", _body_motion)

    results, _elapsed = runner._perform_motion_track(
        run=run,
        runtime=_FakeRuntime(),
        motion_track=[PerformanceMotionBeat(offset_ms=0, action="look_forward")],
    )

    assert calls == ["look_forward"]
    assert results[0]["preview_only"] is False
    assert run.preview_only is False
    assert any(note.startswith("body_settle_warning:settle_check_suspect_voltage_event") for note in run.notes)


def test_performance_runner_body_range_demo_ignores_historical_fault_latch(tmp_path: Path, monkeypatch) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )
    run = PerformanceRunResult(
        run_id="test-run",
        show_name="robot_head_servo_range_showcase_v1",
        session_id="investor-show-main",
        body_fault_latched_preview_only=True,
        body_fault_trigger_cue_id="arrival_greeting",
        body_fault_detail="confirmed_low_voltage:all",
    )
    cue = PerformanceCue(
        cue_id="servo_range_showcase_run",
        cue_kind=PerformanceCueKind.BODY_RANGE_DEMO,
        payload={"sequence_name": "servo_range_showcase_v1", "preset_name": "servo_range_showcase_joint_envelope_v1"},
    )
    calls: list[str] = []

    monkeypatch.setattr(
        runner,
        "_run_body_range_demo_cue",
        lambda cue_arg: (
            calls.append(cue_arg.cue_id)
            or {
                "success": True,
                "status": "ok",
                "detail": None,
                "degraded": False,
                "sequence_name": "servo_range_showcase_v1",
                "preview_only": False,
                "live_requested": True,
                "preset_name": "servo_range_showcase_joint_envelope_v1",
                "range_demo": {},
                "blocked_reason": None,
                "body_projection_outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
                "motion_outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
                "motion_margin_record": {
                    "action": "body_range_demo:servo_range_showcase_v1",
                    "outcome": PerformanceMotionOutcome.LIVE_APPLIED.value,
                    "safety_gate_passed": True,
                    "peak_calibrated_target": {},
                    "latest_readback": {},
                    "min_remaining_margin_percent_by_joint": {},
                    "min_remaining_margin_percent_by_group": {},
                    "max_remaining_margin_percent_by_group": {},
                    "threshold_percent_by_group": {},
                    "health_flags": [],
                    "error_joints": [],
                    "abnormal_load_joints": [],
                    "transport_mode": "live_serial",
                    "transport_confirmed_live": True,
                    "live_readback_checked": True,
                },
                "actuator_coverage": {"head_yaw": True},
            }
        ),
    )

    payload = runner._run_cue(
        run=run,
        definition=load_show_definition("robot_head_servo_range_showcase_v1"),
        request=PerformanceRunRequest(background=False),
        segment=PerformanceSegment(
            segment_id="servo_range_showcase",
            title="Servo showcase",
            investor_claim="Servo range showcase",
        ),
        cue=cue,
    )

    assert calls == ["servo_range_showcase_run"]
    assert payload["motion_outcome"] == PerformanceMotionOutcome.LIVE_APPLIED.value


def test_select_show_definition_supports_segment_and_narration_filters() -> None:
    definition = _build_grounded_runtime_smoke_definition()

    filtered = select_show_definition(
        definition,
        PerformanceRunRequest(
            segment_ids=["grounded_perception"],
            narration_only=True,
            background=False,
        ),
    )

    assert [segment.segment_id for segment in filtered.segments] == ["grounded_perception"]
    assert {cue.cue_kind for cue in filtered.segments[0].cues} == {
        PerformanceCueKind.CAPTION,
        PerformanceCueKind.PROMPT,
        PerformanceCueKind.PAUSE,
    }


@pytest.mark.parametrize(
    ("runtime_mode", "body_driver"),
    [
        (RobotMode.DESKTOP_VIRTUAL_BODY, BodyDriverMode.VIRTUAL),
        (RobotMode.DESKTOP_BODYLESS, BodyDriverMode.BODYLESS),
    ],
)
def test_performance_runner_completes_in_ci_safe_modes(
    tmp_path: Path,
    runtime_mode: RobotMode,
    body_driver: BodyDriverMode,
) -> None:
    operator_console, _settings = _build_operator_console(
        tmp_path,
        blink_runtime_mode=runtime_mode,
        blink_body_driver=body_driver,
    )

    result = operator_console.run_performance_show(
        "investor_expressive_motion_v8",
        PerformanceRunRequest(background=False, narration_enabled=False),
    )

    assert result.status == DemoRunStatus.COMPLETED
    assert result.artifact_dir is not None
    assert result.episode_id is None
    assert Path(result.artifact_files["run_summary"]).exists()
    assert Path(result.artifact_files["proof_results"]).exists()

    proof_results = json.loads(Path(result.artifact_files["proof_results"]).read_text(encoding="utf-8"))
    assert proof_results == []


def test_performance_runner_uses_fallback_narration_when_proof_cue_degrades(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    definition = _build_grounded_runtime_smoke_definition().model_copy(deep=True)
    grounded_scene = next(
        cue
        for segment in definition.segments
        if segment.segment_id == "grounded_perception"
        for cue in segment.cues
        if cue.cue_id == "grounded_scene"
    )
    grounded_scene.expect_reply_contains.append("definitely_missing_signal")

    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )
    result = runner.run(
        definition,
        PerformanceRunRequest(background=False, narration_enabled=False),
    )

    grounded_segment = next(item for item in result.segment_results if item.segment_id == "grounded_perception")
    grounded_result = next(item for item in grounded_segment.cue_results if item.cue_id == "grounded_scene")

    assert result.status == DemoRunStatus.COMPLETED
    assert grounded_result.degraded is True
    assert grounded_result.fallback_used is True
    assert grounded_result.payload["fallback_narration"]["spoken_text"] == grounded_scene.fallback_text


def test_performance_runner_supports_forced_degraded_rehearsal(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    definition = _build_grounded_runtime_smoke_definition().model_copy(deep=True)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )

    result = runner.run(
        definition,
        PerformanceRunRequest(
            background=False,
            narration_enabled=False,
            force_degraded_cue_ids=["grounded_scene"],
        ),
    )

    grounded_segment = next(item for item in result.segment_results if item.segment_id == "grounded_perception")
    grounded_result = next(item for item in grounded_segment.cue_results if item.cue_id == "grounded_scene")
    assert result.status == DemoRunStatus.COMPLETED
    assert grounded_result.degraded is True
    assert grounded_result.fallback_used is True
    assert grounded_result.payload["forced_degraded_rehearsal"] is True


def test_performance_runner_supports_narration_via_live_voice_runtime(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    definition = _build_grounded_runtime_smoke_definition().model_copy(deep=True)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )

    result = runner.run(
        definition,
        PerformanceRunRequest(
            background=False,
            narration_enabled=True,
            narration_voice_mode=VoiceRuntimeMode.STUB_DEMO,
            segment_ids=["arrival"],
            cue_ids=["arrival_line_1"],
        ),
    )

    arrival_segment = next(item for item in result.segment_results if item.segment_id == "arrival")
    narration_result = next(item for item in arrival_segment.cue_results if item.cue_id == "arrival_line_1")
    assert result.status == DemoRunStatus.COMPLETED
    assert narration_result.degraded is False
    assert narration_result.payload["narration_enabled"] is True
    assert narration_result.payload["voice_output"]["status"] == "simulated"
    assert narration_result.motion_outcome == PerformanceMotionOutcome.PREVIEW_ONLY
    assert narration_result.motion_margin_record is not None
    assert narration_result.motion_margin_record.safety_gate_passed is True
    assert narration_result.actuator_coverage.head_yaw is True
    assert narration_result.actuator_coverage.brows is True


def test_performance_runner_resolves_localized_narration_text(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    definition = _build_grounded_runtime_smoke_definition().model_copy(deep=True)
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )

    result = runner.run(
        definition,
        PerformanceRunRequest(
            background=False,
            narration_enabled=True,
            narration_voice_mode=VoiceRuntimeMode.STUB_DEMO,
            language="zh-CN",
            segment_ids=["arrival"],
            cue_ids=["arrival_line_1"],
        ),
    )

    cue_result = result.segment_results[0].cue_results[0]
    assert cue_result.payload["language"] == "zh-CN"
    assert "我是 Blink" in cue_result.payload["spoken_text"]


def test_performance_runner_falls_back_to_english_when_localized_text_missing(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    definition = PerformanceShowDefinition(
        show_name="localization_fallback_smoke",
        title="Localization Fallback Smoke",
        version="v1",
        session_id="localization-fallback-session",
        defaults={
            "proof_backend_mode": "deterministic_show"
        },
        segments=[
            PerformanceSegment(
                segment_id="segment",
                title="Segment",
                investor_claim="Fallback should use English when a localized narration line is missing.",
                target_start_seconds=0,
                target_duration_seconds=10,
                cues=[
                    PerformanceCue(
                        cue_id="line",
                        cue_kind=PerformanceCueKind.NARRATE,
                        text="English fallback text.",
                        localized_text={"fr": "Texte francais."},
                    )
                ],
            )
        ],
    )
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )

    result = runner.run(
        definition,
        PerformanceRunRequest(
            background=False,
            narration_enabled=True,
            narration_voice_mode=VoiceRuntimeMode.STUB_DEMO,
            language="zh-CN",
        ),
    )

    cue_result = result.segment_results[0].cue_results[0]
    assert cue_result.payload["spoken_text"] == "English fallback text."


def test_custom_smoke_show_does_not_require_public_localized_narration_coverage(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    definition = _build_grounded_runtime_smoke_definition().model_copy(deep=True)
    definition.segments = [
        segment.model_copy(
            update={
                "cues": [
                    cue.model_copy(update={"localized_text": {}} if cue.cue_id == "arrival_line_1" else {}, deep=True)
                    for cue in segment.cues
                ]
            },
            deep=True,
        )
        for segment in definition.segments
    ]
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )

    result = runner.run(
        definition,
        PerformanceRunRequest(
            background=False,
            narration_enabled=True,
            narration_voice_mode=VoiceRuntimeMode.STUB_DEMO,
            language="zh-CN",
        ),
    )

    assert result.status == DemoRunStatus.COMPLETED


def test_benchmark_show_narration_reports_selected_voice_metadata(tmp_path: Path) -> None:
    operator_console, _settings = _build_operator_console(tmp_path)
    definition = _build_grounded_runtime_smoke_definition()

    result = benchmark_show_narration(
        operator_console=operator_console,
        definition=definition,
        request=PerformanceRunRequest(
            background=False,
            narration_voice_mode=VoiceRuntimeMode.STUB_DEMO,
            language="zh-CN",
            narration_voice_preset="chinese_cute_character",
            segment_ids=["arrival"],
        ),
    )

    assert result["show_name"] == "grounded_runtime_smoke"
    assert result["language"] == "zh-CN"
    assert result["voice_preset"] == "chinese_cute_character"
    assert result["cue_count"] >= 1
    assert result["actual_narration_ms"] >= 0.0


def test_performance_runner_cancels_cleanly_when_requested(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(tmp_path)
    definition = PerformanceShowDefinition(
        show_name="cancel_smoke",
        title="Cancel Smoke",
        version="v1",
        session_id="cancel-smoke-session",
        defaults={
            "proof_backend_mode": "deterministic_show"
        },
        segments=[
            PerformanceSegment(
                segment_id="cancel_segment",
                title="Cancel Segment",
                investor_claim="Cancelled runs should stop cleanly.",
                target_start_seconds=0,
                target_duration_seconds=5,
                cues=[
                    PerformanceCue(
                        cue_id="cancel_prompt",
                        cue_kind=PerformanceCueKind.PROMPT,
                        text="Start cancel rehearsal.",
                    ),
                    PerformanceCue(
                        cue_id="cancel_pause",
                        cue_kind=PerformanceCueKind.PAUSE,
                        target_duration_ms=500,
                    ),
                ],
            )
        ],
    )
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
        cancel_checker=lambda: True,
    )

    result = runner.run(definition, PerformanceRunRequest(background=False, narration_enabled=False))

    assert result.status == DemoRunStatus.CANCELLED
    assert result.stop_requested is True
    assert "performance_show_cancelled" in result.notes


def test_performance_runner_marks_blocked_when_live_serial_transport_is_missing(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_SERIAL_BODY,
        blink_body_driver=BodyDriverMode.SERIAL,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/cu.missing-demo",
    )
    definition = PerformanceShowDefinition(
        show_name="serial_preview_only_smoke",
        title="Serial Preview Only Smoke",
        version="v1",
        session_id="serial-preview-session",
        defaults={
            "proof_backend_mode": "deterministic_show"
        },
        segments=[
            PerformanceSegment(
                segment_id="preview_only",
                title="Preview Only",
                investor_claim="Live serial safety gates should fall back to blocked output honestly.",
                target_start_seconds=0,
                target_duration_seconds=10,
                cues=[
                    PerformanceCue(
                        cue_id="preview_pose",
                        cue_kind=PerformanceCueKind.BODY_SEMANTIC_SMOKE,
                        label="Preview pose",
                        action="look_forward",
                        intensity=0.5,
                    )
                ],
            )
        ],
    )
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )

    result = runner.run(
        definition,
        PerformanceRunRequest(background=False, narration_enabled=False, session_id="serial-preview-session"),
    )

    cue_result = result.segment_results[0].cue_results[0]
    assert result.status == DemoRunStatus.COMPLETED
    assert cue_result.payload["preview_only"] is False
    assert cue_result.payload["body_projection_outcome"] == PerformanceMotionOutcome.BLOCKED.value
    assert cue_result.motion_outcome == PerformanceMotionOutcome.BLOCKED
    assert cue_result.motion_margin_record is not None
    assert cue_result.motion_margin_record.outcome == PerformanceMotionOutcome.BLOCKED
    assert cue_result.motion_margin_record.safety_gate_passed is False
    assert cue_result.motion_margin_record.reason_code == "transport_unconfirmed"
    assert cue_result.actuator_coverage.head_yaw is True
    assert cue_result.actuator_coverage.eye_yaw is True


def test_performance_runner_marks_body_range_demo_blocked_when_live_prerequisites_are_missing(tmp_path: Path) -> None:
    operator_console, settings = _build_operator_console(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_SERIAL_BODY,
        blink_body_driver=BodyDriverMode.SERIAL,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/cu.missing-demo",
    )
    definition = PerformanceShowDefinition(
        show_name="range_demo_blocked_smoke",
        title="Range Demo Blocked Smoke",
        version="v1",
        session_id="range-demo-blocked-session",
        defaults={"proof_backend_mode": "deterministic_show"},
        segments=[
            PerformanceSegment(
                segment_id="motion_envelope",
                title="Motion Envelope",
                investor_claim="The range reveal should degrade honestly when live prerequisites are missing.",
                target_start_seconds=0,
                target_duration_seconds=10,
                cues=[
                    PerformanceCue(
                        cue_id="range_demo",
                        cue_kind=PerformanceCueKind.BODY_RANGE_DEMO,
                        payload={"preset_name": "investor_show_joint_envelope_v1"},
                    )
                ],
            )
        ],
    )
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(settings.performance_report_dir),
    )

    result = runner.run(
        definition,
        PerformanceRunRequest(background=False, narration_enabled=False, session_id="range-demo-blocked-session"),
    )

    cue_result = result.segment_results[0].cue_results[0]
    assert result.status == DemoRunStatus.COMPLETED
    assert cue_result.degraded is True
    assert cue_result.motion_outcome == PerformanceMotionOutcome.BLOCKED
    assert cue_result.payload["preview_only"] is False
    assert cue_result.payload["preset_name"] == "investor_show_joint_envelope_v1"
    assert cue_result.payload["motion_margin_record"]["reason_code"] == "transport_unconfirmed"
    latest_command_audit = (
        cue_result.payload["raw_result"].get("latest_command_audit")
        or cue_result.payload["raw_result"]["body_state"]["latest_command_audit"]
    )
    assert latest_command_audit["executed_frame_count"] > 0
    assert latest_command_audit["peak_normalized_pose"]["head_yaw"] != 0.0
