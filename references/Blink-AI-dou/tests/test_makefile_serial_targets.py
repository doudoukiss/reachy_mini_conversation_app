from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_dry_run(target: str, *extra: str) -> str:
    result = subprocess.run(
        ["make", "-n", target, *extra],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_make_serial_bench_target_uses_stage_e_runner() -> None:
    output = _make_dry_run(
        "serial-bench",
        "BLINK_SERIAL_PORT=/dev/cu.test",
        "BLINK_CONFIRM_LIVE_WRITE=1",
    )
    assert "blink-serial-bench" in output
    assert "--transport live_serial" in output
    assert "--semantic-action look_left" in output
    assert "--joint head_yaw" in output


def test_make_serial_neutral_target_uses_live_write_flag() -> None:
    output = _make_dry_run(
        "serial-neutral",
        "BLINK_SERIAL_PORT=/dev/cu.test",
        "BLINK_CONFIRM_LIVE_WRITE=1",
    )
    assert "body.calibration" in output
    assert "write-neutral" in output
    assert "--confirm-live-write" in output


def test_make_serial_companion_target_launches_appliance_in_serial_mode() -> None:
    output = _make_dry_run(
        "serial-companion",
        "BLINK_SERIAL_PORT=/dev/cu.test",
    )
    assert "blink-appliance" in output
    assert "BLINK_RUNTIME_MODE=desktop_serial_body" in output
    assert "BLINK_SERIAL_TRANSPORT=live_serial" in output


def test_make_action_plane_validate_target_runs_stage6_surfaces() -> None:
    output = _make_dry_run("action-plane-validate")
    assert "tests/action_plane" in output
    assert "tests/brain/test_operator_console.py" in output
    assert "tests/desktop/test_cli.py" in output
    assert "tests/demo/test_action_flywheel.py" in output


def test_make_investor_show_dry_target_uses_local_companion_dry_run() -> None:
    output = _make_dry_run("investor-show-dry")
    assert "BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v8.json" in output
    assert (
        "uv run local-companion performance-dry-run investor_expressive_motion_v8 --proof-backend-mode deterministic_show"
        in output
    )


def test_make_investor_show_target_uses_local_companion_show_runner() -> None:
    output = _make_dry_run("investor-show")
    assert "BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v8.json" in output
    assert (
        "uv run local-companion performance-show investor_expressive_motion_v8 --proof-backend-mode deterministic_show --reset-runtime"
        in output
    )


def test_make_investor_show_v3_target_uses_local_companion_show_runner() -> None:
    output = _make_dry_run("investor-show-v3")
    assert "BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v3.json" in output
    assert "uv run local-companion performance-show investor_head_motion_v3 --proof-backend-mode deterministic_show --reset-runtime" in output


def test_make_investor_show_v3_live_target_uses_serial_runtime() -> None:
    output = _make_dry_run("investor-show-v3-live", "BLINK_SERIAL_PORT=/dev/cu.test")
    assert "body.calibration" in output
    assert "arm-live-motion" in output
    assert "--ttl-seconds 300" in output
    assert "BLINK_RUNTIME_MODE=desktop_serial_body" in output
    assert "BLINK_BODY_DRIVER=serial" in output
    assert "BLINK_SERIAL_TRANSPORT=live_serial" in output
    assert "BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v3.json" in output
    assert "investor_head_motion_v3 --proof-backend-mode deterministic_show --reset-runtime" in output


@pytest.mark.parametrize(
    ("target", "show_name", "tuning_path"),
    [
        ("investor-show-v4", "investor_eye_motion_v4", "runtime/body/semantic_tuning/robot_head_investor_show_v4.json"),
        ("investor-show-v5", "investor_lid_motion_v5", "runtime/body/semantic_tuning/robot_head_investor_show_v5.json"),
        ("investor-show-v6", "investor_brow_motion_v6", "runtime/body/semantic_tuning/robot_head_investor_show_v6.json"),
        ("investor-show-v7", "investor_neck_motion_v7", "runtime/body/semantic_tuning/robot_head_investor_show_v7.json"),
        ("investor-show-v8", "investor_expressive_motion_v8", "runtime/body/semantic_tuning/robot_head_investor_show_v8.json"),
    ],
)
def test_make_post_v3_targets_use_local_companion_show_runner(
    target: str,
    show_name: str,
    tuning_path: str,
) -> None:
    output = _make_dry_run(target)
    assert f"BLINK_BODY_SEMANTIC_TUNING_PATH={tuning_path}" in output
    assert f"uv run local-companion performance-show {show_name} --proof-backend-mode deterministic_show --reset-runtime" in output


@pytest.mark.parametrize(
    ("target", "show_name", "tuning_path"),
    [
        ("investor-show-v4-live", "investor_eye_motion_v4", "runtime/body/semantic_tuning/robot_head_investor_show_v4.json"),
        ("investor-show-v5-live", "investor_lid_motion_v5", "runtime/body/semantic_tuning/robot_head_investor_show_v5.json"),
        ("investor-show-v6-live", "investor_brow_motion_v6", "runtime/body/semantic_tuning/robot_head_investor_show_v6.json"),
        ("investor-show-v7-live", "investor_neck_motion_v7", "runtime/body/semantic_tuning/robot_head_investor_show_v7.json"),
        ("investor-show-v8-live", "investor_expressive_motion_v8", "runtime/body/semantic_tuning/robot_head_investor_show_v8.json"),
    ],
)
def test_make_post_v3_live_targets_use_serial_runtime(
    target: str,
    show_name: str,
    tuning_path: str,
) -> None:
    output = _make_dry_run(target, "BLINK_SERIAL_PORT=/dev/cu.test")
    assert "body.calibration" in output
    assert "arm-live-motion" in output
    assert "--ttl-seconds 300" in output
    assert "BLINK_RUNTIME_MODE=desktop_serial_body" in output
    assert "BLINK_BODY_DRIVER=serial" in output
    assert "BLINK_SERIAL_TRANSPORT=live_serial" in output
    assert f"BLINK_BODY_SEMANTIC_TUNING_PATH={tuning_path}" in output
    assert f"{show_name} --proof-backend-mode deterministic_show --reset-runtime" in output


def test_make_investor_show_virtual_target_runs_virtual_body_show() -> None:
    output = _make_dry_run("investor-show-virtual")
    assert "BLINK_RUNTIME_MODE=desktop_virtual_body" in output
    assert "BLINK_BODY_DRIVER=virtual" in output


def test_make_investor_show_cue_smoke_target_runs_filtered_cues() -> None:
    output = _make_dry_run("investor-show-cue-smoke")
    assert "--cue guarded_close_right_run" in output
    assert "--cue guarded_close_left_run" in output
    assert "--cue playful_peek_right_run" in output
    assert "--cue bright_reengage_run" in output
    assert "investor_expressive_motion_v8" in output


def test_make_investor_power_preflight_target_runs_idle_power_preflight() -> None:
    output = _make_dry_run("investor-power-preflight", "BLINK_SERIAL_PORT=/dev/cu.test")
    assert "body.calibration" in output
    assert "power-preflight" in output
    assert "--transport live_serial" in output


def test_make_investor_show_reset_target_uses_local_companion_reset() -> None:
    output = _make_dry_run("investor-show-reset")
    assert "uv run local-companion reset --no-edge-reset" in output


def test_make_investor_show_targets_no_longer_expose_parallel_versioned_variants() -> None:
    output = _make_dry_run("investor-show")
    assert "investor_ten_minute_v1" not in output
    assert "investor_ten_minute_v2" not in output


def test_make_action_export_inspect_target_uses_inspection_module() -> None:
    output = _make_dry_run("action-export-inspect")
    assert "embodied_stack.demo.action_plane_inspect" in output


def test_make_local_companion_certify_target_uses_certification_entrypoint() -> None:
    output = _make_dry_run("local-companion-certify")
    assert "uv run local-companion-certify" in output


def test_make_local_companion_burn_in_target_uses_burn_in_entrypoint() -> None:
    output = _make_dry_run("local-companion-burn-in")
    assert "uv run local-companion-burn-in" in output


def test_make_local_companion_failure_drills_target_uses_failure_drill_entrypoint() -> None:
    output = _make_dry_run("local-companion-failure-drills")
    assert "uv run local-companion-failure-drills" in output


def test_make_local_companion_soak_target_uses_burn_in_entrypoint() -> None:
    output = _make_dry_run("local-companion-soak")
    assert "uv run local-companion-burn-in" in output


def test_make_local_companion_stress_target_runs_failure_drills_and_burn_in() -> None:
    output = _make_dry_run("local-companion-stress")
    assert "uv run local-companion-failure-drills" in output
    assert "uv run local-companion-burn-in" in output


def test_make_stabilize_fast_target_runs_local_companion_stabilization_lane() -> None:
    output = _make_dry_run("stabilize-fast")
    assert "uv run blink-acceptance quick" in output


def test_make_stabilize_full_target_runs_full_validation_lane() -> None:
    output = _make_dry_run("stabilize-full")
    assert "uv run blink-acceptance full" in output


def test_make_stabilize_live_local_target_prints_manual_acceptance_lane() -> None:
    output = _make_dry_run("stabilize-live-local")
    assert "uv run blink-acceptance manual-local" in output
