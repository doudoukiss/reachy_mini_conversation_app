from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from embodied_stack.config import Settings, get_settings
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.contracts import utc_now


REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = REPO_ROOT / "tests"


class AcceptanceStatus(str, Enum):
    PLANNED = "planned"
    PASSED = "passed"
    FAILED = "failed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    MANUAL = "manual"


class AcceptanceInventoryRecord(BaseModel):
    key: str
    label: str
    description: str
    test_files: list[str] = Field(default_factory=list)


class AcceptanceCommandRecord(BaseModel):
    key: str
    label: str
    category: str
    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    status: AcceptanceStatus = AcceptanceStatus.PLANNED
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    exit_code: int | None = None
    notes: list[str] = Field(default_factory=list)
    payload: dict[str, Any] | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None


class AcceptanceLaneRecord(BaseModel):
    run_id: str
    lane: str
    label: str
    description: str
    status: AcceptanceStatus
    started_at: str
    completed_at: str | None = None
    artifact_dir: str
    commands: list[AcceptanceCommandRecord] = Field(default_factory=list)
    inventory: list[AcceptanceInventoryRecord] = Field(default_factory=list)
    manual_steps: list[str] = Field(default_factory=list)
    summary_notes: list[str] = Field(default_factory=list)
    artifact_files: dict[str, str] = Field(default_factory=dict)


Evaluator = Callable[[subprocess.CompletedProcess[str]], tuple[AcceptanceStatus, dict[str, Any] | None, list[str]]]
Prerequisite = Callable[[], str | None]


@dataclass(frozen=True)
class AcceptanceCommandSpec:
    key: str
    label: str
    category: str
    command: tuple[str, ...]
    evaluator: Evaluator
    env: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    prerequisites: tuple[Prerequisite, ...] = ()


@dataclass(frozen=True)
class AcceptanceLaneSpec:
    key: str
    label: str
    description: str
    commands: tuple[AcceptanceCommandSpec, ...] = ()
    manual_steps: tuple[str, ...] = ()


CATEGORY_METADATA: tuple[tuple[str, str, str], ...] = (
    ("repo_health", "repo health", "Config, protocol, persistence, backend routing, and repo command integrity."),
    ("desktop_runtime", "desktop/runtime", "Terminal-first runtime, CLI, appliance, launcher, and edge bridge behavior."),
    ("agent_os", "Agent OS", "Turn orchestration, skill and tool routing, operator console, and bounded execution."),
    ("memory_relationship", "memory/relationship", "Memory policy, relationship runtime, presence, initiative, perception, and world-model continuity."),
    ("action_plane", "action plane", "Typed digital side effects, browser runtime, workflows, approvals, and action flywheel."),
    ("embodiment_serial", "embodiment/serial", "Character projection, avatar shell, semantic embodiment, serial driver, and live-serial safety gates."),
    ("demos_evals", "demos/evals", "End-to-end demo flows, smoke paths, certification, burn-in, and eval suites."),
)


def _uv(*args: str) -> tuple[str, ...]:
    return ("uv", "run", *args)


def _scenario_dry_run_command() -> tuple[tuple[str, ...], dict[str, str]]:
    return ("uv", "run", "python", "-m", "embodied_stack.sim.scenario_runner", "--dry-run"), {"PYTHONPATH": "src"}


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if not candidate:
        return None
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else {"value": payload}


