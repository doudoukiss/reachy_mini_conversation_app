from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser

import httpx

from embodied_stack.config import Settings, get_settings
from embodied_stack.desktop.doctor import run_local_companion_doctor
from embodied_stack.desktop.runtime_profile import build_appliance_startup_summary, ensure_runtime_layout, reset_runtime_state


def appliance_settings(*, port: int | None = None) -> Settings:
    settings = get_settings().model_copy(deep=True)
    settings.brain_host = "127.0.0.1"
    if port is not None:
        settings.brain_port = port
    settings.blink_appliance_mode = True
    return settings


def build_service_env(settings: Settings) -> dict[str, str]:
    env = dict(os.environ)
    env["BRAIN_HOST"] = settings.brain_host
    env["BRAIN_PORT"] = str(settings.brain_port)
    env["BLINK_APPLIANCE_MODE"] = "true"
    env["BLINK_APPLIANCE_PROFILE_FILE"] = settings.blink_appliance_profile_file
    return env


def wait_for_service_ready(*, base_url: str, timeout_seconds: float = 20.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    with httpx.Client(timeout=2.0) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(f"{base_url}/ready")
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # pragma: no cover - exercised through launcher smoke flow
                last_error = str(exc)
                time.sleep(0.2)
    raise RuntimeError(f"blink_appliance_ready_timeout:{last_error or 'unknown'}")


def fetch_service_health(*, base_url: str) -> dict[str, object]:
    with httpx.Client(timeout=5.0) as client:
        response = client.get(f"{base_url}/health")
        response.raise_for_status()
        return response.json()


def fetch_appliance_status(*, base_url: str) -> dict[str, object]:
    with httpx.Client(timeout=5.0) as client:
        response = client.get(f"{base_url}/api/appliance/status")
        response.raise_for_status()
        return response.json()


def open_console_url(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def launch_service(settings: Settings) -> subprocess.Popen[str]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "embodied_stack.desktop.app:app",
        "--host",
        settings.brain_host,
        "--port",
        str(settings.brain_port),
        "--no-access-log",
    ]
    return subprocess.Popen(command, env=build_service_env(settings))


def run_appliance(*, settings: Settings, open_console: bool) -> int:
    ensure_runtime_layout(settings)
    process = launch_service(settings)
    base_url = f"http://{settings.brain_host}:{settings.brain_port}"
    startup_summary = build_appliance_startup_summary(
        settings,
        selected_microphone_label=settings.blink_mic_device or "default",
        selected_camera_label=settings.blink_camera_device or "default",
        selected_speaker_label=settings.blink_speaker_device or "system_default",
    )
    try:
        wait_for_service_ready(base_url=base_url)
        console_url = f"{base_url}/console"
        appliance_status = fetch_appliance_status(base_url=base_url)
        health = fetch_service_health(base_url=base_url)
        opened = open_console_url(console_url) if open_console else False
        warnings = [
            issue.get("category") or issue.get("message") or "warning"
            for issue in appliance_status.get("setup_issues", [])
            if not issue.get("blocking")
        ]
        print(f"blink_appliance url={console_url}")
        print(f"blink_appliance browser={'opened' if opened else 'available'}")
        print(
            "blink_appliance_ready "
            f"console={console_url} "
            f"text={health.get('dialogue_backend') or '-'} "
            f"microphone={appliance_status.get('selected_microphone_label') or '-'} "
            f"camera={appliance_status.get('selected_camera_label') or '-'} "
            f"speaker={appliance_status.get('selected_speaker_label') or '-'} "
            f"warnings={','.join(warnings) if warnings else '-'}"
        )
        print(
            "blink_appliance_startup "
            f"runtime_mode={startup_summary.runtime_mode.value if startup_summary.runtime_mode else '-'} "
            f"model_profile={startup_summary.model_profile or '-'} "
            f"backend_profile={startup_summary.backend_profile or '-'} "
            f"voice_profile={startup_summary.voice_profile or '-'} "
            f"device_preset={startup_summary.device_preset or '-'} "
            f"config_source={startup_summary.config_source or '-'}"
        )
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            return process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait(timeout=5.0)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch Blink-AI as a localhost appliance on macOS.")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--reset-runtime", action="store_true")
    parser.add_argument("--open-console", action="store_true", default=True)
    parser.add_argument("--no-open-console", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = appliance_settings(port=args.port)

    if args.reset_runtime:
        removed = reset_runtime_state(settings)
        print(f"blink_appliance_reset removed={len(removed)}")
        return 0

    if args.doctor:
        report = run_local_companion_doctor(settings=settings, write_path="runtime/diagnostics/blink_appliance_report.md")
        print(f"blink_appliance_doctor report={report['report_path']} issues={len(report.get('issues', []))}")
        return 0

    return run_appliance(settings=settings, open_console=bool(args.open_console and not args.no_open_console))


if __name__ == "__main__":
    raise SystemExit(main())
