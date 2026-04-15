---
name: embodiment-runtime
description: Use when changing the local-first companion runtime, optional embodiment, body semantics, runtime modes, or head-profile-related config and docs in Blink-AI.
---

Use this skill when work touches any of:

- `src/embodied_stack/desktop/`
- `src/embodied_stack/body/`
- runtime modes
- body-driver config
- head-profile assumptions
- semantic embodiment contracts

Before making changes:

1. Read:
   - `AGENTS.md`
   - `docs/north_star.md`
   - `docs/current_direction.md`
   - `docs/embodiment_runtime.md`
   - `docs/hardware_grounded_expression_architecture.md`
   - `docs/body_motion_tuning.md`
   - `docs/robot_head_hardware_and_serial_handoff.md`
   - `docs/evolution/01_desktop_first_refactor/01_target_refactor_plan.md`
   - `docs/evolution/01_desktop_first_refactor/02_robot_head_hardware_profile.md`
   - `docs/evolution/01_desktop_first_refactor/03_repo_refactor_map.md`
   - `docs/evolution/01_desktop_first_refactor/04_validation_and_acceptance.md`

2. Preserve these invariants:
   - Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.
   - `local-companion` is the default daily-use product path on the Mac.
   - `blink-appliance` is the default browser/operator entrypoint around that same runtime.
   - `desktop/` is the default development and demo path.
   - `body/` owns semantic embodiment and future transport boundaries.
   - The runtime must stay useful when no powered body is attached.
   - The robot head, virtual body, avatar shell, and bench tooling are optional embodiment layers around the same companion core, not alternative product identities.
   - The same fast loop / slow loop companion runtime should project through bodyless, avatar, virtual-body, and serial-head paths.
   - The brain must never depend on raw servo IDs.
   - The body must not be assumed to be always present.
   - Tethered or Jetson paths must remain optional compatibility layers, not mandatory blockers.
   - Safety and safe-idle behavior beat cleverness.
   - The maintained body-expression source of truth is the grounded catalog, not ad hoc semantic composite poses.
   - The maintained investor embodiment surface is the V3-V7 evidence ladder plus the V8 expressive-motif lane.
   - Structural motion and eye-area motion must be sequenced, not changed concurrently, unless hardware evidence explicitly proves otherwise.

3. Prefer:
   - semantic commands over raw device-specific commands
   - appliance setup and explicit device-health visibility over hidden inference
   - explicit config over hidden runtime inference
   - bodyless and virtual-body compatibility for all new work
   - additive refactors over destructive renames unless the rename clearly improves the repo
   - `GET /api/operator/body/expression-catalog` as the first inspection surface for supported expression capability
   - motif or grounded-state implementations over reviving older free-form body semantics

4. After changes:
   - update docs if runtime modes, config, or body semantics changed
   - run:
     - `uv run pytest`
     - `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`
