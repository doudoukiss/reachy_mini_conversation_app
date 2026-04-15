# 03. Backend, Transport, and API Plan

## High-level architecture

Build Servo Lab as a **parallel operator-only path** on top of the existing body stack.

The existing chain already works:

- body transport
- body bridge
- body driver
- desktop runtime
- operator service
- `/api/operator/body/*`
- `/console`

Servo Lab should reuse this chain.

## Do not overload the Stage B smoke helpers

The existing Stage B helpers have valuable semantics and tests.

Do not mutate them into lab behavior.

### Keep unchanged

- `resolve_joint_targets()` in `src/embodied_stack/body/serial/bench.py`
- `motion_smoke_limit()`
- `move-joint`
- `sync-move`

### Add new helpers instead

Create a new module, for example:

- `src/embodied_stack/body/servo_lab.py`

This module should own:

- joint catalog assembly
- current-position reads for lab operations
- current-relative target resolution
- lab-bound clamping
- sweep planning
- calibration write-back helpers
- operator-facing metadata for the UI

## Proposed typed request models

Add new request models to `src/embodied_stack/shared/contracts/operator.py`.

Keep response shape as `BodyActionResult` unless there is a compelling reason to add a second response type.

### Suggested request models

#### `BodyServoLabMoveRequest`

Fields:

- `joint_name: str`
- `reference_mode: Literal["absolute_raw", "neutral_delta", "current_delta"]`
- `target_raw: int | None = None`
- `delta_counts: int | None = None`
- `lab_min: int | None = None`
- `lab_max: int | None = None`
- `duration_ms: int = 600`
- `speed_override: int | None = None`
- `acceleration_override: int | None = None`
- `note: str | None = None`

#### `BodyServoLabSweepRequest`

Fields:

- `joint_name: str`
- `lab_min: int | None = None`
- `lab_max: int | None = None`
- `cycles: int = 1`
- `duration_ms: int = 600`
- `dwell_ms: int = 250`
- `speed_override: int | None = None`
- `acceleration_override: int | None = None`
- `return_to_neutral: bool = True`
- `note: str | None = None`

#### `BodyServoLabCalibrationRequest`

Fields:

- `joint_name: str`
- `save_current_as_neutral: bool = False`
- `raw_min: int | None = None`
- `raw_max: int | None = None`
- `confirm_mirrored: bool | None = None`

#### `BodyServoLabReadbackRequest`

Fields:

- `joint_name: str | None = None`
- `include_health: bool = True`

## Driver-layer responsibilities

Add Servo Lab methods to the serial-capable body driver and runtime gateway.

### Suggested driver methods

In `src/embodied_stack/body/driver.py` add methods such as:

- `servo_lab_catalog()`
- `servo_lab_readback(joint_name=None, include_health=True)`
- `servo_lab_move(...)`
- `servo_lab_sweep(...)`
- `servo_lab_save_calibration(...)`

### Suggested runtime/operator methods

Mirror these through:

- `src/embodied_stack/desktop/runtime.py`
- `src/embodied_stack/brain/operator/service.py`
- `src/embodied_stack/brain/app.py`

### Suggested API routes

Add routes like:

- `GET /api/operator/body/servo-lab/catalog`
- `POST /api/operator/body/servo-lab/readback`
- `POST /api/operator/body/servo-lab/move`
- `POST /api/operator/body/servo-lab/sweep`
- `POST /api/operator/body/servo-lab/save-calibration`

Keep them operator-only and under the existing body namespace.

## Joint catalog payload

The catalog response should expose enough information for the UI to be self-contained.

For each joint include:

- `joint_name`
- `servo_ids`
- `positive_direction`
- `neutral`
- `raw_min`
- `raw_max`
- `current_position` if readable
- `readback_error` if not readable
- `coupling_group`
- `coupling_hint`
- `supports_absolute_move`
- `supports_current_delta`
- `supports_sweep`
- `speed_override_supported`
- `acceleration_supported`

