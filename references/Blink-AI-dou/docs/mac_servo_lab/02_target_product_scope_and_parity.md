# 02. Target Product Scope and Windows-Parity Goals

## Product definition

Mac Servo Lab is an **operator-only calibration and characterization surface** for the embodied head.

It is not:

- a new planner
- a new product identity
- a replacement for semantic expressions
- a replacement for the normal investor-demo runtime

It is:

- a controlled way to inspect and drive every active servo from Mac
- the maintained Mac-native alternative to a Windows-only tuning experience
- a tool for learning the real motion envelope before adjusting shows and expressions

## Where it lives

### Primary surface

Add Servo Lab to the existing `/console` body panel.

This keeps the workflow coherent:

- connect hardware
- verify transport
- inspect body state
- run Servo Lab
- save calibration
- return to semantic motion and shows

### Secondary surface

Add CLI parity commands for headless bench use, regression tests, and scripted validation.

This should use the same backend helpers as the console, not a second independent implementation.

## Windows-parity feature goals

Mac Servo Lab should cover these operator needs.

| Capability | Target on Mac |
|---|---|
| Select one of 11 servo-backed joints | Yes |
| See raw min / max / neutral / current | Yes |
| Move to a specific raw target | Yes |
| Step by configurable increment | Yes |
| Step relative to current live position | Yes |
| Move directly to min / max / neutral | Yes |
| Run visible min↔max sweeps | Yes |
| Choose per-command speed | Yes |
| Choose per-command acceleration | Only if a verified transport path is implemented; otherwise show unsupported explicitly |
| Save adjusted calibration values | Yes |
| Use the same maintained Mac artifact flow | Yes |

## Non-negotiable design constraints

### 1. Preserve the semantic planner/body boundary

Raw servo lab controls must remain confined to:

- body layer
- desktop runtime
- operator service
- operator console
- calibration CLI

The AI planner must continue to speak in semantic actions, not raw servo IDs.

### 2. Preserve existing Stage B smoke behavior

Do **not** redefine the existing meanings of:

- `move-joint`
- `sync-move`
- `semantic-smoke`
- `safe-idle`
- `write-neutral`

Those flows are already used by runbooks and tests.

If Servo Lab needs more direct behavior, add a **parallel** lab path.

### 3. Do not hide unsupported acceleration

The current repo does not prove a working acceleration control path.

Therefore:

- if Codex can verify and implement a real acceleration write path from existing trusted project evidence, do it
- otherwise, keep the rest of Servo Lab moving forward and mark acceleration as unsupported in the UI and API

### 4. Stay inside calibrated hard limits

Servo Lab may bypass smoke-limit clamps, but it must **not** bypass calibrated or profiled hard limits.

### 5. Use the existing evidence system where possible

Servo Lab operations should reuse the existing motion report / audit machinery whenever feasible.

## User journeys

### Journey A: inspect one joint

1. Open `/console`
2. Connect and arm the body
3. Open Servo Lab
4. Select `head_yaw`
5. Read current live position
6. View calibrated min/max/neutral
7. Decide the next move

### Journey B: jog and characterize a joint

1. Select `eye_yaw`
2. Set step size to `20`
3. Press `Step -` twice
4. Press `Step +` once
5. Observe readback after each move
6. Move to `Min`
7. Move to `Neutral`

### Journey C: verify full calibrated range

1. Select `upper_lid_left`
2. Use the joint's calibrated min/max as lab min/max
3. Choose duration and speed
4. Run a bounded sweep
5. Confirm the actual visible envelope
6. Save revised lab bounds only if needed

### Journey D: refine calibration

1. Select `brow_right`
2. Read current position at visually correct neutral
3. Save current as neutral
4. Optionally tighten min/max
5. Save calibration
6. Rerun the same sweep

## What “done” looks like

Mac Servo Lab is complete when the operator can do, from Mac alone, what they previously needed Windows for:

- isolate any one of the 11 joints
- move it through its calibrated working range
- adjust speed honestly
- understand whether acceleration is actually supported
- save better calibration values
- return to semantic runtime work without switching hosts