def _get_field(payload: dict[str, Any] | None, path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _evaluate_exit_zero(result: subprocess.CompletedProcess[str]) -> tuple[AcceptanceStatus, dict[str, Any] | None, list[str]]:
    payload = _extract_json_payload(result.stdout)
    if result.returncode == 0:
        return AcceptanceStatus.PASSED, payload, []
    return AcceptanceStatus.FAILED, payload, [f"exit_code={result.returncode}"]


def _evaluate_json_truthy(field: str) -> Evaluator:
    def _evaluate(result: subprocess.CompletedProcess[str]) -> tuple[AcceptanceStatus, dict[str, Any] | None, list[str]]:
        payload = _extract_json_payload(result.stdout)
        value = _get_field(payload, field)
        notes = [f"{field}={value!r}"]
        if result.returncode != 0:
            notes.append(f"exit_code={result.returncode}")
            return AcceptanceStatus.FAILED, payload, notes
        if bool(value):
            return AcceptanceStatus.PASSED, payload, notes
        return AcceptanceStatus.FAILED, payload, notes

    return _evaluate


def _evaluate_json_equals(field: str, *, expected: str) -> Evaluator:
    def _evaluate(result: subprocess.CompletedProcess[str]) -> tuple[AcceptanceStatus, dict[str, Any] | None, list[str]]:
        payload = _extract_json_payload(result.stdout)
        value = _get_field(payload, field)
        notes = [f"{field}={value!r}"]
        if result.returncode != 0:
            notes.append(f"exit_code={result.returncode}")
            return AcceptanceStatus.FAILED, payload, notes
        if value == expected:
            return AcceptanceStatus.PASSED, payload, notes
        return AcceptanceStatus.FAILED, payload, notes

    return _evaluate


def _evaluate_certification(*, allow_degraded: bool) -> Evaluator:
    def _evaluate(result: subprocess.CompletedProcess[str]) -> tuple[AcceptanceStatus, dict[str, Any] | None, list[str]]:
        payload = _extract_json_payload(result.stdout)
        verdict = str(_get_field(payload, "verdict") or "")
        notes = [
            f"verdict={verdict or 'unknown'}",
            f"machine_readiness_passed={_get_field(payload, 'machine_readiness_passed')!r}",
            f"repo_runtime_correctness_passed={_get_field(payload, 'repo_runtime_correctness_passed')!r}",
        ]
        if result.returncode != 0:
            notes.append(f"exit_code={result.returncode}")
            return AcceptanceStatus.FAILED, payload, notes
        if verdict == "certified":
            return AcceptanceStatus.PASSED, payload, notes
        if allow_degraded and verdict == "degraded_but_acceptable":
            return AcceptanceStatus.DEGRADED, payload, notes
        return AcceptanceStatus.FAILED, payload, notes

    return _evaluate


def _require_env(name: str) -> Prerequisite:
    def _check() -> str | None:
        if os.getenv(name):
            return None
        return f"{name} is not set."

    return _check


def _require_existing_env_path(name: str) -> Prerequisite:
    def _check() -> str | None:
        value = os.getenv(name)
        if not value:
            return f"{name} is not set."
        if Path(value).exists():
            return None
        return f"{name} does not point to an existing path: {value}"

    return _check


def _categorize_test_file(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT)
    parts = relative.parts
    if len(parts) < 2:
        return "repo_health"
    if parts[1] == "action_plane":
        return "action_plane"
    if parts[1] == "body":
        return "embodiment_serial"
    if parts[1] in {"desktop", "edge"}:
        return "desktop_runtime"
    if parts[1] in {"demo", "evals"}:
        if relative.name == "test_action_flywheel.py":
            return "action_plane"
        return "demos_evals"
    if parts[1] in {"shared", "backends"}:
        return "repo_health"
    if parts[1] == "brain":
        if relative.name.startswith("test_agent_os_") or relative.name in {
            "test_auth.py",
            "test_brain_api.py",
            "test_operator_console.py",
            "test_orchestrator_integration.py",
            "test_participant_routing.py",
        }:
            return "agent_os"
        return "memory_relationship"
    if relative.name in {
        "test_config.py",
        "test_makefile_acceptance_targets.py",
        "test_makefile_serial_targets.py",
        "test_persistence.py",
    }:
        return "repo_health"
    return "repo_health"


def build_test_inventory() -> list[AcceptanceInventoryRecord]:
    buckets: dict[str, list[str]] = {key: [] for key, _, _ in CATEGORY_METADATA}
    for path in sorted(TEST_ROOT.rglob("test*.py")):
        category = _categorize_test_file(path)
        buckets[category].append(str(path.relative_to(REPO_ROOT)))
    return [
        AcceptanceInventoryRecord(
            key=key,
            label=label,
            description=description,
            test_files=buckets[key],
        )
        for key, label, description in CATEGORY_METADATA
    ]


def _acceptance_lanes() -> dict[str, AcceptanceLaneSpec]:
    scenario_command, scenario_env = _scenario_dry_run_command()
    return {
        "inventory": AcceptanceLaneSpec(
            key="inventory",
            label="Acceptance Inventory",
            description="Print the current automated acceptance surface by category.",
        ),
        "quick": AcceptanceLaneSpec(
            key="quick",
            label="Quick Acceptance",
            description="Fast high-yield acceptance lane for day-to-day regression checks on the current milestone.",
            commands=(
                AcceptanceCommandSpec(
                    key="pytest_collect",
                    label="pytest collect-only",
                    category="repo_health",
                    command=_uv("pytest", "--collect-only", "-q"),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="repo_health_pytests",
                    label="repo health pytest slice",
                    category="repo_health",
                    command=_uv(
                        "pytest",
                        "tests/test_config.py",
                        "tests/test_persistence.py",
                        "tests/shared/test_protocol.py",
                        "tests/backends/test_router.py",
                        "tests/test_makefile_serial_targets.py",
                        "tests/test_makefile_acceptance_targets.py",
                        "-q",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="desktop_runtime_pytests",
                    label="desktop/runtime pytest slice",
                    category="desktop_runtime",
                    command=_uv(
                        "pytest",
                        "tests/desktop/test_cli.py",
                        "tests/desktop/test_local_runtime.py",
                        "tests/desktop/test_runtime.py",
                        "tests/desktop/test_always_on_runtime.py",
                        "tests/desktop/test_streaming_local_runtime.py",
                        "tests/edge/test_edge_runtime.py",
                        "-q",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="agent_os_pytests",
                    label="Agent OS pytest slice",
                    category="agent_os",
                    command=_uv(
                        "pytest",
                        "tests/brain/test_agent_os_runtime.py",
                        "tests/brain/test_agent_os_tools.py",
                        "tests/brain/test_operator_console.py",
                        "-q",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="memory_relationship_pytests",
                    label="memory/relationship pytest slice",
                    category="memory_relationship",
                    command=_uv(
                        "pytest",
                        "tests/brain/test_memory_store.py",
                        "tests/brain/test_companion_memory.py",
                        "tests/brain/test_presence_runtime.py",
                        "tests/brain/test_initiative_engine.py",
                        "tests/brain/test_world_model.py",
                        "-q",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="action_plane_pytests",
                    label="action plane pytest slice",
                    category="action_plane",
                    command=_uv(
                        "pytest",
                        "tests/action_plane/test_stage_a.py",
                        "tests/action_plane/test_workflow_runtime.py",
                        "tests/demo/test_action_flywheel.py",
                        "-q",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="embodiment_pytests",
                    label="embodiment/serial pytest slice",
                    category="embodiment_serial",
                    command=_uv(
                        "pytest",
                        "tests/body/test_character_projection.py",
                        "tests/body/test_presence_shell.py",
                        "tests/body/test_serial_driver.py",
                        "tests/body/test_live_serial_gates.py",
                        "-q",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="local_companion_checks",
                    label="local companion checks",
                    category="demos_evals",
                    command=_uv("local-companion-checks"),
                    evaluator=_evaluate_json_truthy("passed"),
                ),
                AcceptanceCommandSpec(
                    key="always_on_local_checks",
                    label="always-on local checks",
                    category="demos_evals",
                    command=_uv("always-on-local-checks"),
                    evaluator=_evaluate_json_truthy("passed"),
                ),
                AcceptanceCommandSpec(
                    key="continuous_local_checks",
                    label="continuous local checks",
                    category="demos_evals",
                    command=_uv("continuous-local-checks"),
                    evaluator=_evaluate_json_truthy("passed"),
                ),
                AcceptanceCommandSpec(
                    key="scenario_dry_run",
                    label="scenario dry-run",
                    category="demos_evals",
                    command=scenario_command,
                    env=scenario_env,
                    evaluator=_evaluate_exit_zero,
                ),
            ),
        ),
        "full": AcceptanceLaneSpec(
            key="full",
            label="Full Acceptance",
            description="Authoritative automated milestone acceptance lane for the current no-robot local companion path.",
            commands=(
                AcceptanceCommandSpec(
                    key="full_pytest",
                    label="full pytest suite",
                    category="repo_health",
                    command=_uv("pytest"),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="scenario_dry_run",
                    label="scenario dry-run",
                    category="demos_evals",
                    command=scenario_command,
                    env=scenario_env,
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="local_companion_certify",
                    label="local companion certification",
                    category="demos_evals",
                    command=_uv("local-companion-certify"),
                    evaluator=_evaluate_certification(allow_degraded=True),
                    notes=(
                        "A degraded certification result is reported as degraded rather than failed in the full lane.",
                    ),
                ),
                AcceptanceCommandSpec(
                    key="local_companion_burn_in",
                    label="local companion burn-in",
                    category="demos_evals",
                    command=_uv("local-companion-burn-in"),
                    evaluator=_evaluate_json_truthy("passed"),
                ),
                AcceptanceCommandSpec(
                    key="demo_checks",
                    label="demo checks",
                    category="demos_evals",
                    command=_uv("demo-checks"),
                    evaluator=_evaluate_json_truthy("passed"),
                ),
            ),
        ),
        "rc": AcceptanceLaneSpec(
            key="rc",
            label="Release Candidate Acceptance",
            description="Stricter automated release-candidate lane for the current milestone before manual local-Mac review.",
            commands=(
                AcceptanceCommandSpec(
                    key="full_pytest",
                    label="full pytest suite",
                    category="repo_health",
                    command=_uv("pytest"),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="scenario_dry_run",
                    label="scenario dry-run",
                    category="demos_evals",
                    command=scenario_command,
                    env=scenario_env,
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="local_companion_certify",
                    label="local companion certification",
                    category="demos_evals",
                    command=_uv("local-companion-certify"),
                    evaluator=_evaluate_certification(allow_degraded=False),
                ),
                AcceptanceCommandSpec(
                    key="local_companion_burn_in",
                    label="local companion burn-in",
                    category="demos_evals",
                    command=_uv("local-companion-burn-in"),
                    evaluator=_evaluate_json_truthy("passed"),
                ),
                AcceptanceCommandSpec(
                    key="demo_checks",
                    label="demo checks",
                    category="demos_evals",
                    command=_uv("demo-checks"),
                    evaluator=_evaluate_json_truthy("passed"),
                ),
                AcceptanceCommandSpec(
                    key="smoke",
                    label="in-process smoke path",
                    category="demos_evals",
                    command=_uv("smoke-runner"),
                    evaluator=_evaluate_json_equals("status", expected="completed"),
                ),
                AcceptanceCommandSpec(
                    key="multimodal_demo_checks",
                    label="multimodal demo checks",
                    category="demos_evals",
                    command=_uv("multimodal-demo-checks"),
                    evaluator=_evaluate_json_truthy("passed"),
                ),
            ),
            manual_steps=(
                "Run `make acceptance-manual-local` for the live local-Mac walkthrough after the automated RC lane is green.",
                "If serial hardware is part of the release candidate, also run `make acceptance-hardware` on the wired Mac with the validated head profile and saved calibration.",
            ),
        ),
        "manual-local": AcceptanceLaneSpec(
            key="manual-local",
            label="Manual Local-Mac Acceptance",
            description="Human acceptance checklist for the terminal-first companion plus optional browser surfaces on the target Mac.",
            manual_steps=(
                "Run `uv run local-companion --open-console` on the target Mac so the terminal-first companion path stays primary.",
                "Use `docs/human_acceptance.md` as the authoritative 20 to 30 minute checklist and session script.",
                "Run the companion/chat session and verify startup, terminal conversation, memory continuity, and bounded initiative.",
                "Run the helpful task session and verify console visibility plus action approval clarity in both terminal and Action Center.",
                "Run the interruption/failure session and verify degraded-mode honesty, stop controls, silence controls, and clean shutdown.",
                "Restart with a fresh `--session-id` and confirm the tester can tell what reset changed and what continuity remained.",
            ),
        ),
        "hardware": AcceptanceLaneSpec(
            key="hardware",
            label="Hardware Acceptance",
            description="Optional live-serial acceptance lane for the real robot head. This lane is intentionally separate from the default no-robot acceptance flow.",
            commands=(
                AcceptanceCommandSpec(
                    key="live_serial_readback",
                    label="live-serial readback and safe-idle",
                    category="embodiment_serial",
                    command=_uv("pytest", "tests/body/test_live_serial_validation.py", "-m", "live_serial", "-q"),
                    evaluator=_evaluate_exit_zero,
                    prerequisites=(
                        _require_env("BLINK_SERIAL_PORT"),
                    ),
                    notes=(
                        "Requires a real serial transport path and the validated port exported in BLINK_SERIAL_PORT.",
                    ),
                ),
                AcceptanceCommandSpec(
                    key="live_serial_motion",
                    label="live-serial motion smoke",
                    category="embodiment_serial",
                    command=_uv("pytest", "tests/body/test_live_serial_validation.py", "-m", "live_serial_motion", "-q"),
                    evaluator=_evaluate_exit_zero,
                    prerequisites=(
                        _require_env("BLINK_SERIAL_PORT"),
                        _require_existing_env_path("BLINK_HEAD_CALIBRATION"),
                    ),
                    notes=(
                        "Requires a saved live calibration and should be run only after operator motion-arm confirmation.",
                    ),
                ),
            ),
        ),
        "investor-show-quick": AcceptanceLaneSpec(
            key="investor-show-quick",
            label="Investor Show Quick Acceptance",
            description="Fast maintained investor-show regression lane covering V8 asset integrity, CLI/API drift, and a deterministic proof-only bodyless run.",
            commands=(
                AcceptanceCommandSpec(
                    key="investor_show_pytests",
                    label="investor show pytest slice",
                    category="demos_evals",
                    command=_uv(
                        "pytest",
                        "tests/demo/test_performance_show.py",
                        "tests/body/test_performance_motion_profile.py",
                        "tests/brain/test_operator_console.py",
                        "tests/desktop/test_cli.py",
                        "tests/test_makefile_serial_targets.py",
                        "tests/test_makefile_acceptance_targets.py",
                        "-q",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_dry_run",
                    label="investor show dry run",
                    category="demos_evals",
                    command=_uv(
                        "local-companion",
                        "performance-dry-run",
                        "investor_expressive_motion_v8",
                        "--proof-backend-mode",
                        "deterministic_show",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_v8_cue_smoke",
                    label="investor show V8 cue smoke",
                    category="demos_evals",
                    command=_uv(
                        "local-companion",
                        "performance-show",
                        "investor_expressive_motion_v8",
                        "--cue",
                        "guarded_close_right_run",
                        "--cue",
                        "bright_reengage_run",
                        "--no-narration",
                        "--proof-backend-mode",
                        "deterministic_show",
                        "--reset-runtime",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_bodyless_proof",
                    label="investor show bodyless proof-only run",
                    category="demos_evals",
                    command=_uv(
                        "local-companion",
                        "performance-show",
                        "investor_expressive_motion_v8",
                        "--proof-backend-mode",
                        "deterministic_show",
                        "--proof-only",
                        "--no-narration",
                        "--reset-runtime",
                        "--session-id",
                        "acceptance-investor-show-quick",
                    ),
                    env={
                        "BLINK_RUNTIME_MODE": "desktop_bodyless",
                        "BLINK_BODY_DRIVER": "bodyless",
                    },
                    evaluator=_evaluate_exit_zero,
                ),
            ),
            manual_steps=(
                "Use `docs/investor_show_runbook.md` for the maintained rehearsal order and fallback ladder after the quick lane is green.",
            ),
        ),
        "investor-show-full": AcceptanceLaneSpec(
            key="investor-show-full",
            label="Investor Show Full Acceptance",
            description="Authoritative maintained investor-show lane covering V8 dry run, bodyless and virtual runs, focused cue-smokes, and motion-profile regressions.",
            commands=(
                AcceptanceCommandSpec(
                    key="investor_show_pytests",
                    label="investor show pytest slice",
                    category="demos_evals",
                    command=_uv(
                        "pytest",
                        "tests/demo/test_performance_show.py",
                        "tests/body/test_performance_motion_profile.py",
                        "tests/brain/test_operator_console.py",
                        "tests/desktop/test_cli.py",
                        "-q",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_dry_run",
                    label="investor show dry run",
                    category="demos_evals",
                    command=_uv(
                        "local-companion",
                        "performance-dry-run",
                        "investor_expressive_motion_v8",
                        "--proof-backend-mode",
                        "deterministic_show",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_guarded_close_smoke",
                    label="investor show guarded-close cue smoke",
                    category="demos_evals",
                    command=_uv(
                        "local-companion",
                        "performance-show",
                        "investor_expressive_motion_v8",
                        "--cue",
                        "guarded_close_right_run",
                        "--cue",
                        "guarded_close_left_run",
                        "--no-narration",
                        "--proof-backend-mode",
                        "deterministic_show",
                        "--reset-runtime",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_playful_reengage_smoke",
                    label="investor show playful and reengage cue smoke",
                    category="demos_evals",
                    command=_uv(
                        "local-companion",
                        "performance-show",
                        "investor_expressive_motion_v8",
                        "--cue",
                        "playful_peek_right_run",
                        "--cue",
                        "bright_reengage_run",
                        "--no-narration",
                        "--proof-backend-mode",
                        "deterministic_show",
                        "--reset-runtime",
                    ),
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_bodyless_full",
                    label="investor show full bodyless run",
                    category="demos_evals",
                    command=_uv(
                        "local-companion",
                        "performance-show",
                        "investor_expressive_motion_v8",
                        "--proof-backend-mode",
                        "deterministic_show",
                        "--narration-voice-mode",
                        "stub_demo",
                        "--reset-runtime",
                        "--session-id",
                        "acceptance-investor-show-bodyless",
                    ),
                    env={
                        "BLINK_RUNTIME_MODE": "desktop_bodyless",
                        "BLINK_BODY_DRIVER": "bodyless",
                    },
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_virtual_full",
                    label="investor show full virtual-body run",
                    category="embodiment_serial",
                    command=_uv(
                        "local-companion",
                        "performance-show",
                        "investor_expressive_motion_v8",
                        "--proof-backend-mode",
                        "deterministic_show",
                        "--narration-voice-mode",
                        "stub_demo",
                        "--reset-runtime",
                        "--session-id",
                        "acceptance-investor-show-virtual",
                    ),
                    env={
                        "BLINK_RUNTIME_MODE": "desktop_virtual_body",
                        "BLINK_BODY_DRIVER": "virtual",
                    },
                    evaluator=_evaluate_exit_zero,
                ),
                AcceptanceCommandSpec(
                    key="investor_show_full_v8_run",
                    label="investor show full V8 run",
                    category="demos_evals",
                    command=_uv(
                        "local-companion",
                        "performance-show",
                        "investor_expressive_motion_v8",
                        "--proof-backend-mode",
                        "deterministic_show",
                        "--no-narration",
                        "--reset-runtime",
                        "--session-id",
                        "acceptance-investor-show-v8",
                    ),
                    env={
                        "BLINK_RUNTIME_MODE": "desktop_bodyless",
                        "BLINK_BODY_DRIVER": "bodyless",
                    },
                    evaluator=_evaluate_exit_zero,
                ),
            ),
            manual_steps=(
                "After the automated full lane, run a cue-by-cue live-head rehearsal and then one full dress rehearsal using `docs/investor_show_runbook.md`.",
            ),
        ),
        "investor-show-hardware": AcceptanceLaneSpec(
            key="investor-show-hardware",
            label="Investor Show Hardware Acceptance",
            description="Optional live-serial gate for the maintained V3-V8 evidence ladder and the V8 expressive proof.",
            commands=(
                AcceptanceCommandSpec(
                    key="live_serial_readback",
                    label="live-serial readback and safe-idle",
                    category="embodiment_serial",
                    command=_uv("pytest", "tests/body/test_live_serial_validation.py", "-m", "live_serial", "-q"),
                    evaluator=_evaluate_exit_zero,
                    prerequisites=(
                        _require_env("BLINK_SERIAL_PORT"),
                    ),
                ),
                AcceptanceCommandSpec(
                    key="live_serial_motion",
                    label="live-serial motion smoke",
                    category="embodiment_serial",
                    command=_uv("pytest", "tests/body/test_live_serial_validation.py", "-m", "live_serial_motion", "-q"),
                    evaluator=_evaluate_exit_zero,
                    prerequisites=(
                        _require_env("BLINK_SERIAL_PORT"),
                        _require_existing_env_path("BLINK_HEAD_CALIBRATION"),
                    ),
                ),
            ),
            manual_steps=(
                "Run the cue-by-cue live-head rehearsal and preflight checklist from `docs/investor_show_runbook.md` before any public show use.",
            ),
        ),
    }


def _artifact_root(settings: Settings) -> Path:
    return Path(settings.acceptance_report_dir)


def _command_log_base(lane_dir: Path, command_key: str) -> tuple[Path, Path]:
    log_dir = lane_dir / "commands"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{command_key}.stdout.log", log_dir / f"{command_key}.stderr.log"


def _write_markdown_summary(record: AcceptanceLaneRecord, *, path: Path) -> None:
    lines = [
        "# Blink-AI Acceptance Report",
        "",
        f"- lane: `{record.lane}`",
        f"- status: `{record.status.value}`",
        f"- started_at: `{record.started_at}`",
        f"- completed_at: `{record.completed_at or '-'}`",
        f"- artifact_dir: `{record.artifact_dir}`",
        "",
        "## Test Inventory",
        "",
        "| category | file count | scope |",
        "| --- | ---: | --- |",
    ]
    for item in record.inventory:
        scope = "<br>".join(item.test_files) if item.test_files else "-"
        lines.append(f"| {item.label} | {len(item.test_files)} | {scope} |")
    if record.summary_notes:
        lines.extend(["", "## Summary Notes", ""])
        lines.extend([f"- {note}" for note in record.summary_notes])
    if record.commands:
        lines.extend(["", "## Commands", ""])
        for item in record.commands:
            lines.extend(
                [
                    f"### {item.label}",
                    "",
                    f"- category: `{item.category}`",
                    f"- status: `{item.status.value}`",
                    f"- command: `{subprocess.list2cmdline(item.command)}`",
                    f"- started_at: `{item.started_at or '-'}`",
                    f"- completed_at: `{item.completed_at or '-'}`",
                    f"- duration_seconds: `{item.duration_seconds if item.duration_seconds is not None else '-'}`",
                    f"- exit_code: `{item.exit_code if item.exit_code is not None else '-'}`",
                ]
            )
            if item.notes:
                lines.extend([f"- note: {note}" for note in item.notes])
            if item.stdout_path:
                lines.append(f"- stdout: `{item.stdout_path}`")
            if item.stderr_path:
                lines.append(f"- stderr: `{item.stderr_path}`")
            lines.append("")
    if record.manual_steps:
        lines.extend(["## Manual Steps", ""])
        lines.extend([f"1. {step}" if index == 0 else f"{index + 1}. {step}" for index, step in enumerate(record.manual_steps)])
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _summarize_status(commands: list[AcceptanceCommandRecord], *, manual_steps: list[str], planned: bool) -> AcceptanceStatus:
    if planned:
        return AcceptanceStatus.PLANNED
    if commands:
        statuses = {item.status for item in commands}
        if AcceptanceStatus.FAILED in statuses:
            return AcceptanceStatus.FAILED
        if AcceptanceStatus.DEGRADED in statuses:
            return AcceptanceStatus.DEGRADED
        if statuses == {AcceptanceStatus.SKIPPED}:
            return AcceptanceStatus.SKIPPED
        return AcceptanceStatus.PASSED
    if manual_steps:
        return AcceptanceStatus.MANUAL
    return AcceptanceStatus.PASSED


def run_acceptance(
    lane: str,
    *,
    settings: Settings | None = None,
    execute: bool = True,
) -> AcceptanceLaneRecord:
    settings = settings or get_settings()
    lanes = _acceptance_lanes()
    if lane not in lanes:
        raise ValueError(f"Unknown acceptance lane: {lane}")
    spec = lanes[lane]
    started_at = utc_now()
    run_id = f"{lane}-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    lane_dir = _artifact_root(settings) / run_id
    lane_dir.mkdir(parents=True, exist_ok=True)

    record = AcceptanceLaneRecord(
        run_id=run_id,
        lane=spec.key,
        label=spec.label,
        description=spec.description,
        status=AcceptanceStatus.PLANNED,
        started_at=started_at.isoformat(),
        artifact_dir=str(lane_dir),
        inventory=build_test_inventory(),
        manual_steps=list(spec.manual_steps),
    )

    for command in spec.commands:
        command_record = AcceptanceCommandRecord(
            key=command.key,
            label=command.label,
            category=command.category,
            command=list(command.command),
            env=dict(command.env),
            notes=list(command.notes),
        )
        stdout_path, stderr_path = _command_log_base(lane_dir, command.key)
        command_record.stdout_path = str(stdout_path)
        command_record.stderr_path = str(stderr_path)

        skip_reasons = [reason for prereq in command.prerequisites if (reason := prereq()) is not None]
        if skip_reasons:
            command_record.status = AcceptanceStatus.SKIPPED
            command_record.notes.extend(skip_reasons)
            record.commands.append(command_record)
            continue

        if not execute:
            record.commands.append(command_record)
            continue

        env = os.environ.copy()
        env.update(command.env)
        command_started = utc_now()
        command_record.started_at = command_started.isoformat()
        completed = subprocess.run(
            list(command.command),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        command_completed = utc_now()
        status, payload, notes = command.evaluator(completed)
        command_record.status = status
        command_record.payload = payload
        command_record.exit_code = completed.returncode
        command_record.completed_at = command_completed.isoformat()
        command_record.duration_seconds = round((command_completed - command_started).total_seconds(), 3)
        command_record.notes.extend(notes)
        record.commands.append(command_record)

    record.completed_at = utc_now().isoformat()
    record.status = _summarize_status(record.commands, manual_steps=record.manual_steps, planned=not execute)
    if record.status == AcceptanceStatus.DEGRADED:
        record.summary_notes.append(
            "This lane completed, but at least one acceptance command reported a degraded result. Review the certification and suite artifacts before treating the machine as release-ready."
        )
    if record.status == AcceptanceStatus.SKIPPED:
        record.summary_notes.append("This lane did not execute because its prerequisites were not present in the current environment.")
    if record.status == AcceptanceStatus.MANUAL:
        record.summary_notes.append("This lane is a human checklist. It does not execute automated checks.")

    json_path = lane_dir / "acceptance.json"
    markdown_path = lane_dir / "acceptance.md"
    record.artifact_files = {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }
    write_json_atomic(json_path, record.model_dump(mode="json"))
    _write_markdown_summary(record, path=markdown_path)
    return record


def _print_summary(record: AcceptanceLaneRecord) -> None:
    summary = {
        "run_id": record.run_id,
        "lane": record.lane,
        "status": record.status.value,
        "artifact_dir": record.artifact_dir,
        "artifact_files": record.artifact_files,
        "command_count": len(record.commands),
        "failed_commands": [item.key for item in record.commands if item.status == AcceptanceStatus.FAILED],
        "degraded_commands": [item.key for item in record.commands if item.status == AcceptanceStatus.DEGRADED],
        "skipped_commands": [item.key for item in record.commands if item.status == AcceptanceStatus.SKIPPED],
    }
    print(json.dumps(summary, indent=2))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blink-AI acceptance harness.")
    parser.add_argument(
        "lane",
        choices=tuple(_acceptance_lanes().keys()),
        help="Acceptance lane to run.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Write the lane inventory and planned commands without executing them.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    record = run_acceptance(args.lane, execute=not args.plan)
    _print_summary(record)
    if record.status == AcceptanceStatus.FAILED:
        raise SystemExit(1)


__all__ = [
    "AcceptanceCommandRecord",
    "AcceptanceInventoryRecord",
    "AcceptanceLaneRecord",
    "AcceptanceStatus",
    "build_test_inventory",
    "main",
    "parse_args",
    "run_acceptance",
]
