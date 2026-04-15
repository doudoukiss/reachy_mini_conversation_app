from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from embodied_stack.config import Settings, get_settings
from embodied_stack.persistence import load_json_value_or_quarantine, write_json_atomic


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class ManagedServiceProcess:
    name: str
    url: str
    process: subprocess.Popen[str]
    log_path: Path
    log_handle: Any

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.log_handle.close()


class TetheredDemoStack:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        runtime_dir: str | Path | None = None,
        brain_port: int | None = None,
        edge_port: int | None = None,
        edge_driver_profile: str = "jetson_simulated_io",
        operator_auth_token: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.runtime_dir = Path(runtime_dir or "runtime/tethered_demo/live")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.runtime_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.stack_info_path = self.runtime_dir / "stack_info.json"
        self.brain_port = brain_port or _find_free_port()
        self.edge_port = edge_port or _find_free_port()
        self.edge_driver_profile = edge_driver_profile
        self.operator_auth_token = operator_auth_token or secrets.token_urlsafe(18)
        self.operator_auth_runtime_file = self.runtime_dir / "operator_auth.json"
        self.edge: ManagedServiceProcess | None = None
        self.brain: ManagedServiceProcess | None = None

    @property
    def brain_url(self) -> str:
        return f"http://127.0.0.1:{self.brain_port}"

    @property
    def edge_url(self) -> str:
        return f"http://127.0.0.1:{self.edge_port}"

    def start(self) -> "TetheredDemoStack":
        self.edge = self._launch_service(
            name="edge",
            module="embodied_stack.edge.app",
            port=self.edge_port,
            extra_env={
                "EDGE_HOST": "127.0.0.1",
                "EDGE_PORT": str(self.edge_port),
                "EDGE_DRIVER_PROFILE": self.edge_driver_profile,
            },
        )
        self._wait_for_health(f"{self.edge_url}/health")
        self._wait_for_ready(f"{self.edge_url}/ready")

        self.brain = self._launch_service(
            name="brain",
            module="embodied_stack.brain.app",
            port=self.brain_port,
            extra_env={
                "BRAIN_HOST": "127.0.0.1",
                "BRAIN_PORT": str(self.brain_port),
                "EDGE_BASE_URL": self.edge_url,
                "BRAIN_STORE_PATH": str(self.runtime_dir / "brain_store.json"),
                "DEMO_REPORT_DIR": str(self.runtime_dir / "demo_runs"),
                "DEMO_CHECK_DIR": str(self.runtime_dir / "demo_checks"),
                "BRAIN_DIALOGUE_BACKEND": self.settings.brain_dialogue_backend,
                "BRAIN_VOICE_BACKEND": self.settings.brain_voice_backend,
                "BRAIN_RUNTIME_PROFILE": "tethered-demo-ops",
                "BRAIN_DEPLOYMENT_TARGET": "mac_studio",
                "BLINK_RUNTIME_MODE": "tethered_future",
                "BLINK_BODY_DRIVER": "tethered",
                "OPERATOR_AUTH_TOKEN": self.operator_auth_token,
                "OPERATOR_AUTH_RUNTIME_FILE": str(self.operator_auth_runtime_file),
            },
        )
        self._wait_for_health(f"{self.brain_url}/health")
        self._wait_for_ready(f"{self.brain_url}/ready")
        self._write_stack_info()
        return self

    def stop(self) -> None:
        if self.brain is not None:
            self.brain.stop()
        if self.edge is not None:
            self.edge.stop()

    def __enter__(self) -> "TetheredDemoStack":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def operator_headers(self) -> dict[str, str]:
        return {"x-blink-operator-token": self.operator_auth_token}

    def http_client(self, *, timeout: float = 10.0) -> httpx.Client:
        return httpx.Client(timeout=timeout, headers=self.operator_headers())

    def readiness_snapshot(self) -> dict[str, Any]:
        with self.http_client(timeout=5.0) as client:
            brain_ready = client.get(f"{self.brain_url}/ready")
            edge_ready = httpx.get(f"{self.edge_url}/ready", timeout=5.0)
            auth_status = client.get(f"{self.brain_url}/api/operator/auth/status")
        brain_ready.raise_for_status()
        edge_ready.raise_for_status()
        auth_status.raise_for_status()
        return {
            "brain": brain_ready.json(),
            "edge": edge_ready.json(),
            "operator_auth": auth_status.json(),
        }

    def stack_info(self) -> dict[str, Any]:
        return {
            "brain_url": self.brain_url,
            "edge_url": self.edge_url,
            "runtime_dir": str(self.runtime_dir),
            "logs_dir": str(self.logs_dir),
            "brain_log": str(self.logs_dir / "brain.log"),
            "edge_log": str(self.logs_dir / "edge.log"),
            "brain_store_path": str(self.runtime_dir / "brain_store.json"),
            "demo_report_dir": str(self.runtime_dir / "demo_runs"),
            "demo_check_dir": str(self.runtime_dir / "demo_checks"),
            "operator_auth_token": self.operator_auth_token,
            "operator_auth_runtime_file": str(self.operator_auth_runtime_file),
            "edge_driver_profile": self.edge_driver_profile,
        }

    def _write_stack_info(self) -> None:
        write_json_atomic(self.stack_info_path, self.stack_info(), keep_backups=3)

    def _launch_service(self, *, name: str, module: str, port: int, extra_env: dict[str, str]) -> ManagedServiceProcess:
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", "src")
        env.update(extra_env)
        log_path = self.logs_dir / f"{name}.log"
        log_handle = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-m", module],
            cwd=self._repo_root(),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return ManagedServiceProcess(
            name=name,
            url=f"http://127.0.0.1:{port}",
            process=process,
            log_path=log_path,
            log_handle=log_handle,
        )

    def _wait_for_health(self, url: str, timeout_seconds: float = 12.0) -> None:
        deadline = time.time() + timeout_seconds
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                response = httpx.get(url, timeout=1.0)
                if response.status_code == 200:
                    return
            except Exception as exc:  # pragma: no cover - polling
                last_error = exc
            time.sleep(0.1)
        raise RuntimeError(f"service_failed_healthcheck:{url}:{last_error}")

    def _wait_for_ready(self, url: str, timeout_seconds: float = 12.0) -> None:
        deadline = time.time() + timeout_seconds
        last_detail: str | None = None
        while time.time() < deadline:
            try:
                response = httpx.get(url, timeout=1.0)
                if response.status_code == 200:
                    body = response.json()
                    if body.get("ok"):
                        return
                    last_detail = json.dumps(body)
            except Exception as exc:  # pragma: no cover - polling
                last_detail = str(exc)
            time.sleep(0.1)
        raise RuntimeError(f"service_failed_readiness:{url}:{last_detail}")

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[3]


