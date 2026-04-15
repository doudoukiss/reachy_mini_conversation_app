# 06. Execution Sequence and Acceptance

## Implementation order

Codex should implement this in the following order.

## Phase 1: contracts and helper module

1. Add Servo Lab request models in `src/embodied_stack/shared/contracts/operator.py`
2. Create a new helper module, for example `src/embodied_stack/body/servo_lab.py`
3. Add joint-catalog assembly helpers
4. Add hard-bound and lab-bound resolution helpers
5. Add current-relative target computation helpers
6. Add sweep planning helpers
7. Add payload builders for UI/API responses

### Acceptance gate

- unit tests prove the catalog contains all 11 joints
- current-relative target math is correct
- hard-bound and lab-bound clamps are reported explicitly

## Phase 2: bridge and driver plumbing

1. Extend the bridge write path for per-command speed override
2. Keep speed clamped by the existing safe ceiling rules
3. Add acceleration capability reporting
4. Do **not** fake acceleration if the write path cannot be verified
5. Add driver methods for Servo Lab catalog, readback, move, sweep, and calibration save
6. Reuse motion report generation where possible

### Acceptance gate

- a Servo Lab move can execute without the Stage B smoke-limit clamp
- speed override reaches the effective write path
- unsupported acceleration is reported honestly
- existing Stage B tests still pass unchanged

## Phase 3: desktop runtime, operator service, and API routes

1. Add desktop-runtime gateway methods
2. Add operator-service proxy methods
3. Add `/api/operator/body/servo-lab/*` routes
4. Keep them operator-only and body-scoped

### Acceptance gate

- operator API tests can call the new routes successfully
- existing body API routes still behave the same

## Phase 4: console UI

1. Add the Servo Lab subsection to `console.html`
2. Add the new JS helpers to `console.js`
3. Render catalog, selection metadata, and current readback
4. Implement move, step, sweep, and calibration-save actions
5. Show effective speed and acceleration support status clearly

### Acceptance gate

- `/console` contains the new Servo Lab controls
- UI state updates after move and sweep calls
- the operator can select any of the 11 joints

## Phase 5: CLI parity

1. Add new Servo Lab CLI commands
2. Keep them separate from Stage B smoke commands
3. Reuse the same body/servo-lab helpers as the console path

### Acceptance gate

- CLI can list the catalog
- CLI can perform current-relative step
- CLI can run a bounded sweep
- CLI can write calibration changes

## Phase 6: docs and validation

1. Add concise docs explaining Servo Lab
2. Update the Mac runbook to point operators to Servo Lab instead of Windows for normal tuning
3. Keep `docs/windows_fd_serial_reference.md` as fallback-only documentation
4. Add targeted tests and regression coverage

### Acceptance gate

- docs describe the truth:
  - Mac Servo Lab is the primary maintained tuning path
  - Windows remains fallback-only
  - acceleration is either implemented and tested or explicitly unsupported

## Test plan

## Unit tests

Add tests for:

- joint catalog construction
- current-relative step math
- lab-bound clamp behavior
- speed override clamping
- acceleration unsupported state
- calibration save payloads

## Driver tests

Add tests for:

- Servo Lab move path bypasses smoke-limit logic
- Servo Lab still respects calibration hard bounds
- sweep writes multiple visible steps with dwell metadata
- report payload contains effective target / speed / readback fields

## API tests

Extend operator-console/API coverage to verify:

- catalog route
- move route
- sweep route
- save-calibration route

## UI regression checks

At minimum assert that `/console` includes IDs for:

- joint selector
- target input
- step controls
- min/max buttons
- sweep button
- save calibration button

## Manual acceptance checklist

Servo Lab is acceptable only if an operator on Mac can:

1. connect the serial head
2. arm motion
3. select any one of the 11 joints
4. read its current position
5. step it from the current position
6. drive it to min and max
7. run a visible min↔max sweep
8. change speed and see the effective speed reported
9. see the truth about acceleration support
10. save revised min/max/neutral values
11. recover to neutral or safe idle cleanly

## Explicit “not done yet” conditions

Do not mark Servo Lab complete if any of the following are still true:

- the UI cannot select all 11 joints
- step mode still behaves neutral-relative only
- Servo Lab still silently uses the Stage B smoke clamp
- speed override is present in the UI but ignored in execution
- acceleration is shown as adjustable but is not actually wired through
- calibration save only updates UI state and does not persist to file
- the operator still needs Windows for ordinary joint tuning work
