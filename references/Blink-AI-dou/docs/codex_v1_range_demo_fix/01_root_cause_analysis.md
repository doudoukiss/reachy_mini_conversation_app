# 01. Root cause analysis

This document explains **why the current show still looks wrong on hardware** even though the docs and code claim the new motions exist.

## A. The show asset already references the new motions

The V1 show JSON already includes the new expressive actions.

Examples:

- `arrival_greeting` uses `youthful_greeting` in `src/embodied_stack/demo/data/performance_investor_ten_minute_v1.json:31-35`
- `arrival_line_1` uses `double_blink` in the narration motion track in `src/embodied_stack/demo/data/performance_investor_ten_minute_v1.json:72-84`
- the show also references `soft_reengage`, `playful_peek_left`, `playful_peek_right`, `brow_raise_soft`, and `brow_knit_soft`

So the problem is **not** “the show file forgot to call the new actions.”

## B. The new gestures and animations compile into real multi-frame timelines

`double_blink` is implemented as a real multi-frame gesture with:

- `start`
- `blink_one`
- `recover_one`
- `blink_two`
- `recover_two`

See `src/embodied_stack/body/animations.py:123-142`.

`youthful_greeting` is implemented as:

- `friendly`
- `curious_bright`
- `double_blink`
- `listen_attentively`

See `src/embodied_stack/body/animations.py:381-396`.

`soft_reengage` is implemented as:

- `look_down`
- `focused_soft`
- `double_blink`
- `listen_attentively`

See `src/embodied_stack/body/animations.py:397-412`.

So the new motions **do** exist in the body layer.

## C. The live bridge is collapsing multi-frame actions on hardware

This is the critical bug.

In `src/embodied_stack/body/serial/driver.py:52-84`, `apply_compiled_animation()` loops over compiled frames and calls `_send_frame(frame)` immediately for each frame:

- there is **no wait** for `duration_ms`
- there is **no wait** for `hold_ms`
- there is **no per-frame dwell**
- health is only polled after the final frame

That means:

- the preview path can still look correct
- the compiled animation structure can still look correct in tests
- but on real hardware, multi-frame gestures and animations collapse into the final or near-final command sequence

This directly explains why `double_blink` and other new expressive motions feel “missing in practice.”

## D. Why the head drops down hard

There are two reasons.

### D1. Collapsed animations expose the final frame instead of the intended sequence

Both `youthful_greeting` and `soft_reengage` terminate in `listen_attentively`.

- `youthful_greeting` final frame: `listen_attentively` (`src/embodied_stack/body/animations.py:390-395`)
- `soft_reengage` final frame: `listen_attentively` (`src/embodied_stack/body/animations.py:406-411`)

If the live bridge collapses the animation, the operator will mostly perceive an abrupt jump into that final listening pose instead of the staged expressive path.

### D2. `listen_attentively` is authored with negative head pitch

`listen_attentively` is currently defined with `head_pitch=-0.05` in `src/embodied_stack/body/library.py:96-104`.

That is a legitimate mild listening pose **if entered smoothly**.

But once the multi-frame animation collapses, it becomes a visible head-down drop.

### D3. `soft_reengage` also begins with a deliberate downward glance

`soft_reengage` begins with `look_down_briefly` and then still ends in `listen_attentively`.

So when frame timing is broken, the sequence can read as a more aggressive down motion than intended.

## E. Secondary risk: the repo snapshot does not include the live calibration file

`load_head_calibration()` falls back to a template calibration if the configured path does not exist.
See `src/embodied_stack/body/calibration.py:289-314`.

The current repo bundle does not contain `runtime/calibrations/robot_head_live_v1.json`.

Implications:

- Codex cannot assume the repo snapshot contains the real neutral offsets of the physical robot
- if the local live machine uses an external calibration file, the actual perceived neck neutral may differ from the template
- small negative head-pitch offsets can look more severe than the source code suggests if the physical neutral is not truly level

This does **not** explain the missing double blink by itself, but it can make the head-drop symptom worse.

## F. Existing bench utilities are too conservative for the requested opening range reveal

The existing bench helper `motion_smoke_limit()` clamps:

- head and eye joints to ±100 raw counts
- lids and brows to ±60 raw counts

See `src/embodied_stack/body/serial/bench.py:97-100`.

That is useful for smoke tests, but it is not enough for the new “show me the true usable range” requirement.

So the new opening demo **must not** simply reuse the small smoke clamp unchanged.

## G. Design conclusion

Do **not** start by tweaking expression values alone.

The correct order is:

1. fix live frame timing
2. add a dedicated show-specific range demo path
3. retune the down-pitch expressions and animation endings
4. rebuild the V1 opening around the new range demo and visible expressive cues

If Step 1 is skipped, Codex can keep editing show assets forever and the real robot will still underperform.
