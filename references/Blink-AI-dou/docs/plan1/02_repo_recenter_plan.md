# Repo Recenter Plan

This file is preserved planning lineage. The authoritative product definition now lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).

## Problem

The repo already contains the right components, but the top-level product story is split.

Examples of the split:
- top-level docs already say "local embodied companion OS"
- runtime defaults already support `personal_local`
- terminal-first companion path already exists
- some core prompts and identity files still frame Blink-AI as a community concierge robot

## Goal

Make the codebase tell one story:

**Blink-AI is a terminal-first, local-first, character-presence companion first.**

## Recenter sequence

### Stage A — freeze the product thesis
Update all top-level docs so they say the same thing.

Required files:
- `README.md`
- `PLAN.md`
- `AGENTS.md`
- `docs/current_direction.md`
- `docs/README.md`
- `docs/architecture.md`
- `docs/development_guide.md`

### Stage B — rewrite identity prompts and instructions
Remove concierge-first wording from:
- `src/embodied_stack/brain/instructions/IDENTITY.md`
- `src/embodied_stack/brain/llm.py`
- perception system prompts that still say community concierge by default

Replace with:
- personal companion default
- explicit `venue_demo` override language
- explicit robot-body-is-optional language

### Stage C — reclassify skills
Skill library should be organized around the real product.

Recommended top-level first-party skills:
- `general_companion_conversation`
- `daily_planning`
- `memory_followup`
- `observe_and_comment`
- `relationship_maintenance`
- `safe_degraded_response`
- `bounded_action_assistance`
- `community_concierge` as explicit vertical mode

### Stage D — make terminal-first companion the hero path
The best documented path should be:
- `uv run local-companion`

The browser should remain:
- console
- Action Center
- inspection surface
- approvals surface
- optional operator UI

### Stage E — reframe embodiment
Robot body docs should say:
- embodiment is optional
- the head is an expressive endpoint
- semantic body API is downstream of the companion brain

### Stage F — simplify public terminology
Use one consistent vocabulary:
- Companion Core
- Action Plane
- Embodiment Layer
- Demo / Vertical Modes

Avoid mixing these with overlapping or contradictory labels.

## Acceptance test

A new reader should be able to answer all five questions consistently:
1. What is Blink-AI?
2. What is the main user-facing surface?
3. Is the robot required?
4. What is the action plane for?
5. What is concierge mode relative to the core product?
