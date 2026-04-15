# Current Direction

This is the maintained execution brief for Blink-AI.

The authoritative product definition lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).
For the maintained product-layer summary, use [product_direction.md](/Users/sonics/project/Blink-AI/docs/product_direction.md).
For the maintained Stage 0 through Stage 7 status bundle, use [plan_w/README.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/README.md).
For the historical planning lineage, use [evolution/README.md](/Users/sonics/project/Blink-AI/docs/evolution/README.md).

## Current Truths

Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.

In the current phase:

- the MacBook Pro is the active companion runtime host
- the terminal-first `local-companion` loop is the hero product surface
- `companion_live` is the default daily-use profile because it keeps the product loop grounded in a local-first companion
- the browser appliance, `/console`, and the Action Center are secondary operator and control surfaces
- the body is optional, virtualizable, and safety-gated embodiment
- the robot remains an expressive social head and bust, not a locomotion platform
- the Action Plane is the safe slow-loop digital action substrate, not the repo identity
- `venue_demo` remains the strongest near-term commercial proof point, but as an explicit mode layered on top of the same companion core

## What Matters Most Now

1. Make the local-first companion path feel daily-usable.
   - one-command launch
   - safe setup and device handling
   - honest fallback when mic, camera, speaker, or models are degraded
   - an explicit no-robot certification lane that separates machine readiness from repo/runtime correctness
   - a maintained acceptance harness with quick, full, release-candidate, manual-local, and optional hardware lanes
2. Build the character presence runtime as the next major product layer.
   - an explicit persona manifest instead of personality hidden in prompts
   - a clear `fast loop / slow loop` split
   - a lightweight avatar shell that projects the same runtime without replacing the terminal
   - synchronized language, memory, initiative, and expression
   - a bounded initiative engine that is grounded in desktop context, easy to silence, and conservative about auto-action
3. Keep the relationship runtime bounded and inspectable.
   - useful continuity for greeting, re-entry, follow-up, planning, and tone preferences
   - no fake intimacy or hidden personality drift
4. Keep the slow loop explicit.
   - the Action Plane handles typed actions, approvals, workflows, and replayable side effects
   - body execution remains outside the digital action executor
5. Keep optional embodiment downstream of the same companion core.
   - expression, gaze, gesture, animation, and safe idle
   - hardware-grounded expression states, units, motifs, and operator-visible capability export
   - no brain-side servo or transport logic
6. Keep the whole system measurable, replayable, and honest.
   - traces, checkpoints, exports, evals, and investor evidence
   - deterministic investor-show lanes with explicit voice, motion, and safety diagnostics

The Stage 4 embodiment baseline is no longer only a dry-run landing zone. The Mac serial path has already been exercised end to end on the real head, but that remains optional embodiment around the same companion core.

## Current Program Order

- Stage 0: local companion and appliance reliability
  - baseline is in the repo
  - continue hardening launch, setup, readiness reporting, fallback honesty, acceptance quality, certification, and burn-in quality
- Stage 1: Agent OS and tool protocol
  - baseline is in the repo
  - continue hardening run recovery, contract stability, and operator inspection
- Stage 2: perception, world model, and social runtime
  - baseline is in the repo
  - continue hardening watcher and semantic refresh discipline plus inspectable social policy
- Stage 3: memory, episode flywheel, and teacher mode
  - baseline is in the repo
  - continue hardening memory policy, review quality, and benchmark scoring
- Stage 4: semantic embodiment and Feetech bridge
  - baseline is in the repo
  - continue hardening live calibration, serial health, and embodiment quality
- Stage 5: research bridge and world-class eval stack
  - baseline is in the repo
  - continue hardening replay determinism, planner-swap scoring, export quality, and dataset hygiene
- Stage 6: Action Plane and operator-safe tool execution
  - the Stage A through Stage F baseline is in the repo
  - continue hardening browser recipes, workflow orchestration quality, action-quality evals, bounded connector expansion, and the operator product loop around the Action Center
- Stage 7: character presence runtime
  - next major upgrade
  - first fast-loop baseline now exists as an explicit terminal-first presence state machine with separate `presence_runtime` and `voice_loop` inspection
  - the bounded initiative engine now exists as an explicit `monitor -> candidate -> infer -> score -> decide -> cooldown` path with terminal activity, current companion state, recent memory, reminders, and optional browser context grounding
  - a first lightweight browser character shell now exists as an optional surface driven by the shared `character_presence_shell` projection and `/api/operator/presence`
  - the character runtime now also emits a shared `CharacterSemanticIntent` plus explicit projection profiles so avatar-shell state and serial-head behavior stay downstream of the same mind
  - live head projection is conservative by design: if transport, calibration, coupling, or arm gates are not clean, the runtime keeps preview-only projection and logs the block reason
  - keep suggestions and questions as the default initiative path, with only narrow reminder follow-up auto-action enabled by default
  - continue building the fast loop, persona manifest, avatar shell, and focused desktop grounding for terminal, IDE, and browser workflows
  - keep the Action Plane as the slow loop and keep embodiment as a projection of the same companion core

## Working Rules

- Prefer a deterministic shell around probabilistic reasoning.
- Keep `local-companion` as the primary user-facing path and the desktop appliance as the secondary browser/operator path.
- Treat embodiment and `venue_demo` as explicit layers on top of the same companion core, not competing product identities.
- Keep companion continuity explicit, respectful, and inspectable instead of hiding it inside vague personality prompts.
- Keep the flagship path conversation-first: low-latency when configured, local-first by default, and honest when degraded.
- Keep initiative tasteful and easy to silence from the terminal-first companion path.
- Keep the body optional and safely degradable.
- Keep major behavior measurable, replayable, and exportable.
- Preserve the Mac brain and optional Jetson edge split.
- Preserve simulation-first development and honest investor demos.
- Treat the deterministic investor embodiment surface as one maintained V8 expressive lane backed by the V3-V7 hardware evidence ladder, not a stack of drifting parallel investor shows.

## Canonical Docs

When working in this repo, prioritize these docs:

- [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md)
- [README.md](/Users/sonics/project/Blink-AI/README.md)
- [product_direction.md](/Users/sonics/project/Blink-AI/docs/product_direction.md)
- [character_presence_runtime.md](/Users/sonics/project/Blink-AI/docs/character_presence_runtime.md)
- [relationship_runtime.md](/Users/sonics/project/Blink-AI/docs/relationship_runtime.md)
- [PLAN.md](/Users/sonics/project/Blink-AI/PLAN.md)
- [development_guide.md](/Users/sonics/project/Blink-AI/docs/development_guide.md)
- [architecture.md](/Users/sonics/project/Blink-AI/docs/architecture.md)
- [embodiment_runtime.md](/Users/sonics/project/Blink-AI/docs/embodiment_runtime.md)
- [protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)

Use `docs/evolution/plan_w/` for staged status and remaining-gap context, and `docs/evolution/` for broader historical context.
