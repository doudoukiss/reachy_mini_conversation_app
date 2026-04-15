# Mac Servo Lab Design Pack

This pack is the implementation blueprint for a **Mac Servo Lab** inside the existing Blink-AI Mac workflow.

The design is based on the current repo state, especially:

- `docs/robot_head_live_limits.md`
- `docs/robot_head_live_revalidation_2026-04-10.md`
- `docs/serial_head_mac_runbook.md`
- `docs/windows_fd_serial_reference.md`
- `docs/serial_head_live_observation_sequence.md`
- `src/embodied_stack/body/calibration.py`
- `src/embodied_stack/body/serial/bench.py`
- `src/embodied_stack/body/serial/driver.py`
- `src/embodied_stack/body/serial/transport.py`
- `src/embodied_stack/brain/static/console.html`
- `src/embodied_stack/brain/static/console.js`
- `src/embodied_stack/body/driver.py`
- `src/embodied_stack/desktop/runtime.py`
- `src/embodied_stack/shared/contracts/operator.py`
- `src/embodied_stack/shared/contracts/body.py`

## Core judgment

The Mac path already has most of the hard parts:

- live serial transport
- per-servo ping and readback
- saved calibration
- body driver and runtime gateway
- `/console` body panel
- motion reports and operator audits

What it does **not** have is a true Windows-style operator-facing servo tuning surface.

The current Stage B tools are deliberately smoke-safe and therefore not a good answer to the question, “What can each servo really do?” In particular:

- `move-joint` is **neutral-relative**, not truly **current-relative**
- `move-joint` is constrained by a hard-coded smoke limit
- the console only exposes connect / scan / ping / health / arm / semantic smoke / write neutral / safe idle
- per-command speed override is not exposed even though the transport payload already carries speed

Mac Servo Lab closes that gap on the maintained Mac path:

- `/console` now exposes an operator-only Servo Lab panel for all 11 servo-backed joints
- the calibration CLI now exposes `servo-lab-catalog`, `servo-lab-readback`, `servo-lab-move`, `servo-lab-sweep`, and `servo-lab-save-calibration`
- current-relative stepping is resolved from live readback, not from neutral
- Servo Lab bypasses the Stage B smoke clamp but still respects calibrated hard limits
- per-command speed override is real and operator-visible
- acceleration support is reported truthfully from the current transport and is surfaced in results instead of being implied

## What this pack tells Codex to build

A **Mac Servo Lab** that stays inside the existing product architecture:

- operator-only raw servo tools
- exposed on Mac through `/console`
- backed by the same body driver and desktop runtime stack
- optionally mirrored in CLI for headless bench use and regression tests
- explicitly separated from the semantic planner/runtime boundary

## Important implementation principles

1. Do **not** break or redefine the existing Stage B smoke tools.
2. Do **not** route raw servo control into the AI planner.
3. Do **not** fake acceleration support.
4. Do add a real operator-facing lab for:
   - selecting all 11 controllable joints
   - reading current position and health
   - setting lab min/max
   - moving to min / max / neutral / target
   - current-relative stepping
   - bounded min↔max sweeps
   - per-command speed override
   - calibration write-back
5. Use the existing motion-report and audit machinery whenever possible so export and evidence flows stay coherent.

## Operator summary

Mac Servo Lab is now the maintained Mac tuning path.

Use it through either:

- `/console` -> `Body Runtime` -> `Servo Lab`
- `PYTHONPATH=src uv run python -m embodied_stack.body.calibration servo-lab-*`

Windows remains fallback-only for hardware sanity checks when the Mac path itself is in doubt.

## File order

Read and execute in this order:

1. `01_current_state_and_gap_analysis.md`
2. `02_target_product_scope_and_parity.md`
3. `03_backend_transport_and_api_plan.md`
4. `04_console_ui_and_cli_plan.md`
5. `05_motion_calibration_and_operator_rules.md`
6. `06_execution_sequence_and_acceptance.md`

Then use:

- `codex_prompts/mac_servo_lab_implementation_prompt.md`
- `codex_prompts/mac_servo_lab_validation_prompt.md`
