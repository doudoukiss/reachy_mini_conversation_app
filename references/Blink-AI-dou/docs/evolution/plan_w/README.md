# World-Class Stage Bundle

This directory is now the maintained **stage-status bundle** for the roadmap that pushed Blink-AI from a desktop-first local runtime toward the current Stage 0 through Stage 7 plan.

It is no longer a “future Codex execution pack.” Most of the work described here has landed in the repo. The useful job of this directory now is:

- preserve the staged design intent in compact form
- show what is already implemented
- call out the remaining hardening gaps that still matter

If you need the current source of truth for day-to-day work, read these first:

1. [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md)
2. [README.md](/Users/sonics/project/Blink-AI/README.md)
3. [PLAN.md](/Users/sonics/project/Blink-AI/PLAN.md)
4. [current_direction.md](/Users/sonics/project/Blink-AI/docs/current_direction.md)
5. [architecture.md](/Users/sonics/project/Blink-AI/docs/architecture.md)
6. [protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)

## What remains here

Read these in order:

1. [00_north_star_and_design_principles.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/00_north_star_and_design_principles.md)
2. [01_stage0_local_appliance_reliability.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/01_stage0_local_appliance_reliability.md)
3. [02_stage1_agent_os_and_tool_protocol.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/02_stage1_agent_os_and_tool_protocol.md)
4. [03_stage2_perception_world_model_social_runtime.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/03_stage2_perception_world_model_social_runtime.md)
5. [04_stage3_memory_episode_flywheel_teacher_mode.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/04_stage3_memory_episode_flywheel_teacher_mode.md)
6. [05_stage4_semantic_embodiment_and_feetech_bridge.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/05_stage4_semantic_embodiment_and_feetech_bridge.md)
7. [06_stage5_research_bridge_and_world_class_eval.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/06_stage5_research_bridge_and_world_class_eval.md)
8. [07_stage6_action_plane_and_operator_product.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/07_stage6_action_plane_and_operator_product.md)
9. [08_stage7_character_presence_runtime.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/08_stage7_character_presence_runtime.md)

## What was archived

Superseded execution packs and one-shot prompt bundles now live under `docs/evolution/`:

- [docs/evolution/04_world_class_status_bundle](/Users/sonics/project/Blink-AI/docs/evolution/04_world_class_status_bundle)
- [docs/evolution/05_stage6_action_plane_execution_pack](/Users/sonics/project/Blink-AI/docs/evolution/05_stage6_action_plane_execution_pack)
- [docs/evolution/06_world_class_hardening_pack](/Users/sonics/project/Blink-AI/docs/evolution/06_world_class_hardening_pack)
- [docs/evolution/07_mac_serial_head_execution_pack](/Users/sonics/project/Blink-AI/docs/evolution/07_mac_serial_head_execution_pack)

Those files are still useful historical context, but they are no longer maintained as active operator or contributor guidance.

## Current high-level status

- Stage 0 baseline: implemented
- Stage 1 baseline: implemented
- Stage 2 baseline: implemented
- Stage 3 baseline: implemented
- Stage 4 baseline: implemented
- Stage 5 baseline: implemented
- Stage 6 baseline: implemented
- Stage 7: planned next major upgrade

## Remaining cross-stage hardening themes

- keep the browser appliance and non-browser recovery paths boring and reliable
- keep replay, export, and benchmark artifacts honest instead of “demo-clean”
- improve strict replay determinism instead of claiming it is solved
- keep live serial/hardware work gated behind real calibration and health checks
- keep the repo centered on the local-first companion while Stage 7 adds the character presence runtime
- continue pruning doc drift so maintained docs describe the actual repo, not the older implementation campaign
