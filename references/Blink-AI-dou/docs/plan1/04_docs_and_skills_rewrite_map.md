# Docs and Skills Rewrite Map

This file is preserved planning lineage. The authoritative product definition now lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).

## Docs that should change first

### Top-priority docs
- `README.md`
- `PLAN.md`
- `AGENTS.md`
- `docs/current_direction.md`
- `docs/architecture.md`
- `docs/development_guide.md`
- `docs/README.md`

### New docs to add
- `docs/north_star.md`
- `docs/companion_core.md`
- `docs/latency_strategy.md`
- `docs/vertical_modes.md`

## Prompt and identity files to rewrite

### Required
- `src/embodied_stack/brain/instructions/IDENTITY.md`
- `src/embodied_stack/brain/llm.py`
- perception service prompts that still hardcode concierge language

### Rewrite principle
Default identity should be:
- personal companion
- local-first companion
- optional embodied endpoint

Venue/concierge language should only appear when:
- `context_mode == venue_demo`
- a venue-specific skill is active
- a venue-specific instruction layer is loaded

## Skill library cleanup

### Promote to primary skills
- `general_companion_conversation`
- `daily_planning`
- `memory_followup`
- `observe_and_comment`
- `safe_degraded_response`

### Add
- `relationship_maintenance`
- `bounded_action_assistance`
- `focus_session_support`

### Demote
- `community_concierge`
  - keep it
  - do not remove it
  - make it explicit vertical mode, not baseline identity

## `.agents/skills/` updates

The Codex skills currently emphasize project context, embodiment runtime, and demo quality.
Add a fourth skill:

### `product-direction`
It should enforce:
- personal companion first
- terminal-first companion path as the hero UX
- action plane as capability substrate, not identity
- embodiment as optional shell
- concierge as explicit vertical mode

## Required consistency checks

After rewrite:
- grep for `community concierge robot` should only hit venue-specific files
- grep for `personal_local` should map to the default product path
- grep for `terminal-first companion` should appear in the primary docs
- no top-level doc should imply that the robot is required for Blink-AI to be useful
