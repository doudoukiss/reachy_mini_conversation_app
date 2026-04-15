# 02. Live frame scheduler and animation visibility

This plan fixes the most important execution bug first: **multi-frame actions must become visibly real on hardware**.

## Goal

Make the live embodied path honor each compiled frame's timing so gestures and animations become readable on the robot.

## Scope

Touch only the embodiment/live execution path needed to make compiled animations physically visible.

Primary files likely involved:

- `src/embodied_stack/body/serial/driver.py`
- `src/embodied_stack/body/driver.py`
- optionally a new helper under `src/embodied_stack/body/serial/`
- targeted tests under `tests/body/`

## Step-by-step design

### Step 1 — Introduce a real frame execution loop

Refactor `FeetechBodyBridge.apply_compiled_animation()` so it does **not** blast all frames immediately.

Required behavior:

1. Send frame N.
2. Wait for its effective transition time.
3. Respect its `hold_ms` if present.
4. Move to frame N+1.
5. Poll final health at the end, and optionally poll intermediate health for debugging.

Implementation guidance:

- compute an effective per-frame dwell time from `duration_ms + hold_ms`
- chunk waiting in small sleeps so cancellation and future instrumentation remain possible
- keep the current servo `speed` and `duration_ms` payload behavior, but add **host-side dwell** between frames

### Step 2 — Record per-frame execution details in audit output

The show now needs stronger proof that a gesture truly executed.

Add audit detail such as:

- `executed_frame_count`
- `executed_frame_names`
- `per_frame_duration_ms`
- `per_frame_hold_ms`
- `elapsed_wall_clock_ms`
- `final_frame_name`

This should end up visible in the command audit or motion result payload so dry runs and live runs can be compared.

### Step 3 — Preserve current single-frame behavior

Single-frame expressions and gazes must continue working exactly as before.

Acceptance rule:

- single-frame actions should still complete with equivalent results
- only multi-frame readability should materially change

### Step 4 — Keep preview behavior deterministic

Do not break virtual preview.

The preview path already represents the intended motion structure well enough. The live path must catch up to that behavior rather than rewriting the preview semantics.

### Step 5 — Add a regression test proving `double_blink` is no longer collapsed

Write a test using a fake transport or mocked `_send_frame` timestamps.

The test should prove:

- `double_blink` sends multiple frames
- there is measurable dwell between frames
- the total elapsed time is at least the sum of transition/hold timing minus a small scheduling tolerance

Do the same for `youthful_greeting` or `soft_reengage`.

## Important design choice

The timing fix belongs in the **live animation execution path**, not in the show runner.

Reason:

- `double_blink`, `wink`, `youthful_greeting`, and `soft_reengage` should be readable everywhere they are used
- this is a body-runtime correctness issue, not just a V1 show issue

## Guardrails

- Do not increase servo speed or acceleration here.
- Do not change joint hard limits here.
- Do not rewrite action authoring until the execution loop is fixed.

## Acceptance criteria

Codex should consider this plan complete only when all of the following are true:

1. `double_blink` is visibly readable on hardware.
2. `youthful_greeting` visibly stages through its intermediate beats instead of collapsing.
3. `soft_reengage` visibly stages through its intermediate beats instead of collapsing.
4. The audit trail contains enough information to prove multi-frame execution occurred.