def read_stack_info(runtime_dir: str | Path | None = None) -> dict[str, Any]:
    info_path = Path(runtime_dir or "runtime/tethered_demo/live") / "stack_info.json"
    existed = info_path.exists()
    payload = load_json_value_or_quarantine(info_path, quarantine_invalid=True)
    if isinstance(payload, dict):
        return payload
    if existed:
        raise RuntimeError(f"invalid_stack_info:{info_path}")
    raise FileNotFoundError(info_path)


def reset_running_stack(*, runtime_dir: str | Path | None = None) -> dict[str, Any]:
    info = read_stack_info(runtime_dir)
    with httpx.Client(timeout=10.0, headers={"x-blink-operator-token": info["operator_auth_token"]}) as client:
        response = client.post(
            f"{info['brain_url']}/api/reset",
            json={"reset_edge": True, "clear_user_memory": True, "clear_demo_runs": False},
        )
        response.raise_for_status()
        return response.json()


def readiness_status(*, runtime_dir: str | Path | None = None) -> dict[str, Any]:
    info = read_stack_info(runtime_dir)
    with httpx.Client(timeout=10.0, headers={"x-blink-operator-token": info["operator_auth_token"]}) as client:
        brain_ready = client.get(f"{info['brain_url']}/ready")
        edge_ready = httpx.get(f"{info['edge_url']}/ready", timeout=10.0)
        auth_status = client.get(f"{info['brain_url']}/api/operator/auth/status")
    brain_ready.raise_for_status()
    edge_ready.raise_for_status()
    auth_status.raise_for_status()
    return {
        "brain": brain_ready.json(),
        "edge": edge_ready.json(),
        "operator_auth": auth_status.json(),
        "brain_url": info["brain_url"],
        "edge_url": info["edge_url"],
        "logs_dir": info["logs_dir"],
    }


def run_tethered_smoke(*, runtime_dir: str | Path | None = None) -> dict[str, Any]:
    with TetheredDemoStack(runtime_dir=runtime_dir) as stack, stack.http_client(timeout=30.0) as client:
        reset = client.post(
            f"{stack.brain_url}/api/reset",
            json={"reset_edge": True, "clear_user_memory": True, "clear_demo_runs": True},
        )
        reset.raise_for_status()
        snapshot = client.get(f"{stack.brain_url}/api/operator/snapshot")
        snapshot.raise_for_status()
        run = client.post(
            f"{stack.brain_url}/api/demo-runs",
            json={"scenario_names": ["welcome_and_wayfinding", "safe_fallback_demo"]},
        )
        run.raise_for_status()
        body = run.json()
        return {
            "brain_url": stack.brain_url,
            "edge_url": stack.edge_url,
            "runtime_profile": snapshot.json()["runtime"]["runtime_profile"],
            "edge_transport_mode": snapshot.json()["runtime"]["edge_transport_mode"],
            "edge_transport_state": snapshot.json()["runtime"]["edge_transport_state"],
            "run_id": body["run_id"],
            "status": body["status"],
            "passed": body["passed"],
            "report_path": body["report_path"],
            "artifact_dir": body["artifact_dir"],
            "edge_driver_profile": stack.edge_driver_profile,
            "stack_info_path": str(stack.stack_info_path),
        }


def serve_tethered_demo(*, runtime_dir: str | Path | None = None, edge_driver_profile: str = "jetson_simulated_io") -> None:
    stack = TetheredDemoStack(
        runtime_dir=runtime_dir or "runtime/tethered_demo/live",
        brain_port=8000,
        edge_port=8010,
        edge_driver_profile=edge_driver_profile,
    )
    try:
        stack.start()
        print(json.dumps({**stack.stack_info(), "readiness": stack.readiness_snapshot()}, indent=2))
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stack.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("smoke")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--runtime-dir", default="runtime/tethered_demo/live")
    serve_parser.add_argument("--edge-driver-profile", default="jetson_simulated_io")

    reset_parser = subparsers.add_parser("reset")
    reset_parser.add_argument("--runtime-dir", default="runtime/tethered_demo/live")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--runtime-dir", default="runtime/tethered_demo/live")

    args = parser.parse_args()
    if args.command in {None, "smoke"}:
        print(json.dumps(run_tethered_smoke(), indent=2))
        return
    if args.command == "serve":
        serve_tethered_demo(runtime_dir=args.runtime_dir, edge_driver_profile=args.edge_driver_profile)
        return
    if args.command == "reset":
        print(json.dumps(reset_running_stack(runtime_dir=args.runtime_dir), indent=2))
        return
    if args.command == "status":
        print(json.dumps(readiness_status(runtime_dir=args.runtime_dir), indent=2))
        return


if __name__ == "__main__":
    main()
