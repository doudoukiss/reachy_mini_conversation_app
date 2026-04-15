# 05. Tests, acceptance gates, and operator validation

This plan ensures the fixes are provable rather than subjective.

## Goal

Make the new behavior testable in three layers:

1. unit-level body execution correctness
2. show-level asset and sequencing correctness
3. live operator validation on the real head

## A. Unit and integration tests

### 1. Frame timing tests

Add tests proving that live compiled animations are no longer collapsed.

Required tests:

- `double_blink` executes multiple frames with non-zero dwell
- `youthful_greeting` executes intermediate frames in order
- `soft_reengage` executes intermediate frames in order

Use a fake transport or monkeypatched time source if needed.

### 2. Head-drop regression tests

Add tests around the authored final poses.

Required assertions:

- rewritten `youthful_greeting` final pose is not visibly downward
- rewritten `soft_reengage` final pose is not visibly downward
- `listen_attentively` head pitch stays within the newly approved shallow band
- `safe_idle` head pitch stays level or nearly level

### 3. Range-demo planning tests

Add tests that the new range demo:

- plans targets for all eleven active joints
- uses calibrated bounds when available
- falls back to profile bounds when calibration is missing
- respects per-family safety margins
- never commands a target outside calibrated hard limits
- keeps pitch and roll demonstrations separate enough to avoid pair overdrive

### 4. Show asset tests

Update tests around `investor_ten_minute_v1` so they assert:

- the first segment is the new motion-envelope segment
- the new range-demo cue exists
- the show still totals 600 seconds unless the spec is intentionally changed everywhere
- signature expressive cues like `double_blink` remain present

### 5. Motion-proof artifact tests

Add assertions that dry-run or preview results now include:

- range-demo planning output
- executed-frame metadata for multi-frame actions
- degraded status if live prerequisites for the range demo are missing

## B. Operator live checklist

Before running on hardware:

1. verify confirmed live transport
2. verify motion arm lease is active
3. verify non-template calibration is present
4. verify mechanical clearances
5. run neutral write once before the show

## C. Live validation sequence for this feature

Run in this order:

1. range demo only
2. `double_blink` only
3. `youthful_greeting` only
4. `soft_reengage` only
5. full V1 show

At each step verify:

- motion is clearly visible
- no scraping or stall sound
- no unexpected asymmetric neck behavior
- no aggressive droop at the start or during fallback beats

## D. Release gates

Do not mark this work complete until all of the following are true:

- timing tests pass
- show asset tests pass
- range-demo planning tests pass
- the opening range demo visibly shows the usable envelope of every active joint
- `double_blink` is unmistakably visible on the real robot
- the operator no longer reports the two abrupt head-down drops

## E. Deliverables Codex should leave behind

- code changes
- updated tests
- updated show JSON
- updated docs explaining the range demo and the animation timing fix
- a short verification summary with exact commands used
