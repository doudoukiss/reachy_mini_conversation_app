#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${BLINK_SERIAL_PORT:-/dev/cu.usbmodem5B790314811}"
BAUD="${BLINK_SERVO_BAUD:-1000000}"
PROFILE="${BLINK_HEAD_PROFILE:-src/embodied_stack/body/profiles/robot_head_v1.json}"
CALIBRATION="${BLINK_HEAD_CALIBRATION:-runtime/calibrations/robot_head_live_v1.json}"
PAUSE_SECONDS="${BLINK_OBSERVE_PAUSE_SECONDS:-2.5}"
INTENSITY="${BLINK_OBSERVE_INTENSITY:-0.3}"
HEAD_EYE_TOLERANCE="${BLINK_OBSERVE_HEAD_EYE_NEUTRAL_TOLERANCE:-100}"
LID_BROW_TOLERANCE="${BLINK_OBSERVE_LID_BROW_NEUTRAL_TOLERANCE:-60}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="runtime/serial/manual_validation/${RUN_ID}_live_observation"
RUN_COMPLETED=0

mkdir -p "$RUN_DIR"

body_calibration() {
  PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
    --transport live_serial \
    --port "$PORT" \
    --baud "$BAUD" \
    --profile "$PROFILE" \
    --calibration "$CALIBRATION" \
    "$@"
}

run_step() {
  local step_name="$1"
  shift
  printf '==> %s\n' "$step_name"
  body_calibration "$@" >"$RUN_DIR/${step_name}.json" 2>"$RUN_DIR/${step_name}.stderr.txt"
  sleep "$PAUSE_SECONDS"
}

run_semantic() {
  local action_name="$1"
  local extra_flag="${2:-}"
  printf '==> semantic:%s\n' "$action_name"
  if [[ -n "$extra_flag" ]]; then
    body_calibration semantic-smoke \
      --action "$action_name" \
      --intensity "$INTENSITY" \
      --repeat-count 1 \
      --confirm-live-write \
      "$extra_flag" >"$RUN_DIR/semantic_${action_name}.json" 2>"$RUN_DIR/semantic_${action_name}.stderr.txt"
  else
    body_calibration semantic-smoke \
      --action "$action_name" \
      --intensity "$INTENSITY" \
      --repeat-count 1 \
      --confirm-live-write >"$RUN_DIR/semantic_${action_name}.json" 2>"$RUN_DIR/semantic_${action_name}.stderr.txt"
  fi
  sleep "$PAUSE_SECONDS"
  run_step "neutral_after_${action_name}" write-neutral --confirm-live-write
}

check_final_neutral_tolerance() {
  uv run python - "$CALIBRATION" "$RUN_DIR/bench_health_end.json" "$RUN_DIR/neutral_tolerance_check.json" "$HEAD_EYE_TOLERANCE" "$LID_BROW_TOLERANCE" <<'PY'
import json
import sys
from pathlib import Path

calibration_path = Path(sys.argv[1])
bench_health_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])
head_eye_tolerance = int(sys.argv[4])
lid_brow_tolerance = int(sys.argv[5])

calibration = json.loads(calibration_path.read_text())
bench_health = json.loads(bench_health_path.read_text())
positions = bench_health["position_reads"]

def tolerance_for_joint(name: str) -> int:
    if name.startswith("head_") or name.startswith("eye_"):
        return head_eye_tolerance
    if "lid" in name or "brow" in name:
        return lid_brow_tolerance
    return head_eye_tolerance

joint_positions = {
    str(payload["servo_id"]): payload["position"]
    for payload in positions.values()
    if isinstance(payload, dict) and "position" in payload
}

checks: list[dict[str, object]] = []
violations: list[dict[str, object]] = []

for joint in calibration["joint_records"]:
    servo_ids = joint.get("servo_ids") or []
    if not servo_ids:
        continue
    servo_id = str(servo_ids[0])
    observed = joint_positions.get(servo_id)
    if observed is None:
        continue
    neutral = int(joint["neutral"])
    delta = abs(int(observed) - neutral)
    tolerance = tolerance_for_joint(joint["joint_name"])
    item = {
        "joint_name": joint["joint_name"],
        "servo_id": int(servo_id),
        "neutral": neutral,
        "observed": int(observed),
        "delta": delta,
        "tolerance": tolerance,
        "within_tolerance": delta <= tolerance,
    }
    checks.append(item)
    if delta > tolerance:
        violations.append(item)

