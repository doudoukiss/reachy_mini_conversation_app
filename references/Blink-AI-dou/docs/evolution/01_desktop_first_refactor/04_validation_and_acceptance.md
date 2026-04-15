# Validation and Acceptance

Use this file to keep the Codex work grounded and testable.

## Phase-level acceptance criteria

## Phase 1 — Desktop Embodiment Mode

### Must be true
- Blink-AI can run on one Mac as the main runtime
- typed input and at least one microphone path work
- webcam input is ingestible or mockable
- the app can run with no physical robot attached
- the existing brain memory/session behavior still works

### Validation
```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

## Phase 2 — Virtual Body and Expression Layer

### Must be true
- semantic actions compile into a virtual body state
- the virtual body can show neutral, blink, wink, gaze, and head motion
- safety clamps prevent impossible or out-of-range servo targets
- bodyless mode and virtual-body mode are both supported

### Validation
```bash
uv run pytest -q
PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport dry_run scan --ids 1-11
```

## Phase 3 — Feetech Serial Landing Zone

### Must be true
- protocol frames can be encoded and decoded
- read/write/sync write calls are tested against fixtures
- no-hardware dry-run mode is fully supported
- serial settings are configurable
- the driver fails safely when no device is connected

### Validation
```bash
uv run pytest -q
```

## Phase 4 — Demo Profiles and Evals

### Must be true
- there is a cloud-demo profile
- there is a local-dev profile
- there is a bodyless profile
- there is a virtual-body profile
- at least one investor demo path is replayable end-to-end
- outcomes are logged

### Validation
```bash
uv run pytest -q
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

## Behavior-specific checks

### Voice
- microphone unavailable -> typed fallback
- TTS unavailable -> text output still visible
- provider unavailable -> deterministic fallback still works

### Perception
- webcam unavailable -> fixture replay path still works
- perception unavailable -> dialogue still works honestly

### Body
- no body driver -> no crash
- virtual body -> visible motion plan
- serial body unavailable -> clean degraded behavior
- serial body powered off -> no unsafe retry storm

## Expression-specific checks

These should be regression tested:

- neutral pose
- look left
- look right
- look up
- look down
- blink
- wink left
- wink right
- attentive/listening pose
- surprised pose
- head tilt left
- head tilt right
- nod micro-animation

## Feetech-specific checks

- checksum generation
- low-byte-first packing
- write target position
- read current position
- sync write to multiple IDs
- sync read from multiple IDs
- torque off safe idle
- invalid reply handling
- timeout handling

## Documentation done criteria

The work is not done unless:
- `README.md` explains desktop mode clearly
- architecture docs reflect the new center of gravity
- the robot head profile is documented
- operator/demo instructions are updated
- future Jetson compatibility is explained without making it the current bottleneck