### Coupling hints matter

The UI must tell the operator the truth.

Examples:

- `head_pitch_pair_a`: single-joint raw+ means right tilt contribution; paired A/B motion creates head pitch
- `head_pitch_pair_b`: single-joint raw- means left tilt contribution; paired A/B motion creates head pitch
- lids and brows are mirrored in semantic meaning
- eye pitch has lid-follow implications in semantic mode, but Servo Lab is raw/operator mode

## Speed implementation

The transport already supports speed in the target-position payload.

Codex should thread speed through honestly.

### Required code change

Extend the body bridge path so a Servo Lab request can pass a per-command speed override into frame writes.

Possible implementation:

- add `speed_override: int | None = None` to `FeetechBodyBridge.execute_joint_targets()`
- add `speed_override: int | None = None` to `_send_frame()`
- compute `effective_speed` as:

```text
requested override if present
else calibration safe_speed if present
else profile safe_speed
then clamp by profile safe_speed_ceiling if present
```

### Reporting requirement

Every move/sweep report must include:

- `requested_speed_override`
- `effective_speed`
- `speed_clamped: bool`
- `speed_clamp_reason` if clamped

## Acceleration implementation policy

Do not invent acceleration behavior.

### Required approach

1. Search the current repo for a verified acceleration register/write path.
2. If a verified path exists and can be implemented safely, wire it through end-to-end.
3. If not, return:

- `acceleration_supported = false`
- `requested_acceleration_override` in the payload
- `effective_acceleration = null`
- `acceleration_status = "unsupported_on_current_transport"`

The UI must render that state clearly.

### Why this matters

A fake acceleration control is worse than no control because it makes bench conclusions untrustworthy.

## Target resolution rules for Servo Lab

Servo Lab must **not** use `motion_smoke_limit()`.

Instead use this clamp order:

1. determine hard limits from saved calibration, else profile
2. determine optional operator lab bounds (`lab_min`, `lab_max`)
3. ensure lab bounds are inside hard limits
4. compute requested target from:
   - absolute raw target
   - neutral delta
   - current delta
5. clamp only to lab bounds / hard limits
6. report any clamp explicitly

## Readback and current-relative stepping

For `current_delta` moves, Servo Lab must read live position first and then compute:

```text
target = current_position + delta_counts
```

This is the key behavioral difference from the existing Stage B `move-joint` flow.

## Sweep implementation

Do not implement sweep by reusing the existing compiled-animation path.

The current live animation path has known visibility problems when multiple frames are sent back-to-back.

### Instead

Implement Servo Lab sweep as an explicit sequence of bench writes with real dwell:

1. read current
2. move to `lab_min`
3. dwell
4. move to `lab_max`
5. dwell
6. repeat for requested cycles
7. optionally return to neutral

Each substep should produce:

- target used
- readback after settle
- clamp notes
- health snapshot if requested

## Calibration write-back

Servo Lab should support calibration edits from the operator surface.

### Supported actions

- save current position as neutral for one joint
- save raw min/max for one joint
- write both into the existing calibration file
- preserve provenance and notes
- require mirrored confirmation when editing mirrored lid/brow pairs if the existing calibration flow expects it

### Important rule

Reuse the calibration record format already in the repo. Do not invent a second calibration file format.

## Reporting and evidence

Prefer reusing the existing motion report machinery.

### Recommended path

- keep using `runtime/serial/motion_reports/`
- give Servo Lab operations distinct command families such as:
  - `servo_lab_move`
  - `servo_lab_sweep`
  - `servo_lab_save_calibration`

### Required report metadata

Each report should include:

- joint name
- reference mode
- requested target or delta
- effective target
- hard min/max
- effective lab min/max
- requested/effective speed
- requested/effective acceleration
- readback before
- readback after
- settle and dwell times
- health snapshot
- clamp notes
- calibration path
- operator note if provided

This keeps export and audit flows coherent with the rest of the body stack.
