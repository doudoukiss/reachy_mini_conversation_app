# PLAN.md

Purpose: keep Blink-AI pointed at the maintained north star without duplicating the detailed stage-status docs in `docs/evolution/plan_w/`.

Start with [docs/north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).

## Current Direction

Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.

Current truths:

- the MacBook Pro is the active runtime host
- the terminal-first `local-companion` loop is the primary product surface
- the browser appliance, `/console`, and the Action Center are secondary operator and control surfaces
- the primary product is the AI presence living in the computer
- the body is optional, virtualizable, and safety-gated embodiment
- cloud backends are enhancements, not prerequisites
- the Action Plane is slow-loop capability substrate, not product identity
- `venue_demo` community concierge remains the strongest near-term commercial proof point, but as an explicit mode

## Current Baseline

The repository already has:

- a maintained terminal-first local companion path with local device health and honest fallback reporting
- a maintained browser and operator path with `uv run blink-appliance` as the browser/operator entrypoint around the same runtime
- a no-robot local companion certification lane with machine-readiness vs product-readiness separation, bounded burn-in coverage, and aggregate artifacts under `runtime/diagnostics/local_companion_certification/`
- a maintained acceptance harness with quick, full, release-candidate, manual-local, and optional hardware lanes under `runtime/diagnostics/acceptance/`
- an explicit Agent OS runtime with skills, subagents, typed tools, run persistence, checkpoints, and operator inspection APIs
- a Stage 6 Action Plane baseline with typed action contracts, deterministic policy, approval resolution and replay, connector health, bounded connector runtime, browser session artifacts, reentrant workflow runs, proactive trigger evaluation, idempotent execution records, durable action bundles, deterministic action replays, unified Action Center UX, and conservative restart-review handling under `runtime/actions/`
- world model, perception, shift supervisor, incident, replay, report, and episode-export infrastructure
- layered memory policy with append-only memory actions, reviews, operator corrections, and a bounded relationship runtime
- `blink_episode/v2` exports with scene facts, run lineage, memory actions, teacher annotations, and local benchmark artifacts
- a Stage 5 research bridge with registered planner adapters, episode replay artifacts, `blink_research_bundle/v1`, and benchmark support for replay, determinism, and export quality
- semantic optional embodiment with virtual-body support and a serial landing zone behind the body package
- a hardware-grounded body expression catalog with explicit supported states, units, motifs, alias mapping, and operator export
- simulation-first, dry-run, and replayable investor/demo evidence paths
- a deterministic investor embodiment surface grounded in the V3-V7 hardware evidence ladder plus the V8 expressive motif lane around the same companion core

## Active Execution Order

Detailed stage-status docs live in `docs/evolution/plan_w/`. The maintained execution order is:

1. Stage 0: local companion and appliance reliability
   - baseline implemented
   - continue hardening launch, setup, device reporting, fallback honesty, the maintained acceptance lanes, and the real-Mac certification bar for the no-robot companion path
2. Stage 1: Agent OS and tool protocol
   - baseline implemented
   - continue hardening run recovery, tool discipline, operator inspection, and contract stability
3. Stage 2: perception, world model, and social runtime
   - baseline implemented
   - continue hardening watcher and semantic refresh discipline plus social-policy behavior
4. Stage 3: memory, episode flywheel, and teacher mode
   - baseline implemented
   - continue hardening memory policy, teacher workflows, and benchmark quality
5. Stage 4: semantic embodiment and Feetech bridge
   - baseline implemented
   - continue hardening live calibration, serial health, and embodiment quality
6. Stage 5: research bridge and world-class eval stack
   - baseline implemented
   - continue hardening replay determinism, planner-swap scoring, research export quality, and dataset hygiene
7. Stage 6: Action Plane and operator-safe tool execution
   - baseline implemented
   - continue with richer browser recipes, workflow polish, action-quality evals, external connector expansion, and higher-fidelity operator workflows on top of the current policy and gateway substrate
8. Stage 7: character presence runtime
   - next major upgrade
   - build the fast loop, persona manifest, lightweight avatar shell, bounded initiative engine, and focused desktop grounding for terminal, IDE, and browser workflows
   - keep the Action Plane as the slow loop and keep embodiment as a projection of the same companion core

## Working Rules

- Prefer a deterministic shell around probabilistic reasoning.
- Keep `local-companion` as the primary user-facing path and the desktop appliance as the secondary browser/operator path.
- Keep semantic body actions above raw servo commands.
- Keep the system useful with no physical body attached.
- Keep every major capability measurable, replayable, and exportable.
- Preserve the Mac brain and optional Jetson edge split.
- Preserve simulation-first development and honest investor demos.

## Documentation Structure

- Current truth: `README.md`, `docs/north_star.md`, `docs/product_direction.md`, `docs/current_direction.md`, `docs/development_guide.md`, `docs/architecture.md`, `docs/embodiment_runtime.md`, `docs/protocol.md`
- Stage status bundle: `docs/evolution/plan_w/` (Stages 0 through 7)
- Historical plans and past checkpoints: `docs/evolution/`

## Validation

Run after meaningful changes:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

For milestone-level validation, use:

```bash
make acceptance-quick
make acceptance-full
make acceptance-rc
```

Use the manual local-Mac and optional hardware lanes only when the current proof actually needs them.
