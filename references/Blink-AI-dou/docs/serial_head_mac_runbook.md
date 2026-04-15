# Mac Serial Head Runbook

This runbook covers the Stage A bring-up path, the Stage B safe bench path, the Stage C runtime takeover path, the Stage D semantic behavior loop, and the Stage E validation workflow for the real Feetech/ST head on a Mac.

## Goal

Use one maintained Mac workflow to:

- confirm link and readback on the real head
- capture and validate live calibration
- run guarded small-motion bench tests
- exercise semantic actions through the same serial body stack used by the runtime
- package comparable Stage E validation evidence

Stage A inside this runbook is intentionally read-only. Motion begins only after Stage A is clean and a saved non-template calibration exists.

Current known-good bench setup:

- port: `/dev/cu.usbmodem5B790314811`
- baud: `1000000`
- profile: `src/embodied_stack/body/profiles/robot_head_v1.json`
- live calibration: `runtime/calibrations/robot_head_live_v1.json`

New motion-truth commands:

- `motion-config` reports profile defaults, calibration overrides, explicit demo overrides, effective live speed, and whether acceleration was actually applied or remains unverified on the current Mac transport path.
- `power-preflight` reads all 11 servos twice at idle and classifies startup power health before the first investor-show body cue.
- `usable-range` reports profile bounds, calibration bounds, suspicious neutrals, and the calibrated maximum-safe demo envelope that the standalone showcase will use.
- `range-demo --sequence servo_range_showcase_v1` runs the standalone maximum-safe servo showcase through the body layer and writes per-step motion artifacts.
- `servo-lab-*` commands provide the maintained Mac raw-joint tuning path for per-joint inspection, stepping, sweeps, speed override, and calibration write-back.

Servo Lab truth rules:

- speed override is real and visible in command results
- acceleration is surfaced truthfully from the active transport path
- Servo Lab bypasses the Stage B smoke clamp
- Servo Lab still respects calibrated hard limits and live-motion gates
- Windows FD remains fallback-only
- bus-wide `input_voltage` packet bits alone are not treated as a confirmed power fault on the maintained Mac runtime path
- confirmed late-show power faults now require corroborating reread and extended health evidence
- if the runtime confirms a real late-show body fault during a performance show, the warning is recorded in artifacts and `/performance`, but the show runner keeps issuing later live body cues unless some separate non-fault preview path is active

## Primary Commands

List ports:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration ports
```

Recommended doctor flow:

```bash
uv run blink-serial-doctor --ids 1-11 --auto-scan-baud
```

If multiple recommended `/dev/cu.*` devices exist, rerun with an explicit port:

```bash
uv run blink-serial-doctor \
  --port /dev/cu.usbmodem5B790314811 \
  --ids 1-11 \
  --auto-scan-baud
```

Direct calibration CLI equivalents:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  doctor --ids 1-11 --auto-scan-baud

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  read-position --ids 1-11

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  read-health --ids 1-11

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  suggest-env

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --profile src/embodied_stack/body/profiles/robot_head_v1.json \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  motion-config

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --profile src/embodied_stack/body/profiles/robot_head_v1.json \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  power-preflight

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --profile src/embodied_stack/body/profiles/robot_head_v1.json \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  usable-range --sequence servo_range_showcase_v1 --preset servo_range_showcase_joint_envelope_v1
```

Stage B bootstrap:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  capture-neutral --confirm-live-write --confirm-visual-neutral

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  set-range --joint upper_lid_left --raw-min 1547 --raw-max 2247 --confirm-mirrored true --in-place

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  validate-coupling --in-place

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  arm-live-motion

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  move-joint --joint head_yaw --delta 40
```

Mac Servo Lab examples:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  servo-lab-catalog

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  servo-lab-readback --joint head_yaw

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  servo-lab-move \
  --joint head_yaw \
  --reference-mode current_delta \
  --delta-counts 80 \
  --speed-override 100 \
  --confirm-live-write

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  servo-lab-sweep \
  --joint eye_pitch \
  --lab-min 1700 \
  --lab-max 2200 \
  --duration-ms 500 \
  --dwell-ms 200 \
  --confirm-live-write
```

Console path:

1. Open `/console`
2. Use `Body Runtime` to connect, arm, and confirm status
3. Use the `Servo Lab` subsection to select a joint, inspect current raw position, step from current, run sweeps, and save calibration updates

Repeat `set-range --confirm-mirrored true --in-place` for the lid and brow joints after bench confirmation, and use `set-range` on any joint that captured outside its inherited raw limits before rerunning `validate-coupling`.

Current bench note: the saved live calibration already includes a manual right-brow neutral correction. `brow_right.neutral` is now `2000` in `runtime/calibrations/robot_head_live_v1.json`, replacing the earlier too-low baseline that made the right brow appear stuck.

The neck pitch pair should now be treated as audit-sensitive. If `usable-range` flags either pitch joint as suspiciously close to a hard stop, do not accept a bold pitch demo until that neutral is validated or recaptured.

## Maximum-safe servo showcase

Use the standalone showcase when you need an honest proof of calibrated end-to-end joint travel on the real head without hiding behind investor-show pacing.

