# Body Expression Model

See also:
- [body_motion_tuning.md](/Users/sonics/project/Blink-AI/docs/body_motion_tuning.md) for the calibration-derived `default_live` and `demo_live` tuning lanes, kinetics profiles, and operating-band policy.

## Neutral-Centered Ratio Model

Blink-AI now treats lids and brows as **calibrated around hardware neutral**, not around raw min/max extremes.

- Planner-facing APIs still use the same semantic expression, gaze, gesture, and animation names.
- Inside the body stack, ratio joints are authored around a `neutral_ratio` derived from:
  - saved live calibration when present
  - otherwise the head profile neutral values
- This corrects the previous mismatch where `BodyPose()` looked visually wide-eyed and low-brow even when a semantic action intended "neutral."

For ratio joints:

- positive/open/raise joints use `(neutral - raw_min) / (raw_max - raw_min)`
- mirrored raw-minus or close-direction joints use `(raw_max - neutral) / (raw_max - raw_min)`

If the live calibration file is missing, the compiler falls back safely to profile-derived neutral ratios.

## Motion Envelopes And Live Tuning Lanes

The body layer now applies three typed motion envelopes:

- `idle`: calm baseline and safe-idle behavior
- `social`: normal companion and investor-show held expressions
- `accent`: readable transient beats and stronger public demo moments

Each envelope limits:

- head yaw
- head pitch
- head roll
- eye yaw
- eye pitch
- upper-lid deviation from neutral
- lower-lid deviation from neutral
- brow deviation from neutral

Transient blink and wink frames may use larger lid travel than held expressions. Held expressions are intentionally kept away from endstops.

The compiler also enforces a pitch-roll budget so the coupled neck pair cannot be pushed too hard when pitch and roll stack in the same beat.

These envelopes sit underneath two body-only live tuning lanes:

- `default_live` for stable companion behavior
- `demo_live` for bolder investor/operator behavior that is still backed off from the saved live limits

## Expression Design Direction

The robot should become more expressive mainly through:

- clearer head yaw
- more legible pitch and roll participation
- stronger brow contrast
- cleaner timing on transient blink and wink beats

It should **not** become bolder by simply opening the eyes wider or pinning lids and brows near their limits.

That means:

- eyes handle precision
- head handles presence
- brows handle emotional readability
- lids handle warmth, focus, and punctuation

## Public-Live Safety Direction

The public investor-show path now uses show-specific `social` and `accent` envelopes so live behavior can get more legible without changing repo-wide safety defaults.

The safety strategy is:

- broaden head and brow contribution first
- keep eye travel in the existing public-safe band
- keep near-full lid closure reserved for transient blink and wink frames
- recover all gestures and animations into a stable neutral or socially calm end state

This keeps investor demos bolder and easier to read while staying inside the same semantic planner/body boundary and the existing `safe_speed` / `safe_acceleration` behavior.
