# Project Evolution

This directory preserves the major planning and design checkpoints that led to the current Blink-AI shape.

These files are still useful context, but they are **not** the primary source of truth for current work. Use:

- [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md)
- [README.md](/Users/sonics/project/Blink-AI/README.md)
- [current_direction.md](/Users/sonics/project/Blink-AI/docs/current_direction.md)
- [development_guide.md](/Users/sonics/project/Blink-AI/docs/development_guide.md)
- [architecture.md](/Users/sonics/project/Blink-AI/docs/architecture.md)
- [embodiment_runtime.md](/Users/sonics/project/Blink-AI/docs/embodiment_runtime.md)
- [protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)
- [plan_w/README.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/README.md)

## Evolution Map

### 1. Desktop-first refactor

Directory:

- [01_desktop_first_refactor](/Users/sonics/project/Blink-AI/docs/evolution/01_desktop_first_refactor)

What changed:

- moved the center of gravity from an edge-first assumption to a desktop-first embodiment runtime
- established the `body/` semantic boundary
- framed the robot as an expressive head/bust instead of a locomotion product

### 2. Agent/platform recentering

Directory:

- [02_agent_platform_recenter](/Users/sonics/project/Blink-AI/docs/evolution/02_agent_platform_recenter)

What changed:

- re-centered the roadmap around local interaction, agent structure, local model profiles, and grounded tooling
- clarified the gap between a useful app and a durable local agent runtime

### 3. Always-on local companion

Directory:

- [03_always_on_local_companion](/Users/sonics/project/Blink-AI/docs/evolution/03_always_on_local_companion)

What changed:

- pushed the repo toward a continuous local companion loop
- strengthened the role of the local M4 Pro/Ollama path, scene observation, and memory continuity

### 4. Consolidation checkpoint

Preserved review:

- [2026-03-30_engineering_review.md](/Users/sonics/project/Blink-AI/docs/evolution/2026-03-30_engineering_review.md)

What changed:

- captured a stabilization review after the large feature-building phase
- documented early consolidation and hardening work

### 5. World-class stage bundle archive

Directory:

- [04_world_class_status_bundle](/Users/sonics/project/Blink-AI/docs/evolution/04_world_class_status_bundle)

What changed:

- preserved the original prompt-driven execution pack that accompanied the Stage 0 through Stage 5 implementation campaign
- moved one-shot Codex prompts and generic execution scaffolding out of the active `plan_w` directory after the baseline landed

### 6. Stage 6 Action Plane execution pack archive

Directory:

- [05_stage6_action_plane_execution_pack](/Users/sonics/project/Blink-AI/docs/evolution/05_stage6_action_plane_execution_pack)

What changed:

- preserved the original Stage 6A through Stage 6F implementation pack for the Action Plane, browser runtime, workflows, bundles, and operator productization
- moved that prompt-driven execution material out of the active docs path after the Stage 6 baseline landed

### 7. World-class hardening pack archive

Directory:

- [06_world_class_hardening_pack](/Users/sonics/project/Blink-AI/docs/evolution/06_world_class_hardening_pack)

What changed:

- preserved the later broad hardening execution pack that followed the original Stage 0 through Stage 5 campaign
- kept it as historical context rather than a maintained execution source because the repo has since moved to status-oriented docs

### 8. Mac serial head execution pack archive

Directory:

- [07_mac_serial_head_execution_pack](/Users/sonics/project/Blink-AI/docs/evolution/07_mac_serial_head_execution_pack)

What changed:

- preserved the dedicated Mac serial head bring-up and embodied takeover execution pack
- kept the detailed stage-by-stage serial work as historical design context after the hardware baseline landed in the maintained docs and runbooks

## Relationship To `plan_w`

The `docs/evolution/plan_w/` bundle is different from this directory:

- `docs/evolution/` explains how the project got here
- `docs/evolution/plan_w/` now summarizes the maintained Stage 0 through Stage 7 status, remaining gaps, and the still-relevant design intent

Keep that distinction clear so historical design context does not crowd out the current execution plan.

Some historical files still use older framing such as "embodied companion OS" or "desktop appliance first." Read those as design lineage, not as the current product definition. The maintained wording lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).