Dry run through the performance lane:

```bash
make servo-showcase-dry
```

Operator-facing live run:

```bash
make servo-showcase-live
```

Lower-level bench/calibration live run:

```bash
BLINK_CONFIRM_LIVE_WRITE=1 make servo-showcase-bench
```

The canonical sequence is `servo_range_showcase_v1`. It is intentionally body-first and silent by default, and it now drives each enabled joint from calibrated raw minimum to calibrated raw maximum before returning to neutral:

1. neutral settle
2. head yaw
3. neck servo A
4. neck servo B
5. eye yaw
6. eye pitch
7. upper lids
8. lower lids
9. brows
10. neutral recover

## Late-show fault triage

When a late investor-show cue looks wrong on hardware:

1. inspect `latest_command_audit` in the run artifact first
2. treat packet-level `input_voltage` bits as suspect until the confirmation reread agrees
3. if the confirmation path still shows bus-wide voltage bits plus persistent readback divergence or low extended-health voltage, accept it as a `confirmed_power_fault`
4. if a live show records confirmed fault warnings, inspect the artifact and `/performance` details before the next rehearsal; only re-arm for the next run if the live-motion lease itself expired or was cleared
5. if only `suspect_voltage_event` or `readback_implausible` appears, keep debugging choreography and bus/readback timing before blaming the power rail

## What Success Looks Like

- a recommended `/dev/cu.*` port is visible
- the working baud is detected
- IDs `1-11` reply consistently
- `read-position` succeeds for the expected IDs
- `read-health` returns position, speed, load, voltage, temperature, status bits, moving flag, and current when readable
- `runtime/serial/bringup_report.json` exists and includes request/response history

## Failure Order

Always debug in this order:

1. link
2. readback
3. calibration
4. single-joint motion
5. grouped motion
6. semantic motion
7. AI automation

For Stage A, stop after the first two.

## Stage A Failure Checklist

1. Port missing
   - cable or adapter unplugged
   - wrong USB/serial device
   - device node changed
2. Port open fails or reports busy
   - another tool still owns the device
   - macOS permissions or driver issue
3. Ping fails for every ID
   - wrong port
   - wrong baud
   - no bus power
4. Only some IDs reply
   - partial bus failure
   - one servo changed baud
   - wiring or power instability
5. `read-position` fails after ping succeeds
   - unstable live serial link
   - servo replies are incomplete or timing out
6. `read-health` is less stable than `read-position`
   - bus quality is not clean enough for larger reads
   - do not proceed to Stage B yet

## Artifact Review

Check these fields in `runtime/serial/bringup_report.json`:

- `available_ports`
- `chosen_port`
- `tested_bauds`
- `detected_baud`
- `responsive_ids`
- `position_reads`
- `health_reads`
- `transport_status`
- `request_response_history`
- `failure_summary`
- `next_steps`
- `suggested_env`

## Next Step

Only move to Stage B after Stage A is clean on live serial. Stage B starts by saving a non-template calibration under `runtime/calibrations/robot_head_live_v1.json`, then validating coupling, arming live motion, and limiting bench motion to the fixed Stage B smoke commands.

## Stage C Runtime Takeover

Launch the local runtime with the confirmed live serial env:

```bash
BLINK_RUNTIME_MODE=desktop_serial_body
BLINK_BODY_DRIVER=serial
BLINK_SERIAL_TRANSPORT=live_serial
BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
BLINK_SERVO_BAUD=1000000
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json
uv run blink-appliance
```

In Stage C, use `/console` to verify:

- transport mode, port, baud, and confirmed-live status
- calibration status and arm state
- live motion enabled versus blocked
- current `character_projection` outcome, including whether the head is following the shared character runtime or staying preview-only
- last body command outcome and latest command audit
- per-joint target versus readback and per-servo health

Use the console body controls in this order:

1. `Connect`
2. `Scan`
3. `Ping`
4. `Read Health`
5. `Arm`
6. one `Semantic Smoke`
7. `Write Neutral`
8. `Safe Idle`

If the serial link drops, the AI runtime should remain responsive while the console body panel becomes explicitly degraded.

## Stage D Semantic Behavior Loop

Use the same saved calibration and arm lease, but drive the head through semantic actions instead of raw joint moves:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  list-semantic-actions --smoke-safe-only

PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  semantic-smoke --action look_left --confirm-live-write
```

After a semantic smoke pass, record teacher feedback and optional tuning deltas:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  teacher-review \
  --action look_left \
  --review adjust \
  --proposed-tuning-delta '{"action_overrides":{"look_left":{"pose_offsets":{"eye_yaw":-0.05}}}}' \
  --apply-tuning
```

Stage D tuning artifacts live under `runtime/body/semantic_tuning/`. The `/console` body panel now fetches the semantic library, runs semantic smoke by canonical action name, and saves teacher reviews against the same live body state and audit trail.

The maintained runtime story is now:

- the character-presence runtime resolves one semantic intent
- the optional avatar shell and optional serial head both consume that same intent
- the serial head does not get a separate planner or separate social behavior tree
- when live-motion gates are not satisfied, the serial path must stay preview-only and report the block reason instead of faking motion

