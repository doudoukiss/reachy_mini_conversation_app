# 01. Current State and Gap Analysis

## What the repo already supports on Mac

The current Mac path already supports real serial control and real bench workflows.

### Hardware and calibration ground truth

The current checked-in hardware truth is [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md), backed by `runtime/calibrations/robot_head_live_v1.json`. It describes an 11-servo STS3032 head with these controllable joints:

- `head_yaw`
- `head_pitch_pair_a`
- `head_pitch_pair_b`
- `lower_lid_left`
- `upper_lid_left`
- `lower_lid_right`
- `upper_lid_right`
- `eye_pitch`
- `eye_yaw`
- `brow_left`
- `brow_right`

The same 11 joints are modeled in `src/embodied_stack/body/profiles/robot_head_v1.json`.

### Existing Mac CLI coverage

`src/embodied_stack/body/calibration.py` already exposes:

- `ports`
- `doctor`
- `arm-live-motion`
- `disarm-live-motion`
- `ping`
- `read-position`
- `read-health`
- `bench-health`
- `list-semantic-actions`
- `semantic-smoke`
- `teacher-review`
- `move-joint`
- `sync-move`
- `torque-on`
- `torque-off`
- `safe-idle`
- `write-neutral`
- `capture-neutral`
- `set-range`
- `validate-coupling`
- `save-calibration`

That means the Mac stack already has enough low-level capability to become a full servo lab.

### Existing console coverage

`src/embodied_stack/brain/static/console.html` and `console.js` already expose a live body panel with:

- connect
- disconnect
- scan
- ping
- read health
- arm
- disarm
- write neutral
- semantic smoke
- safe idle
- teacher review

The API routes already exist in `src/embodied_stack/brain/app.py`, and the operator service/runtime already proxy them through the body driver.

## What is missing

The missing layer is a **true operator-facing raw servo lab**.

### Missing capability 1: direct joint lab UI

There is no console surface for:

- choosing one of the 11 joints explicitly
- reading its live raw position in a dedicated lab view
- entering target raw values
- setting lab min/max bounds
- stepping by a configurable amount
- sweeping a joint from min to max and back

### Missing capability 2: true current-relative step mode

The current CLI `move-joint` path is not a real “step from where the joint currently is” tool.

In `src/embodied_stack/body/serial/bench.py`, `resolve_joint_targets()` computes:

- `requested_value = neutral + delta` when `--delta` is used

That means repeated `--delta 20` commands do **not** accumulate from the current live position. They repeatedly target `neutral + 20`.

This is fine for a smoke-safe bench move. It is not fine for a servo lab.

### Missing capability 3: the current Mac joint move is intentionally too small

`motion_smoke_limit()` in `src/embodied_stack/body/serial/bench.py` clamps:

- head and eye joints to `±100`
- lids and brows to `±60`

This is much smaller than the calibrated raw ranges described in [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md) and `robot_head_v1.json`.

That means the existing Stage B move path is intentionally not showing the true usable envelope.

### Missing capability 4: speed is global, not operator-controlled

The low-level transport payload already includes:

- position
- duration
- speed

`build_target_position_payload()` in `src/embodied_stack/body/serial/protocol.py` writes exactly those values.

But `FeetechBodyBridge._send_frame()` currently resolves speed from the global safe speed path only:

- calibration `safe_speed`
- else profile `safe_speed`
- then clamp by `safe_speed_ceiling`

So Mac has real speed in the transport path, but not real **per-command operator speed override**.

### Missing capability 5: acceleration is modeled but not actually wired through

`safe_acceleration` exists in:

- `HeadProfile`
- `HeadCalibrationRecord`
- `robot_head_v1.json`

However, the actual serial write path uses only:

- position
- duration
- speed

There is no verified acceleration register or write path in the current serial transport/protocol implementation.

So the current repo state is:

- speed: partially real but not exposed per command
- acceleration: modeled in config, **not** implemented end-to-end

### Missing capability 6: no Windows-style sweep or min/max exercise path

There is currently no first-class operator flow on Mac to:

- choose a joint
- choose min and max
- choose step size
- choose speed
- run a visible min↔max sweep
- save the chosen values back into calibration

## What this means

The right conclusion is **not** that Mac cannot do what Windows does.

The right conclusion is:

> The Mac stack already has the transport, runtime, calibration, audit, and console foundations.  
> It just still lacks a true operator-facing servo lab layer.

## Required design direction

The fix is **not** to rewrite the whole embodiment stack.

The fix is to add a parallel operator-only layer that:

- leaves semantic planner/body boundaries intact
- leaves Stage B smoke tools intact
- adds raw servo lab tools on top of the existing driver/runtime/operator-console path
- exposes real current-relative stepping and sweep behavior
- uses calibrated hard limits instead of smoke limits
- exposes speed honestly
- exposes acceleration only if a verified hardware path can be implemented

## Success condition

After the Mac Servo Lab ships, the operator should be able to answer these questions on Mac without touching Windows:

1. Which of the 11 joints am I controlling right now?
2. What is its live raw position?
3. What are its calibrated min, max, and neutral values?
4. Can I step it from its current position?
5. Can I drive it to min, max, and neutral directly?
6. Can I sweep it through its calibrated working envelope?
7. Can I override speed for this move?
8. If acceleration is not truly implemented, does the UI say so explicitly instead of pretending?
9. Can I save revised min/max/neutral values back to calibration?
