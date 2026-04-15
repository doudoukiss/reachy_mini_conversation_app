# Blink-AI Product Direction Recenter

This bundle preserves the product-direction recentering plan that led to the current north-star cleanup.

The authoritative product definition now lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).

## Product decision

Blink-AI should become a **terminal-first, local-first, character-presence companion OS with optional embodiment**.

Not the other way around.

The robot is an embodiment layer for the companion. It is not the product thesis.
The browser console is an operator surface. It is not the product thesis.
The Action Plane is a capability substrate. It is not the product thesis.
The community concierge flow is a believable demo vertical. It is not the product thesis.

## Primary product surface

- `uv run local-companion`
- terminal-first conversational experience
- voice optional but desirable
- browser console as a secondary inspection and control surface
- robot body optional

## Core promise

Blink-AI should feel like a private, persistent, multimodal companion that can:
- talk naturally
- remember important things
- notice the local scene
- help with planning and lightweight digital actions
- stay honest about limits
- later express itself through a desk robot head without redesigning the brain

## Execution order

1. Read `00_product_decision.md`
2. Read `01_product_boundaries_and_non_goals.md`
3. Read `02_repo_recenter_plan.md`
4. Read `03_latency_and_model_strategy.md`
5. Read `04_docs_and_skills_rewrite_map.md`
6. Run `codex_prompt_01_rewrite_north_star_and_identity.md`
7. Run `codex_prompt_02_build_low_latency_hybrid_companion_runtime.md`
8. Run `codex_prompt_03_productize_terminal_first_companion.md`
9. Run `codex_prompt_04_build_relationship_runtime.md`
10. Run `codex_prompt_05_reclassify_robot_and_demo_layers.md`

## Acceptance standard

Blink-AI is on the right path when:
- the product thesis is consistent across docs, prompts, runtime defaults, and skills
- terminal-first companion use feels first-class
- the default conversation path is fluid enough to use daily
- the robot body is clearly an optional embodiment, not a blocker
- concierge/demo behavior is a mode, not the hidden default