## Stage E Validation Tiers

Use these tiers in order:

1. always-on CI
   - `uv run pytest`
   - `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`
2. manual Mac bench suite
   - `uv run blink-serial-bench --transport live_serial ...`
3. opt-in live pytest
   - `BLINK_RUN_LIVE_SERIAL_TESTS=1 uv run pytest -m live_serial`
   - `BLINK_RUN_LIVE_SERIAL_TESTS=1 BLINK_RUN_LIVE_SERIAL_MOTION_TESTS=1 uv run pytest -m live_serial_motion`

Normal CI must stay in tier 1. Never make ordinary validation depend on powered hardware.

## Productized Mac Workflow

Maintained operator/developer flow:

1. connect USB serial and power
2. `make serial-doctor`
3. `PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport live_serial --port /dev/cu.usbmodem5B790314811 --baud 1000000 scan --ids 1-11 --auto-scan-baud`
4. `PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport live_serial --port /dev/cu.usbmodem5B790314811 --baud 1000000 read-position --ids 1-11`
5. `BLINK_CONFIRM_LIVE_WRITE=1 make serial-neutral`
6. `PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport live_serial --port /dev/cu.usbmodem5B790314811 --baud 1000000 --calibration runtime/calibrations/robot_head_live_v1.json semantic-smoke --action look_left --confirm-live-write`
7. `make serial-companion`
8. inspect `/console` and export the session bundle

For direct operator observation of every current movement and expression, use [serial_head_live_observation_sequence.md](/Users/sonics/project/Blink-AI/docs/serial_head_live_observation_sequence.md).

Maintained Stage E make targets:

- `make serial-doctor`
- `make serial-bench`
- `make serial-neutral`
- `make serial-companion`

`make serial-bench` and `make serial-neutral` require `BLINK_CONFIRM_LIVE_WRITE=1` on live hardware.

## Bench Evidence

The maintained bench suite writes one directory under `runtime/serial/bench_suites/<suite_id>/` with:

- `suite.json`
- `doctor_report.json`
- `scan_report.json`
- `position_report.json`
- `health_report.json`
- `calibration_snapshot.json`
- `motion_reports_index.json`
- `console_snapshot.json`
- `body_telemetry.json`
- `failure_summary.json`
- `request_response_history.json`

Check `suite.json` first. It records step order, per-step latency, stop step, metrics, referenced artifact paths, and the failure summary used for regression comparison.

## Failure Localization Matrix

| Layer | Symptom | First command to rerun | Artifact to inspect | Stop/Go rule |
| --- | --- | --- | --- | --- |
| Link | no `/dev/cu.*` port | `body-calibration ports` | `doctor_report.json` | stop until the expected adapter is visible |
| Link | port busy or open fails | `make serial-doctor` | `doctor_report.json` | stop until no other process owns the port |
| Link | wrong baud or no replies | `make serial-doctor` then `body-calibration scan --auto-scan-baud` | `doctor_report.json`, `scan_report.json` | stop until one baud clearly returns IDs |
| Link | ping or read-position timeout | `body-calibration read-position --ids 1-11` | `position_report.json`, `request_response_history.json` | stop until readback is stable |
| Motion | template calibration | `body-calibration capture-neutral --confirm-live-write --confirm-visual-neutral` | `calibration_snapshot.json`, live calibration file | stop until a saved non-template calibration exists |
| Motion | motion not armed | `body-calibration arm-live-motion` | `suite.json`, arm lease file | stop until the lease matches port, baud, and calibration |
| Motion | torque off or degraded after write | `body-calibration safe-idle` then `body-calibration bench-health` | `motion_reports_index.json`, `body_telemetry.json` | stop until health is stable again |
| Motion | out-of-range target | rerun the failing `move-joint` or `semantic-smoke` command | motion report JSON | stop until calibration ranges or semantic tuning are corrected |
| Motion | multi-servo power sag | `body-calibration safe-idle` then `body-calibration read-health --ids 1-11` | motion report JSON, `failure_summary.json` | stop immediately and do not continue motion |
| Expression | mirrored lids or brows wrong way | rerun one `semantic-smoke` action | motion report JSON, tuning file, teacher reviews | stop until the semantic tuning is corrected |
| Expression | neck pitch/roll looks unnatural | rerun `semantic-smoke --action nod_small` or `tilt_curious` | motion report JSON, tuning file | stop until neck weights are retuned |
| Expression | eye/lid coupling exaggerated | rerun `semantic-smoke --action look_up` | motion report JSON, tuning file | stop until lid coupling values are reduced |
| Expression | large readback drift | `body-calibration bench-health` | `body_telemetry.json`, motion report JSON | stop until drift is back inside the current safe tolerance |

## Windows FD Reference

If the Mac path is failing and you need a hardware sanity check, use [windows_fd_serial_reference.md](/Users/sonics/project/Blink-AI/docs/windows_fd_serial_reference.md).

Windows FD is reference-only. It is not the maintained development path, acceptance path, or artifact source of truth.
