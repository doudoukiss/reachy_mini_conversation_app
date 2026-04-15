---
name: character-presence-runtime
description: Use when designing or implementing Blink-AI's next major upgrade around persona manifest, presence state, avatar shell, low-latency presence loop, initiative, and synchronized character output.
---

Read first:

- `AGENTS.md`
- `PLAN.md`
- `docs/north_star.md`
- `docs/current_direction.md`
- `docs/product_direction.md`
- `docs/character_presence_runtime.md`
- `docs/relationship_runtime.md`
- `docs/architecture.md`
- `docs/evolution/plan_w/08_stage7_character_presence_runtime.md`
- `docs/evolution/08_stage7_character_presence_runtime_pack/README.md`

Preserve these rules:

1. Terminal-first `local-companion` stays the primary user path.
2. Blink-AI remains a local-first companion first; the character layer must reinforce that product, not replace it.
3. Avatar shell is a synchronized projection of the same runtime, not a separate chatbot.
4. Use `fast loop / slow loop` as the maintained architecture language.
5. Relationship runtime remains the bounded continuity layer inside the broader character presence runtime.
6. Action Plane remains the slow-loop capability substrate.
7. Embodiment remains optional and semantic.
8. Character identity must remain bounded, non-manipulative, and inspectable.
9. Initiative must be rate-limited, approval-aware when needed, and easy to disable.
10. Do not make universal desktop automation the first implementation target; start with focused terminal, browser, and selected app grounding.

After changes:

- update docs if behavior contracts or architecture changed
- run:
  - `uv run pytest`
  - `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`
