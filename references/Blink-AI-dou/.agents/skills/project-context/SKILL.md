---
name: project-context
description: Use when working anywhere in this repository to understand the north star, local-first companion runtime, optional embodiment, protocol rules, and validation workflow.
---

Before making major changes in this repository:

1. Read:
   - `AGENTS.md`
   - `PLAN.md`
   - `docs/north_star.md`
   - `docs/current_direction.md`
   - `docs/README.md`
   - `docs/architecture.md`
   - `docs/embodiment_runtime.md`
   - `docs/protocol.md`
   - `docs/hardware_grounded_expression_architecture.md`
   - `docs/evolution/README.md`

2. Preserve these invariants:
   - Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.
   - The terminal-first local companion runtime is the default current product path.
   - The desktop appliance is the default browser/operator path around that runtime, not the repo identity.
   - The desktop runtime is the default current development and demo path.
   - The primary product is the AI presence living in the computer.
   - The character presence runtime is the next major product layer.
   - Use `fast loop / slow loop`, `relationship runtime`, `local-first companion`, and `optional embodiment` as the maintained product terms.
   - Mac brain does heavy AI, memory, orchestration, and perception.
   - The runtime is a deterministic shell around probabilistic reasoning.
   - The `body/` package owns semantic embodiment and future transport boundaries.
   - The maintained body-expression source of truth is the grounded catalog and its capability export.
   - Jetson or tethered edge paths stay optional, simple, and safety-focused.
   - Shared contracts live in `src/embodied_stack/shared/`.
   - The domain contract sources are under `src/embodied_stack/shared/contracts/`.
   - `src/embodied_stack/shared/models.py` is a temporary compatibility shim and should not gain new primary logic.
   - The brain must never depend on raw servo IDs.
   - The system must remain useful before hardware exists and must run cleanly with no physical body attached.
   - Major behavior should be measurable, replayable, and exportable.

3. After changes:
   - update docs if contracts or architecture changed
   - run:
     - `uv run pytest`
     - `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`

4. Prefer:
   - companion-first desktop entrypoints such as `uv run local-companion` and `embodied_stack.desktop.app` for local workflows
   - intentional terminal-first companion flow plus appliance-quality browser/operator setup paths
   - deterministic demo flows
   - grounded body-expression behavior over legacy semantic drift
   - visible logs
   - graceful fallbacks
   - explicit runtime/body config over hidden defaults
   - simple code over unnecessary abstraction
