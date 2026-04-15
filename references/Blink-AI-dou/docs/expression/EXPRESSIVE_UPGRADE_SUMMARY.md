# Expressive Behavior Upgrade Summary

## Architectural judgment

- **Global product priority:** the broader safe action substrate is still the biggest missing capability. Browser/computer-use and workflow action remain less mature than the embodiment stack.
- **Embodiment-specific judgment:** the body subsystem is mature enough for disciplined expansion now. It already has canonical semantic actions, a semantic compiler, joint-profile constraints, virtual preview, calibration, live motion gates, tuning overrides, and body-side tests.
- **Decision:** keep the product-level roadmap focused on safe action substrate, but allow a bounded Stage D.5 expansion of head expressions and movements inside the existing semantic body layer.

## New canonical expressions

- `curious_bright`
- `focused_soft`
- `playful`
- `bashful`

## New canonical gestures

- `double_blink`
- `acknowledge_light`
- `playful_peek_left`
- `playful_peek_right`

## New canonical animations

- `youthful_greeting`
- `soft_reengage`
- `playful_react`

## Design rules enforced

- No mouth-first emotion labels or physically impossible affect.
- Youthful style is light, contemporary, and restrained rather than cartoonish.
- New actions are grouped into held expressions, transient gestures, and multi-beat animations.
- Multi-beat animations recover into socially stable states.
- Default orchestration policy is unchanged; new actions are available for explicit use and teacher review before wider rollout.

## Files changed

- `src/embodied_stack/body/semantics.py`
- `src/embodied_stack/body/library.py`
- `src/embodied_stack/body/animations.py`
- `src/embodied_stack/brain/instructions/BODY_POLICY.md`
- `src/embodied_stack/brain/static/console.html`
- `docs/expressive_behavior_system_v1.md`
- `tests/body/test_semantics.py`
- `tests/body/test_compiler.py`

## Validation run

- `uv run pytest tests/body -q`
- Result: `59 passed, 2 skipped`
