from __future__ import annotations

import subprocess
from pathlib import Path


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


def test_make_acceptance_inventory_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-inventory")
    assert "uv run blink-acceptance inventory" in output


def test_make_acceptance_quick_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-quick")
    assert "uv run blink-acceptance quick" in output


def test_make_acceptance_full_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-full")
    assert "uv run blink-acceptance full" in output


def test_make_acceptance_rc_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-rc")
    assert "uv run blink-acceptance rc" in output


def test_make_acceptance_manual_local_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-manual-local")
    assert "uv run blink-acceptance manual-local" in output


def test_make_acceptance_hardware_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-hardware")
    assert "uv run blink-acceptance hardware" in output


def test_make_acceptance_investor_show_quick_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-investor-show-quick")
    assert "uv run blink-acceptance investor-show-quick" in output


def test_make_acceptance_investor_show_full_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-investor-show-full")
    assert "uv run blink-acceptance investor-show-full" in output


def test_make_acceptance_investor_show_hardware_target_uses_acceptance_runner() -> None:
    output = _make_dry_run("acceptance-investor-show-hardware")
    assert "uv run blink-acceptance investor-show-hardware" in output
