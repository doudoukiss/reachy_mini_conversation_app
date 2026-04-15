# Investor Show Runbook

This is the maintained operator runbook for the current investor embodiment surface.

## Maintained Shows

- main expressive proof: `investor_expressive_motion_v8`
- focused evidence ladder:
  - `investor_head_motion_v3`
  - `investor_eye_motion_v4`
  - `investor_lid_motion_v5`
  - `investor_brow_motion_v6`
  - `investor_neck_motion_v7`
- separate range proof: `robot_head_servo_range_showcase_v1`

The old V1 and V2 investor shows are no longer maintained.

## Current Defaults

- proof mode: `deterministic_show`
- shared context: explicit `venue_demo`
- V3-V7 kinetics: `speed=100`, `acceleration=32`
- V8 kinetics: `speed=90`, `acceleration=24`
- live family-demo and V8 arm lease: `300s`
- live calibration authority: `runtime/calibrations/robot_head_live_v1.json`
- maintained V8 tuning: `runtime/body/semantic_tuning/robot_head_investor_show_v8.json`

## Preflight

Before any live rehearsal:

1. Confirm the runtime mode:
   - bodyless: `BLINK_RUNTIME_MODE=desktop_bodyless`, `BLINK_BODY_DRIVER=bodyless`
   - virtual: `BLINK_RUNTIME_MODE=desktop_virtual_body`, `BLINK_BODY_DRIVER=virtual`
   - live serial: `BLINK_RUNTIME_MODE=desktop_serial_body`, `BLINK_BODY_DRIVER=serial`
2. Confirm transport and calibration:
   - `BLINK_SERIAL_PORT`
   - `BLINK_HEAD_CALIBRATION`
   - `BLINK_BODY_SEMANTIC_TUNING_PATH`
3. Run:

```bash
make acceptance-investor-show-quick
make serial-doctor
make motion-config-audit
make investor-power-preflight
make usable-range-audit
```

4. Write neutral before the first live proof:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --profile src/embodied_stack/body/profiles/robot_head_v1.json \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  write-neutral --duration-ms 800 --confirm-live-write
```

## Appliance Path

Use this when you want `/performance`, `/console`, and a visible operator surface:

```bash
uv run blink-appliance
```

Open:

- projector: `/performance`
- operator: `/console`

Useful operator API surfaces:

- capability export:

```bash
curl -sS http://127.0.0.1:8000/api/operator/body/expression-catalog | jq
```

- launch the maintained V8 run:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/operator/performance-shows/investor_expressive_motion_v8/run \
  -H 'Content-Type: application/json' \
  -d '{"background": true, "session_id": "investor-expressive-motion-v8", "reset_runtime": true, "proof_backend_mode": "deterministic_show"}'
```

## One-Shot Local Commands

### Maintained V8 lane

```bash
make investor-show-dry
make investor-show
make investor-show-virtual
make investor-show-cue-smoke
```

### Focused hardware ladder

```bash
make investor-show-v3
make investor-show-v4
make investor-show-v5
make investor-show-v6
make investor-show-v7
make investor-show-v8
```

### Live hardware ladder

```bash
make investor-show-v3-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v4-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v5-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v6-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v7-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v8-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

### Separate servo proof

```bash
make servo-showcase-dry
make servo-showcase-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make servo-showcase-bench
```

## Recommended Live Acceptance Order

Use this exact order for a fresh branch or a new machine:

1. `make serial-doctor`
2. neutral write
3. `make investor-show-v3-live`
4. `make investor-show-v4-live`
5. `make investor-show-v5-live`
6. `make investor-show-v6-live`
7. `make investor-show-v7-live`
8. semantic smoke on grounded persistent states:
   - `friendly`
   - `listen_attentively`
   - `thinking`
   - `focused_soft`
   - `concerned`
9. motif cue-smokes:
   - `guarded_close_right`
   - `guarded_close_left`
   - `skeptical_tilt_right`
   - `playful_peek_right`
   - `bright_reengage`
10. `make investor-show-v8-live`

Do not skip V3-V7 when the branch is trying to establish real hardware truth. They are the evidence ladder.

## Runtime Rules To Respect

- structural motion and eye-area motion must be sequenced, not concurrent
- one structural family changes at a time
- one expressive unit changes at a time
- expressive groups release before structural return
- persistent public expressions are held eye-area states only
- unsupported expression names must resolve through explicit aliases or reject

These rules are enforced by the grounded expression catalog and the V8 motif runtime. The maintained architecture reference is [hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md).

## Failure Interpretation

Interpret failures in this order:

1. transport failure
   - `serial-doctor` or neutral write already unhealthy
2. runtime/catalog failure
   - unsupported name
   - illegal structural/expressive ordering
   - cue rejected before motion
3. family margin failure
   - most common current V8 issue
   - usually `upper_lids`, `lower_lids`, `eye_yaw`, `eye_pitch`, or `brows`

On the current head, most remaining V8 issues are eye-area margin problems, not sequencing bugs.

## Current Live References

Use these when another branch needs the latest maintained hardware truth instead of older historical runs:

- V3 maintained reference:
  - [performance-b84fcfc34f61](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-b84fcfc34f61)
  - `live_applied`
  - limiting family: `head_yaw`
  - minimum remaining margin: `-0.75%`
- V8 maintained full reference:
  - [performance-0d7a47c35d4f](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-0d7a47c35d4f)
  - `live_applied`
  - clean motifs:
    - `guarded_close_right`
    - `guarded_close_left`
  - main limiting families:
    - `lower_lids`
    - `upper_lids`
    - `eye_yaw`
    - `eye_pitch`
    - `brows`

## Post-Run

Artifacts are written to:

- `runtime/performance_runs/<run_id>/`

After any live run:

```bash
make investor-show-reset
PYTHONPATH=src uv run python -m embodied_stack.body.calibration disarm-live-motion
```

If the head is left in an unknown pose, do another neutral write before the next run.

## References

- [hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md)
- [body_motion_tuning.md](/Users/sonics/project/Blink-AI/docs/body_motion_tuning.md)
- [robot_head_hardware_and_serial_handoff.md](/Users/sonics/project/Blink-AI/docs/robot_head_hardware_and_serial_handoff.md)
- [investor_expressive_motion_v8_run_2026-04-11.md](/Users/sonics/project/Blink-AI/docs/investor_expressive_motion_v8_run_2026-04-11.md)
