from __future__ import annotations

import argparse
import json

import httpx

from embodied_stack.demo.community_scripts import DEMO_SCENARIOS
from embodied_stack.shared.models import RobotEvent, SimulatedSensorEventRequest


BRAIN_URL = "http://127.0.0.1:8000"
EDGE_URL = "http://127.0.0.1:8010"


def run_scenarios(dry_run: bool = False) -> None:
    session_id = "demo-session"
    print("Running investor-style scenario sequence...")

    if dry_run:
        for name, scenario in DEMO_SCENARIOS.items():
            print(f"[dry-run] Scenario: {name} - {scenario.description}")
            for step in scenario.steps:
                event = RobotEvent(event_type=step.event_type, payload=step.payload, session_id=session_id)
                print(json.dumps(event.model_dump(mode="json"), indent=2))
        return

    with httpx.Client(timeout=10.0) as client:
        for name, scenario in DEMO_SCENARIOS.items():
            print(f"\n=== Scenario: {name} ===")
            print(scenario.description)
            for step in scenario.steps:
                sim_request = SimulatedSensorEventRequest(
                    event_type=step.event_type,
                    payload=step.payload,
                    session_id=session_id,
                )
                sim_resp = client.post(f"{EDGE_URL}/api/sim/events", json=sim_request.model_dump(mode="json"))
                sim_resp.raise_for_status()
                sim_result = sim_resp.json()
                event = sim_result["event"]
                print(f"Edge emitted event: {event['event_type']}")

                batch_resp = client.post(f"{BRAIN_URL}/api/events", json=event)
                batch_resp.raise_for_status()
                batch = batch_resp.json()
                print(f"Brain reply: {batch.get('reply_text')}")
                for command in batch.get("commands", []):
                    ack_resp = client.post(f"{EDGE_URL}/api/commands", json=command)
                    ack_resp.raise_for_status()
                    ack = ack_resp.json()
                    print(f"  Applied command {command['command_type']}: accepted={ack['accepted']} reason={ack['reason']}")

        telemetry_resp = client.get(f"{EDGE_URL}/api/telemetry")
        telemetry_resp.raise_for_status()
        heartbeat_resp = client.get(f"{EDGE_URL}/api/heartbeat")
        heartbeat_resp.raise_for_status()
        print("\nFinal telemetry:")
        print(json.dumps(telemetry_resp.json(), indent=2))
        print("\nHeartbeat:")
        print(json.dumps(heartbeat_resp.json(), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print scenario events without calling services.")
    args = parser.parse_args()
    run_scenarios(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
