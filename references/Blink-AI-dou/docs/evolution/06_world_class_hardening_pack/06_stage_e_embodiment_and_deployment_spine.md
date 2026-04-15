# Stage E — Embodiment and Deployment Spine

## Objective

Keep the embodiment layer world-class by preserving semantic abstraction now, supporting safe live Feetech bring-up later, and making multi-host deployment credible when hardware returns.

This stage has **two lanes**:

- **Lane 1: pre-power / no live robot required**
- **Lane 2: powered-hardware bring-up**

Do Lane 1 now. Enter Lane 2 only when the power path is real and safe.

## Lane 1 — Pre-power work order

### Step 1 — Complete semantic embodiment discipline

Tasks:

1. Keep planner-facing actions purely semantic.
2. Expand and normalize the canonical action vocabulary:
   - gaze targets
   - attentiveness
   - listening/thinking states
   - blink styles
   - eyebrow and eyelid expressivity
   - nod / tilt / micro-reorientation
   - safe idle
3. Keep virtual-body preview authoritative for non-powered development.

### Step 2 — Make the head compiler richer and safer

Tasks:

1. Compile semantic actions into per-joint targets through the head profile.
2. Respect coupling rules.
3. Add rate limiting, clamping, and blend/transition rules.
4. Make safety envelopes explicit.

### Step 3 — Strengthen serial transport and health model

Tasks:

1. Keep `dry_run`, `fixture_replay`, and `live_serial` behind the same interface.
2. Strengthen health reporting for:
   - no port
   - baud mismatch
   - ID conflict
   - timeout
   - servo status errors
3. Preserve command-outcome logging.

### Step 4 — Prepare multi-host deployment spine

Tasks:

1. Keep the Mac/local runtime as default.
2. Define a clean later path for:
   - MacBook local appliance
   - Mac Studio higher-capacity brain host
   - Jetson/edge thin device bridge
3. Keep the edge deterministic and thin.
4. Keep contracts identical across in-process, serial, and future tethered transport.

## Lane 2 — Powered-hardware bring-up

Only start after safe external power and serial setup are confirmed.

### Step 5 — Live Feetech bring-up

Tasks:

1. Confirm live baud on the shared bus.
2. Confirm ID map and neutral pose.
3. Validate `PING`, `READ`, `WRITE`, `SYNC WRITE`, and `SYNC READ` paths.
4. Validate safe torque handling.
5. Validate calibration writes only under explicit operator flow.

### Step 6 — Live calibration workflow

Tasks:

1. Confirm each joint’s min/max and neutral on real hardware.
2. Confirm mirrored eyelid and brow semantics.
3. Confirm pitch/tilt coupling behavior.
4. Confirm safe speed and acceleration ceilings.
5. Persist calibration with explicit provenance.

### Step 7 — Live embodiment regression suite

Tasks:

1. Run expression/gaze fixtures against live hardware.
2. Log command vs readback outcomes.
3. Surface transport errors in operator UI.
4. Keep `safe_idle` always available.

## Feetech-specific rules

For this stage, preserve these rules in code and docs:

- STS/SMS-style data is low-byte-first for multi-byte fields
- shared bus must use unique servo IDs
- support autoscan for both `115200` and `1000000`
- keep torque switch, target position, running speed, and current position behind semantic/body driver logic
- prefer sync write/read for coordinated behavior where appropriate

## Suggested file targets

- `src/embodied_stack/body/semantics.py`
- `src/embodied_stack/body/compiler.py`
- `src/embodied_stack/body/driver.py`
- `src/embodied_stack/body/serial/protocol.py`
- `src/embodied_stack/body/serial/transport.py`
- `src/embodied_stack/body/serial/health.py`
- `src/embodied_stack/body/calibration.py`
- `src/embodied_stack/body/profiles/robot_head_v1.json`
- `src/embodied_stack/edge/` for later thin bridge hardening only

## Definition of done

- semantic embodiment remains fully separated from raw servo logic
- pre-power development is strong through virtual and dry-run paths
- live bring-up path is safe and explicit once power returns
- deployment spine stays compatible with Mac Studio / Jetson future split
- operator surfaces tell the truth about embodiment capability and health

## Validation

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
uv run body-calibration --help
```
