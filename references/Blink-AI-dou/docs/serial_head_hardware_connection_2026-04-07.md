# Serial Head Hardware Connection Record

Date: 2026-04-07

## Purpose

This note records the verified live serial connection state for the powered robot head before any Stage B calibration capture or motion work.

This checkpoint is intentionally read-only.

This file is now a historical Stage A checkpoint record. Later stages have since been completed on the same hardware path. For the maintained live workflow, use [serial_head_mac_runbook.md](/Users/sonics/project/Blink-AI/docs/serial_head_mac_runbook.md). For the current direct-observation workflow, use [serial_head_live_observation_sequence.md](/Users/sonics/project/Blink-AI/docs/serial_head_live_observation_sequence.md).

## Safety Boundary

The following were allowed for this verification:

- `body-calibration ports`
- `blink-serial-doctor`
- `body-calibration doctor`
- `body-calibration read-position`
- `body-calibration read-health`

The following were explicitly not run:

- `write-neutral`
- `capture-neutral`
- torque enable or neutral write commands
- semantic motion commands
- runtime takeover or AI-driven motion commands

## Robot Configuration Source

Robot-specific hardware notes now live in [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md).

Key confirmed details from that file:

- shared-bus auto-scan target baud: `1000000`
- servo count: `11`
- servo model: `STS3032`
- neutral position reference: `2047`

## Confirmed Mac Serial Link

- chosen port: `/dev/cu.usbmodem5B790314811`
- transport mode: `live_serial`
- working baud: `1000000`
- non-working baud tested: `115200`
- requested IDs: `1-11`
- responsive IDs at `1000000`: `1-11`

Port metadata from the successful report:

- description: `USB Single Serial`
- USB VID:PID: `1A86:55D3`
- serial number: `5B79031481`
- location: `0-1.1`

## Verification Sequence

The live verification was done in this order:

1. `PYTHONPATH=src uv run python -m embodied_stack.body.calibration ports`
2. `uv run blink-serial-doctor --port /dev/cu.usbmodem5B790314811 --baud 1000000 --ids 1-11 --report runtime/serial/bringup_1000000.json`
3. `uv run blink-serial-doctor --port /dev/cu.usbmodem5B790314811 --baud 115200 --ids 1-11 --report runtime/serial/bringup_115200.json`
4. `uv run blink-serial-doctor --port /dev/cu.usbmodem5B790314811 --ids 1-11 --auto-scan-baud --report runtime/serial/bringup_report.json`
5. `PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport live_serial --port /dev/cu.usbmodem5B790314811 --baud 1000000 read-position --ids 1-11`
6. `PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport live_serial --port /dev/cu.usbmodem5B790314811 --baud 1000000 read-health --ids 1-11`

An overlapping concurrent probe attempt happened earlier in the session and was discarded because multiple simultaneous opens against the same serial device can corrupt results. The sequential runs above are the valid checkpoint.

## Results

### Explicit `1000000`

- all IDs `1-11` responded
- `detected_baud` = `1000000`
- `failure_summary` was empty
- transport status was healthy
- live readback was confirmed

### Explicit `115200`

- no IDs responded
- `detected_baud` = `null`
- result pattern was full timeout across all IDs
- this baud should not be used for this head in the current wiring/setup

### Auto-scan

- auto-scan selected `1000000`
- all IDs `1-11` responded
- `failure_summary` was empty
- this matched the robot-specific note in [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md)

## Read-Only Live State Snapshot

Position reads captured during the successful `1000000` run:

- ID 1: `1665`
- ID 2: `1372`
- ID 3: `2681`
- ID 4: `2050`
- ID 5: `2048`
- ID 6: `2045`
- ID 7: `2006`
- ID 8: `2148`
- ID 9: `2073`
- ID 10: `2094`
- ID 11: `2205`

Health observations from the successful live read:

- voltage was stable at roughly `58-61`
- temperature was stable at roughly `25-30`
- torque was disabled
- `moving` was `false`
- current was `0`

## Connection Gate Status

The Stage A "connected enough" gate was met in a read-only way:

- chosen port was explicitly confirmed
- one baud was clearly detected
- IDs `1-11` replied consistently
- `read-position` worked
- `read-health` worked
- the final auto-scan report had an empty `failure_summary`

This means the hardware link was confirmed without sending any motion or calibration write.

## Suggested Runtime Environment

From the successful doctor report:

```bash
BLINK_RUNTIME_MODE=desktop_serial_body
BLINK_BODY_DRIVER=serial
BLINK_SERIAL_TRANSPORT=live_serial
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json
BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
BLINK_SERVO_BAUD=1000000
```

These values should not be treated as permission to move the robot. They only record the verified live link settings.

## Related Artifacts

- [bringup_report.json](/Users/sonics/project/Blink-AI/runtime/serial/bringup_report.json)
- [bringup_1000000.json](/Users/sonics/project/Blink-AI/runtime/serial/bringup_1000000.json)
- [bringup_115200.json](/Users/sonics/project/Blink-AI/runtime/serial/bringup_115200.json)
- [serial_head_mac_runbook.md](/Users/sonics/project/Blink-AI/docs/serial_head_mac_runbook.md)

## Next-Step Constraint

Do not proceed to Stage B motion or live calibration writes unless that work is explicitly requested and stays within the runbook safety order:

1. link
2. readback
3. calibration
4. single-joint motion
5. grouped motion
6. semantic motion
7. AI automation
