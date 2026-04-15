# 05. Motion, Calibration, and Operator Rules

## Servo Lab is less conservative than Stage B, but not reckless

The goal is to expose the real usable envelope on Mac, not to remove all protection.

## Hard rules

### Rule 1: Servo Lab never bypasses calibrated hard limits

Allowed:

- bypassing Stage B smoke limits
- using the full saved calibration range
- using operator-defined lab subranges inside that calibration range

Not allowed:

- writing outside saved calibration limits
- writing outside profile limits if no saved calibration exists

### Rule 2: live writes still require the normal live gates

Before a live Servo Lab move, require:

- confirmed live transport
- healthy readback
- saved non-template calibration
- active arm lease

This preserves the maintained live-write discipline of the repo.

### Rule 3: current-relative movement is the default lab stepping mode

The default jog behavior in Servo Lab should be:

```text
target = current_position + step
```

This is what operators expect from a real servo lab.

Neutral-relative movement should still exist, but as an explicit alternate mode.

### Rule 4: speed is real, acceleration must be truthful

Speed override is part of the existing transport payload and should be implemented.

Acceleration must only be implemented if there is a verified write path. Otherwise, the operator must see an explicit unsupported state.

## Joint-specific guidance

### `head_yaw`

- independent single-joint control
- ideal first test case for Servo Lab
- should support:
  - go min
  - go max
  - current-relative step
  - sweep

### `head_pitch_pair_a` and `head_pitch_pair_b`

- raw single-joint control should be allowed in Servo Lab
- UI must explain that:
  - pair motion creates pitch
  - isolated motion changes tilt contribution
- do not silently convert single-joint requests into pair requests

### Lid joints

- individual lid joints should remain individually selectable
- mirrored semantics must be shown clearly in the UI
- raw lab control is okay because this is an operator tool, not semantic animation

### Brow joints

- same rule as lids
- the right brow should be treated according to calibration, not assumed symmetry

## Lab bounds model

Each move should resolve against two layers of bounds.

### Hard bounds

These come from:

1. saved calibration, if present
2. otherwise the profile

### Lab bounds

These are operator-chosen temporary bounds inside the hard bounds.

Examples:

- use full calibrated min/max
- narrow a sweep to a smaller visual band
- test only the top half of a brow range

### Behavior

- if no lab bounds are provided, default to hard bounds
- if provided lab bounds exceed hard bounds, clamp them and report the clamp

## Sweep rules

A Servo Lab sweep should be bounded, legible, and report-rich.

### Minimum v1 sequence

For one cycle:

1. read current
2. move to lab min
3. dwell
4. move to lab max
5. dwell
6. optionally return to neutral

### Readback requirements

Record readback:

- before the sweep
- after each leg if affordable
- after the final recovery

### Dwell guidance

Do not collapse the sequence into back-to-back writes with no visible pause.

This is specifically important because the current live animation path is not a reliable substitute for a lab sweep.

## Calibration save rules

### Save current as neutral

When the operator chooses this action:

- read the current live position
- update that joint's neutral in the existing calibration record
- preserve provenance metadata
- write the calibration back through the existing record format

### Save lab range

When the operator chooses this action:

- write `raw_min` / `raw_max` for the selected joint
- keep values inside hard limits
- require mirrored confirmation where existing calibration logic expects it

## Report and audit rules

Every Servo Lab operation should generate an auditable record.

### Required metadata

- operator request
- effective execution parameters
- clamp notes
- readback before and after
- health snapshot
- calibration path
- transport summary
- report path

### Keep exports coherent

If the repo already exports body motion reports and audits, Servo Lab should flow into the same evidence story rather than creating a disconnected second system.

## Failure behavior

If a Servo Lab operation fails, the operator needs a clear recovery path.

### Preferred recovery controls

- `Go Neutral`
- `Write Neutral`
- `Safe Idle`

### Failure messaging should distinguish

- transport/readback failure
- arm failure
- calibration missing/template
- clamp to bounds
- unsupported acceleration
- health degradation after motion
