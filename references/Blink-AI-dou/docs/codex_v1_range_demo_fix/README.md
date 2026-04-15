# V1 Show Motion Envelope Fix Pack

This plan pack is for Codex to fix the current embodied show problems in a direct, high-signal order.

## What this pack is solving

Two user-visible problems are currently blocking confidence in the V1 show:

1. **The head still drops hard twice during the show.**
2. **Documented new motions such as `double_blink` exist in code/docs, but they do not read clearly on the real robot during the actual show.**

A third requested addition is now mandatory:

3. **The very beginning of `investor_ten_minute_v1` must contain a dedicated near-full-range servo demonstration** so the operator can immediately see the usable motion envelope of the embodied head before the scripted investor narration continues.

## High-confidence diagnosis

The biggest root cause is **not** the show JSON. The show JSON already references the new actions.

The biggest root cause is the **live animation execution path**:

- multi-frame gestures and animations compile correctly
- but the live bridge currently sends every compiled frame back-to-back without waiting for each frame's `duration_ms` and `hold_ms`
- that collapses multi-frame actions on hardware
- as a result, `double_blink`, `wink`, `playful_peek`, `youthful_greeting`, and `soft_reengage` do not read properly on the real head

Because `youthful_greeting` and `soft_reengage` both end in `listen_attentively`, and `listen_attentively` is authored with negative head pitch, the collapsed animation path makes those sequences look like abrupt head-down drops instead of readable expressive motion.

## Required implementation order

Follow the plans in this order:

1. [01_root_cause_analysis.md](./01_root_cause_analysis.md)
2. [02_live_frame_scheduler_and_animation_visibility.md](./02_live_frame_scheduler_and_animation_visibility.md)
3. [03_opening_servo_range_demo_design.md](./03_opening_servo_range_demo_design.md)
4. [04_v1_show_rebuild_and_head_drop_removal.md](./04_v1_show_rebuild_and_head_drop_removal.md)
5. [05_tests_acceptance_and_operator_validation.md](./05_tests_acceptance_and_operator_validation.md)

## Non-negotiable constraints

- Keep the main product direction unchanged.
- Do **not** expose raw-servo control to the planner or to the general semantic action layer.
- Keep the semantic body interface for normal product behavior.
- The new full-range demo may be **show-specific**, but it must still respect calibrated hard bounds.
- Do not increase servo speed or acceleration above the current safe profile values in this task.
- Do not fake a live calibration file inside the repo. The current bundle does not include one; the implementation must use the configured live calibration when present and fall back safely when absent.

## Outcome required from Codex

After implementation:

- the first visible segment of `investor_ten_minute_v1` is a dedicated range demo
- multi-frame actions become visibly real on hardware
- `double_blink` is unmistakably visible in the show
- the abrupt head-down drops are removed
- the show remains deterministic and operator-friendly
- dry-run artifacts and tests clearly prove the change
