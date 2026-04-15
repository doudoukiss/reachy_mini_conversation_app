# Investor Demo

## Demo Goal

Show that Blink-AI already has a credible local-first companion brain, and that optional embodiment is now grounded in real hardware capability rather than improvised semantic poses.

This remains a vertical proof path, not the product identity of the repo. The maintained investor embodiment surface is now:

- focused hardware evidence ladder: `investor_head_motion_v3` through `investor_neck_motion_v7`
- main expressive proof lane: `investor_expressive_motion_v8`
- separate max-safe hardware proof: `robot_head_servo_range_showcase_v1`

The old V1 and V2 investor shows are no longer maintained.

## Maintained Embodiment Surface

### V3-V7 evidence ladder

Use these to prove each family before running richer expressive behavior:

- `investor_head_motion_v3`
  - head yaw only
  - one atomic `body_range_demo`
  - `speed=100`, `acceleration=32`
- `investor_eye_motion_v4`
  - eye yaw and eye pitch
  - one atomic cue per family
- `investor_lid_motion_v5`
  - both-eye, left-eye, right-eye, and blink proof
  - investor-safe lid envelope, `300s` arm lease
- `investor_brow_motion_v6`
  - both-brow, left-brow, right-brow proof
  - investor-safe brow envelope
- `investor_neck_motion_v7`
  - tilt and pitch proven separately
  - protective neck preset, slower and more conservative than the raw showcase envelope

### V8 expressive proof

`investor_expressive_motion_v8` is the maintained expressive investor lane.

It uses:

- one atomic `body_expressive_motif` cue per segment
- structural motion first
- expressive units set, hold, and release one controlled action at a time
- expressive groups neutralize before structural return
- final full-neutral confirm

It is the maintained proof that sequential expression is achievable on the real head.

### Servo showcase

`robot_head_servo_range_showcase_v1` stays separate from investor proof. Use it for explicit range and bench validation, not as the investor expression surface.

## Hardware-Grounded Expression Rules

The body expression layer is now driven by the grounded catalog in [hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md).

The practical rules are:

- structural units are only head turn, neck pitch, and neck tilt
- expressive units are only eyes, lids, winks, and brows
- public held expressions are eye-area-only grounded states
- dynamic expression is authored as named motifs, not free-form composite poses
- structural and expressive groups must be sequenced, not changed concurrently
- unsupported public names must resolve through an explicit alias or reject

The machine-readable capability export is:

```bash
curl -sS http://127.0.0.1:8000/api/operator/body/expression-catalog | jq
```

Use that export as the source of truth for:

- supported structural units
- supported expressive units
- supported persistent states
- supported motifs
- evidence source
- safe tuning lane
- alias mapping

## Quick Commands

### Dry run

```bash
make investor-show-dry
```

### Main maintained expressive proof

```bash
make investor-show
```

### Virtual-body rehearsal

```bash
make investor-show-virtual
```

### Main live cue-smoke

```bash
make investor-show-cue-smoke BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

### Focused live evidence ladder

```bash
make investor-show-v3-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v4-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v5-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v6-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v7-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v8-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

### Separate range proof

```bash
make servo-showcase-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

## Recommended Live Order

Use this order when another branch connects to the head for the first time:

1. `make serial-doctor`
2. neutral write
3. `make investor-show-v3-live`
4. `make investor-show-v4-live`
5. `make investor-show-v5-live`
6. `make investor-show-v6-live`
7. `make investor-show-v7-live`
8. semantic smoke on grounded persistent states
9. motif cue-smokes
10. `make investor-show-v8-live`

This ordering matters. V3-V7 are the evidence ladder that establishes what the hardware can actually do before a branch attempts richer expression.

## Practical Hardware Truths

These are the main operating truths another branch should assume:

- the current reliable structural settings are conservative
- most readable expressivity comes from eyes, lids, brows, and sequencing quality
- the eye area is the primary margin-limited part of the head
- V8 failures are now usually eye-area family margin issues, not sequencing failures
- the old “chatty narration-timed body beats” model is not maintained
- one atomic animation per cue is the correct transport shape for this hardware

## Current Maintained Live References

- V3 head-yaw proof:
  - [performance-b84fcfc34f61](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-b84fcfc34f61)
  - `live_applied`
  - current limiting family: `head_yaw`
- V8 expressive motif proof:
  - [performance-0d7a47c35d4f](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-0d7a47c35d4f)
  - `live_applied`
  - clean motifs:
    - `guarded_close_right`
    - `guarded_close_left`
  - current limiting families:
    - `lower_lids`
    - `upper_lids`
    - `eye_yaw`
    - `eye_pitch`
    - `brows`

## References

- [hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md)
- [investor_show_runbook.md](/Users/sonics/project/Blink-AI/docs/investor_show_runbook.md)
- [body_motion_tuning.md](/Users/sonics/project/Blink-AI/docs/body_motion_tuning.md)
- [robot_head_hardware_and_serial_handoff.md](/Users/sonics/project/Blink-AI/docs/robot_head_hardware_and_serial_handoff.md)
- [investor_head_motion_v3_run_2026-04-11.md](/Users/sonics/project/Blink-AI/docs/investor_head_motion_v3_run_2026-04-11.md)
- [investor_expressive_motion_v8_run_2026-04-11.md](/Users/sonics/project/Blink-AI/docs/investor_expressive_motion_v8_run_2026-04-11.md)