payload = {
    "operation": "final_neutral_tolerance_check",
    "calibration_path": str(calibration_path),
    "bench_health_path": str(bench_health_path),
    "head_eye_tolerance": head_eye_tolerance,
    "lid_brow_tolerance": lid_brow_tolerance,
    "checks": checks,
    "violations": violations,
    "ok": not violations,
}
output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
if violations:
    print(json.dumps(payload, indent=2))
    raise SystemExit(1)
print(json.dumps(payload, indent=2))
PY
}

cleanup() {
  if [[ "$RUN_COMPLETED" == "1" ]]; then
    return
  fi
  body_calibration write-neutral --confirm-live-write >"$RUN_DIR/final_write_neutral.json" 2>"$RUN_DIR/final_write_neutral.stderr.txt" || true
  sleep "$PAUSE_SECONDS" || true
  body_calibration safe-idle >"$RUN_DIR/final_safe_idle.json" 2>"$RUN_DIR/final_safe_idle.stderr.txt" || true
  body_calibration disarm-live-motion >"$RUN_DIR/final_disarm.json" 2>"$RUN_DIR/final_disarm.stderr.txt" || true
}

trap cleanup EXIT

if [[ ! -f "$CALIBRATION" ]]; then
  printf 'Missing calibration file: %s\n' "$CALIBRATION" >&2
  exit 1
fi

printf 'Live observation run directory: %s\n' "$RUN_DIR"
printf 'Using port=%s baud=%s calibration=%s\n' "$PORT" "$BAUD" "$CALIBRATION"

run_step "bench_health_start" bench-health
run_step "arm_live_motion" arm-live-motion --ttl-seconds 300
run_step "write_neutral_start" write-neutral --confirm-live-write

run_step "move_head_left_small" move-joint --joint head_yaw --delta -20 --duration-ms 500
run_step "neutral_after_move_head_left_small" write-neutral --confirm-live-write
run_step "move_head_right_small" move-joint --joint head_yaw --delta 20 --duration-ms 500
run_step "neutral_after_move_head_right_small" write-neutral --confirm-live-write
run_step "move_eye_left_small" move-joint --joint eye_yaw --delta -20 --duration-ms 450
run_step "neutral_after_move_eye_left_small" write-neutral --confirm-live-write
run_step "move_eye_right_small" move-joint --joint eye_yaw --delta 20 --duration-ms 450
run_step "neutral_after_move_eye_right_small" write-neutral --confirm-live-write
run_step "move_eye_up_small" move-joint --joint eye_pitch --delta 20 --duration-ms 450
run_step "neutral_after_move_eye_up_small" write-neutral --confirm-live-write
run_step "move_eye_down_small" move-joint --joint eye_pitch --delta -20 --duration-ms 450
run_step "neutral_after_move_eye_down_small" write-neutral --confirm-live-write
run_step "move_brow_left_raise_small" move-joint --joint brow_left --delta 20 --duration-ms 450
run_step "neutral_after_move_brow_left_raise_small" write-neutral --confirm-live-write
run_step "move_brow_right_raise_small" move-joint --joint brow_right --delta -20 --duration-ms 450
run_step "neutral_after_move_brow_right_raise_small" write-neutral --confirm-live-write

for group_name in \
  head_up_small \
  head_down_small \
  head_tilt_right_small \
  head_tilt_left_small \
  eyes_left_small \
  eyes_right_small \
  eyes_up_small \
  eyes_down_small \
  lids_open_small \
  lids_close_small \
  brows_raise_small \
  brows_lower_small
do
  run_step "sync_${group_name}" sync-move --group "$group_name" --duration-ms 550
  run_step "neutral_after_sync_${group_name}" write-neutral --confirm-live-write
done

for action_name in \
  look_forward \
  look_at_user \
  look_left \
  look_right \
  look_up \
  look_down_briefly \
  neutral \
  friendly \
  thinking \
  concerned \
  confused \
  listen_attentively \
  blink_soft \
  wink_left \
  wink_right \
  nod_small \
  tilt_curious \
  recover_neutral
do
  run_semantic "$action_name"
done

for action_name in micro_blink_loop scan_softly speak_listen_transition; do
  run_semantic "$action_name" --allow-bench-actions
done

run_step "write_neutral_hold_end" write-neutral --confirm-live-write
run_step "bench_health_end" bench-health
printf '==> final_neutral_tolerance_check\n'
check_final_neutral_tolerance >"$RUN_DIR/final_neutral_tolerance_check.stdout.json" 2>"$RUN_DIR/final_neutral_tolerance_check.stderr.txt"
run_step "disarm_end" disarm-live-motion
RUN_COMPLETED=1

printf 'Observation run complete. Artifacts: %s\n' "$RUN_DIR"
