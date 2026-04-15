# 04. Console UI and CLI Plan

## Console is the primary Servo Lab surface

Add a **Servo Lab** subsection to the existing `Body Runtime` panel in `/console`.

This should sit next to the existing semantic controls, not replace them.

## Console layout

### Section A: Lab status

Show:

- transport mode
- port
- baud
- confirmed live
- calibration status
- armed state
- speed override support
- acceleration support state

This needs to be visible before the operator starts moving anything.

### Section B: Joint selector

Add a selector listing all 11 joints by canonical name:

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

When the operator selects a joint, show:

- servo ID(s)
- current raw position
- neutral
- raw min
- raw max
- positive direction
- coupling hint
- any readback or calibration warnings

### Section C: Motion controls

Add inputs for:

- `reference mode`
  - absolute raw
  - neutral delta
  - current delta
- `target raw`
- `step size`
- `lab min`
- `lab max`
- `duration ms`
- `speed override`
- `acceleration override`

### Section D: Motion buttons

Add buttons for:

- `Read Current`
- `Move`
- `Step -`
- `Step +`
- `Go Min`
- `Go Max`
- `Go Neutral`
- `Sweep Min↔Max`
- `Write Neutral`
- `Safe Idle`

If acceleration is unsupported, the acceleration input must be disabled or visually marked unsupported.

### Section E: Calibration actions

Add calibration buttons for:

- `Save Current as Neutral`
- `Save Lab Range to Calibration`

If a mirrored joint family is being edited, the UI should expose a mirrored confirmation control when needed.

### Section F: Operator feedback

Show:

- last Servo Lab result
- effective target
- clamp notes
- effective speed
- acceleration status
- readback after move
- latest motion report path

## Console implementation notes

### HTML and JS additions

Update:

- `src/embodied_stack/brain/static/console.html`
- `src/embodied_stack/brain/static/console.js`

### Suggested JS helpers

Add helpers such as:

- `refreshServoLabCatalog()`
- `renderServoLabCatalog()`
- `renderServoLabSelection()`
- `servoLabAction(path, payload)`
- `readServoLabCurrent()`
- `moveServoLabJoint()`
- `stepServoLabJoint(direction)`
- `sweepServoLabJoint()`
- `saveServoLabCalibration()`

Do not overload the existing generic semantic `bodyAction()` flow for every new control if that would make the UI state harder to maintain.

## CLI parity

Add a CLI mirror for headless use and regression testing.

### Recommended commands

Add commands such as:

- `servo-lab-catalog`
- `servo-lab-readback`
- `servo-lab-move`
- `servo-lab-sweep`
- `servo-lab-save-calibration`

### Why new commands are better than mutating old ones

The existing `move-joint` command is a Stage B smoke tool with stable semantics and tests.

Servo Lab should have its own command family rather than silently changing Stage B behavior.

## Suggested CLI examples

### Show the joint catalog

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration   --transport live_serial   --port /dev/cu.usbmodemXXXX   --baud 1000000   --calibration runtime/calibrations/robot_head_live_v1.json   servo-lab-catalog
```

### Read one joint

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration   --transport live_serial   --port /dev/cu.usbmodemXXXX   --baud 1000000   --calibration runtime/calibrations/robot_head_live_v1.json   servo-lab-readback --joint head_yaw
```

### Current-relative step

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration   --transport live_serial   --port /dev/cu.usbmodemXXXX   --baud 1000000   --calibration runtime/calibrations/robot_head_live_v1.json   servo-lab-move   --joint head_yaw   --reference-mode current_delta   --delta-counts 20   --speed-override 100   --duration-ms 500
```

### Min↔max sweep

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration   --transport live_serial   --port /dev/cu.usbmodemXXXX   --baud 1000000   --calibration runtime/calibrations/robot_head_live_v1.json   servo-lab-sweep   --joint eye_yaw   --cycles 2   --duration-ms 450   --dwell-ms 250   --speed-override 90
```

## UI behavior requirements

### Preserve operator trust

The UI must always show the truth about:

- what joint is selected
- what command was requested
- what command was actually executed
- whether speed was clamped
- whether acceleration is unsupported
- what the readback says after the move

### Make coupling understandable

For `head_pitch_pair_a` and `head_pitch_pair_b`, the UI should explain that:

- raw single-joint moves are allowed in Servo Lab
- paired A/B motion is how pitch is normally created
- isolated A or B moves can create tilt-like behavior

That keeps the operator from mistaking coupling behavior for servo failure.

## Nice-to-have, but not required in the first pass

These are good follow-ups, but they should not block the first complete Servo Lab:

- paired/group presets in the UI
- a tiny readback chart
- named lab presets
- browser-local persistence of the last used duration/speed/step values
