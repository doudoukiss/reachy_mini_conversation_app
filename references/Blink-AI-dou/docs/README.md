# Documentation Guide

This directory is the durable project-memory layer for Blink-AI.

If you are new to the repository, use this reading order:

1. [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md)
   - Authoritative product definition and standard terminology.
2. [README.md](/Users/sonics/project/Blink-AI/README.md)
   - Product snapshot, quickstart, and user-facing entrypoints.
3. [companion_quickstart.md](/Users/sonics/project/Blink-AI/docs/companion_quickstart.md)
   - Fastest terminal-first daily-use path for `uv run local-companion`.
4. [product_direction.md](/Users/sonics/project/Blink-AI/docs/product_direction.md)
   - Product stack: local-first companion, character presence runtime, relationship runtime, Action Plane, optional embodiment, and `venue_demo`.
5. [current_direction.md](/Users/sonics/project/Blink-AI/docs/current_direction.md)
   - Current priorities, stage order, and working rules.
6. [development_guide.md](/Users/sonics/project/Blink-AI/docs/development_guide.md)
   - Contributor workflow, module map, validation, runtime paths, and debugging notes.
7. [acceptance.md](/Users/sonics/project/Blink-AI/docs/acceptance.md)
   - Maintained acceptance lanes, test-surface inventory, artifact outputs, and contributor validation order.
8. [human_acceptance.md](/Users/sonics/project/Blink-AI/docs/human_acceptance.md)
   - The practical 20 to 30 minute terminal-first human acceptance checklist and session scripts.
9. [relationship_runtime.md](/Users/sonics/project/Blink-AI/docs/relationship_runtime.md)
   - Bounded continuity, memory rules, and proactive behavior bounds.
10. [character_presence_runtime.md](/Users/sonics/project/Blink-AI/docs/character_presence_runtime.md)
   - The next major product layer, including the `fast loop / slow loop` split.
11. [architecture.md](/Users/sonics/project/Blink-AI/docs/architecture.md)
   - Runtime boundaries, subsystem responsibilities, and deployment model.
12. [embodiment_runtime.md](/Users/sonics/project/Blink-AI/docs/embodiment_runtime.md)
   - Desktop runtime modes, body-package ownership, head-profile assumptions, and config surface.
13. [protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)
   - Shared contract surface and API shape.
14. [evolution/plan_w/README.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/README.md)
   - Maintained Stage 0 through Stage 7 status bundle: what landed, what remains, and what was archived.
15. [evolution/README.md](/Users/sonics/project/Blink-AI/docs/evolution/README.md)
   - Historical planning and design checkpoints organized by how the project evolved.

## By Topic

- Product definition and priorities
  - [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md)
  - [product_direction.md](/Users/sonics/project/Blink-AI/docs/product_direction.md)
  - [current_direction.md](/Users/sonics/project/Blink-AI/docs/current_direction.md)
  - [companion_quickstart.md](/Users/sonics/project/Blink-AI/docs/companion_quickstart.md)
- Character presence and continuity
  - [character_presence_runtime.md](/Users/sonics/project/Blink-AI/docs/character_presence_runtime.md)
  - [relationship_runtime.md](/Users/sonics/project/Blink-AI/docs/relationship_runtime.md)
- Architecture and runtime shape
  - [architecture.md](/Users/sonics/project/Blink-AI/docs/architecture.md)
  - [embodiment_runtime.md](/Users/sonics/project/Blink-AI/docs/embodiment_runtime.md)
  - [pre_hardware_solution.md](/Users/sonics/project/Blink-AI/docs/pre_hardware_solution.md)
- Contracts and interfaces
  - [protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)
- Contributor workflow
  - [development_guide.md](/Users/sonics/project/Blink-AI/docs/development_guide.md)
  - [acceptance.md](/Users/sonics/project/Blink-AI/docs/acceptance.md)
  - [human_acceptance.md](/Users/sonics/project/Blink-AI/docs/human_acceptance.md)
- Data and evidence artifacts
  - [data_flywheel.md](/Users/sonics/project/Blink-AI/docs/data_flywheel.md)
- Optional embodiment and hardware workflow
  - [hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md)
  - [serial_head_mac_runbook.md](/Users/sonics/project/Blink-AI/docs/serial_head_mac_runbook.md)
  - [serial_head_live_observation_sequence.md](/Users/sonics/project/Blink-AI/docs/serial_head_live_observation_sequence.md)
  - [serial_head_hardware_connection_2026-04-07.md](/Users/sonics/project/Blink-AI/docs/serial_head_hardware_connection_2026-04-07.md)
- Demo and operator usage
  - [investor_demo.md](/Users/sonics/project/Blink-AI/docs/investor_demo.md)
  - [investor_show_runbook.md](/Users/sonics/project/Blink-AI/docs/investor_show_runbook.md)
  - [stage6_operator_runbook.md](/Users/sonics/project/Blink-AI/docs/stage6_operator_runbook.md)
  - [appliance_intelligence_testing.md](/Users/sonics/project/Blink-AI/docs/appliance_intelligence_testing.md)
  - [local_companion_certification_runbook.md](/Users/sonics/project/Blink-AI/docs/local_companion_certification_runbook.md)
- Explicit vertical mode
  - [community_applications.md](/Users/sonics/project/Blink-AI/docs/community_applications.md)
- Project evolution
  - [evolution/README.md](/Users/sonics/project/Blink-AI/docs/evolution/README.md)

## Status Notes

- `docs/north_star.md` is the product-definition tie-breaker when other docs drift.
- `README.md` is the best first stop for setup and daily commands.
- `docs/companion_quickstart.md` is the shortest path for someone who only wants to launch and use the terminal-first companion.
- `docs/product_direction.md` is the maintained short explanation of what Blink-AI is and how its layers fit together.
- `docs/current_direction.md` is the maintained summary of what matters most right now.
- `docs/acceptance.md` is the maintained acceptance harness and replaces tribal-knowledge stabilization recipes as the primary validation entrypoint.
- `docs/human_acceptance.md` is the maintained human test guide for the current terminal-first milestone.
- `docs/investor_show_runbook.md` is the maintained operator runbook for the deterministic investor-show lane and should be used instead of relying on `docs/plan2/` design notes during rehearsal.
- `docs/hardware_grounded_expression_architecture.md` is the maintained design reference for what the robot head can actually express and how the software layer is required to sequence that behavior.
- `docs/relationship_runtime.md` explains how Blink-AI handles continuity without drifting into fake intimacy.
- `docs/evolution/plan_w/` is the maintained stage-status bundle for the roadmap, not a future execution pack.
- `docs/evolution/05_stage6_action_plane_execution_pack/`, `docs/evolution/06_world_class_hardening_pack/`, and `docs/evolution/07_mac_serial_head_execution_pack/` preserve superseded execution packs that should not be treated as current planning truth.
- `docs/evolution/` preserves superseded but still useful planning and design material so the maintained docs stay focused.
- `tutorial.md` at the repo root remains the append-only project history and beginner walkthrough.
- `protocol.md` describes the public shared contract surface. Internally, those contracts now live under `src/embodied_stack/shared/contracts/`, with `src/embodied_stack/shared/models.py` kept temporarily as a compatibility shim.
- Machine-local diagnostics and runtime outputs belong under `runtime/`, not under `docs/`.
