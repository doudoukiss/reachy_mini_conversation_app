# Serial Head Live Observation Sequence

This runbook is for visually checking the current head movements and expressions on the real robot, using the current live setup from [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md).

For the latest family-by-family revalidation nuances, especially the neck-pair caveats around isolated tilt versus paired pitch, also check [robot_head_live_revalidation_2026-04-10.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_revalidation_2026-04-10.md).

It is intentionally operator-facing:
- low-amplitude direct probes first
- fixed safe sync groups second
- semantic gazes, expressions, gestures, and animations last
- `write-neutral` between actions so each result is easy to judge
- successful runs end in `write-neutral` with torque still on, then `disarm-live-motion`
- successful runs also write `neutral_tolerance_check.json` so the final held pose is compared against the saved calibration neutral
- interrupted or failing runs fall back to `write-neutral`, then `safe-idle`, then `disarm-live-motion`

## Assumptions

- Port: `/dev/cu.usbmodem5B790314811`
- Baud: `1000000`
- Profile: `src/embodied_stack/body/profiles/robot_head_v1.json`
- Calibration: `runtime/calibrations/robot_head_live_v1.json`
- The robot is already powered and mechanically clear.

Current calibration note:

- `brow_right.neutral` was corrected to `2000` in the saved live calibration after live debugging showed the previous saved neutral kept the right brow visually too low.
- The observation sequence below assumes that corrected calibration file is the active source of truth.

## What To Watch

From [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md):

- `head_yaw` maps to ID1.
  - raw `+` = right
  - raw `-` = left
- `head_pitch_pair_a` and `head_pitch_pair_b` map to IDs 2 and 3.
  - `a +` and `b -` = head up
  - `a -` and `b +` = head down
  - `a +` alone = tilt right
  - `b -` alone = tilt left
- `lower_lid_left`, `upper_lid_left`, `lower_lid_right`, `upper_lid_right` map to IDs 4, 5, 6, 7.
- `eye_pitch` maps to ID8.
  - raw `+` = eyes up
  - raw `-` = eyes down
- `eye_yaw` maps to ID9.
  - raw `+` = eyes right
  - raw `-` = eyes left
- `brow_left` and `brow_right` map to IDs 10 and 11.
  - left brow raw `+` = raise
  - right brow raw `-` = raise

## Quick Start

Run the full automated observation sequence:

```bash
cd /Users/sonics/project/Blink-AI
BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811 \
BLINK_SERVO_BAUD=1000000 \
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json \
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json \
BLINK_OBSERVE_PAUSE_SECONDS=2.5 \
BLINK_OBSERVE_INTENSITY=0.3 \
BLINK_OBSERVE_HEAD_EYE_NEUTRAL_TOLERANCE=100 \
BLINK_OBSERVE_LID_BROW_NEUTRAL_TOLERANCE=60 \
bash scripts/serial_head_live_observation.sh
```

Artifacts are written under:

```text
runtime/serial/manual_validation/<timestamp>_live_observation/
```

The run now also writes:

```text
neutral_tolerance_check.json
```

If any joint lands outside the configured tolerance from the saved calibration neutral, the script exits non-zero and the trap falls back to `safe-idle`.

## Manual Command Sequence

If you want to drive it step by step yourself, use this base prefix:

```bash
cd /Users/sonics/project/Blink-AI
BASE='PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --profile src/embodied_stack/body/profiles/robot_head_v1.json \
  --calibration runtime/calibrations/robot_head_live_v1.json'
```

Start safe:

```bash
eval "$BASE bench-health"
eval "$BASE arm-live-motion --ttl-seconds 300"
eval "$BASE write-neutral --confirm-live-write"
```

### Direct Joint Probes

```bash
eval "$BASE move-joint --joint head_yaw --delta -20 --duration-ms 500"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE move-joint --joint head_yaw --delta 20 --duration-ms 500"
eval "$BASE write-neutral --confirm-live-write"

eval "$BASE move-joint --joint eye_yaw --delta -20 --duration-ms 450"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE move-joint --joint eye_yaw --delta 20 --duration-ms 450"
eval "$BASE write-neutral --confirm-live-write"

eval "$BASE move-joint --joint eye_pitch --delta 20 --duration-ms 450"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE move-joint --joint eye_pitch --delta -20 --duration-ms 450"
eval "$BASE write-neutral --confirm-live-write"

eval "$BASE move-joint --joint brow_left --delta 20 --duration-ms 450"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE move-joint --joint brow_right --delta -20 --duration-ms 450"
eval "$BASE write-neutral --confirm-live-write"
```

### Safe Sync Groups

```bash
eval "$BASE sync-move --group head_up_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group head_down_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group head_tilt_right_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group head_tilt_left_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"

eval "$BASE sync-move --group eyes_left_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group eyes_right_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group eyes_up_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group eyes_down_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"

eval "$BASE sync-move --group lids_open_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group lids_close_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group brows_raise_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE sync-move --group brows_lower_small --duration-ms 550"
eval "$BASE write-neutral --confirm-live-write"
```

### Semantic Gazes

```bash
eval "$BASE semantic-smoke --action look_forward --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action look_at_user --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action look_left --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action look_right --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action look_up --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action look_down_briefly --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
```

### Semantic Expressions

```bash
eval "$BASE semantic-smoke --action neutral --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action friendly --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action thinking --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action concerned --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action confused --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action listen_attentively --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
```

### Semantic Gestures

```bash
eval "$BASE semantic-smoke --action blink_soft --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action wink_left --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action wink_right --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action nod_small --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action tilt_curious --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
```

### Semantic Animations

```bash
eval "$BASE semantic-smoke --action recover_neutral --intensity 0.3 --repeat-count 1 --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action micro_blink_loop --intensity 0.3 --repeat-count 1 --allow-bench-actions --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action scan_softly --intensity 0.3 --repeat-count 1 --allow-bench-actions --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE semantic-smoke --action speak_listen_transition --intensity 0.3 --repeat-count 1 --allow-bench-actions --confirm-live-write"
eval "$BASE write-neutral --confirm-live-write"
```

Finish in neutral hold:

```bash
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE bench-health"
eval "$BASE disarm-live-motion"
```

If the run must be aborted or becomes unsafe, use the recovery path instead:

```bash
eval "$BASE write-neutral --confirm-live-write"
eval "$BASE safe-idle"
eval "$BASE disarm-live-motion"
```

## Suggested Observation Checklist

- `head_yaw` left and right should match the direction notes in [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md).
- `head_up_small` and `head_down_small` should be symmetric and not scrape or strain.
- `head_tilt_right_small` and `head_tilt_left_small` should isolate tilt rather than obvious pitch.
- `eyes_left_small`, `eyes_right_small`, `eyes_up_small`, `eyes_down_small` should match the eye direction notes from [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md).
- `lids_open_small` and `lids_close_small` should preserve the mirrored eyelid relationship.
- `brows_raise_small` and `brows_lower_small` should preserve the mirrored brow relationship.
- `brow_right` should now visibly raise and lower instead of appearing pinned near its lowered stop.
- `friendly`, `thinking`, `concerned`, `confused`, and `listen_attentively` should look distinct enough to judge.
- `wink_left` and `wink_right` should isolate the intended side cleanly.
- `scan_softly` and `speak_listen_transition` are bench-only semantic actions and should remain mechanically calm at `0.3` intensity.
