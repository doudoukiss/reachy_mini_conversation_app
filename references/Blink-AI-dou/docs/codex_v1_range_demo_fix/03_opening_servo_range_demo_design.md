# 03. Opening servo range demo design

This plan adds the requested **full-range opening demonstration** at the start of `investor_ten_minute_v1`.

## Goal

Before the regular scripted show begins, run a dedicated embodied sequence that makes the robot visibly exercise the usable range of every active joint.

This must be:

- much bolder than the current smoke-safe semantics
- still inside calibrated safe operating limits
- deterministic
- visually legible for a live operator or investor
- clearly separated from the main product behavior layer

## Architectural decision

Implement this as a **show-specific cue kind**, not as a normal planner-facing semantic action.

Recommended name:

- `PerformanceCueKind.BODY_RANGE_DEMO`

Recommended preset name:

- `investor_show_joint_envelope_v1`

Why this is the right choice:

- the user explicitly asked for a servo demonstration, not a general companion behavior
- this is a demo-only operator feature
- it should not pollute the long-term semantic expression library
- it can safely use calibrated raw target planning internally while keeping the planner boundary clean

## Files likely involved

- `src/embodied_stack/shared/contracts/operator.py`
- `src/embodied_stack/demo/performance_show.py`
- new: `src/embodied_stack/demo/body_range_demo.py`
- optionally new data/preset file under `src/embodied_stack/demo/data/` or `runtime/body/`
- tests under `tests/demo/` and `tests/body/`

## Core design

### A. Use calibrated usable bounds, not tiny smoke-test clamps

Do **not** reuse `motion_smoke_limit()` for this sequence. That utility is intentionally too small for the new requirement.

Instead compute a **usable demo band** from calibration or profile values:

- `usable_min = raw_min + safety_margin_counts`
- `usable_max = raw_max - safety_margin_counts`

Then optionally apply a near-full-range fraction relative to neutral:

- `target_low = neutral - floor((neutral - usable_min) * demo_fraction)`
- `target_high = neutral + floor((usable_max - neutral) * demo_fraction)`

Recommended starting fractions and margins:

| Joint family | Demo fraction | Margin counts |
|---|---:|---:|
| head yaw | 0.92 | 30 |
| head pitch pair | 0.90 | 50 |
| head roll (single-side pair move) | 0.90 | 50 |
| eye yaw | 0.92 | 25 |
| eye pitch | 0.92 | 25 |
| lids | 0.90 | 20 |
| brows | 0.92 | 15 |

These values are intentionally bold, but they still avoid commanding hard stops directly.

### B. Demonstrate all eleven active joints visibly

The sequence must reveal every servo’s usable contribution.

Recommended order:

1. neutral settle
2. **ID1** head yaw: left extreme → right extreme → center
3. **IDs2+3 pair pitch**: full up → full down → center
4. **ID2 contribution**: right tilt extreme → center
5. **ID3 contribution**: left tilt extreme → center
6. **ID9** eye yaw: left → right → center
7. **ID8** eye pitch: up → down → center
8. **ID5** upper lid left: open → close → center
9. **ID7** upper lid right: open → close → center
10. **ID4** lower lid left: open → close → center
11. **ID6** lower lid right: open → close → center
12. **ID10** brow left: raise → lower → center
13. **ID11** brow right: raise → lower → center
14. optional combined accent: both lids brisk close/open, both brows raise/lower
15. finish in a friendly, level pose

This is the most direct way to satisfy “show me what it can really do.”

### C. Respect the neck coupling rules explicitly

For IDs 2 and 3:

- pitch up = pair A toward high, pair B toward low
- pitch down = pair A toward low, pair B toward high
- tilt right = pair A moves while pair B stays near neutral
- tilt left = pair B moves while pair A stays near neutral

Never stack full-range pitch and full-range roll together in the range demo.

### D. Timing profile

Make the sequence bold and readable, not timid.

Recommended first-pass timing:

- transition per directional sweep: `300–360 ms`
- end hold per extreme: `180–260 ms`
- center recover: `220–300 ms`
- lids/brows can be slightly faster than neck

The demo should feel deliberate and impressive, not like a calibration utility.

### E. Presentation layer

The show should surface a simple caption or subtitle during the opening range demo.

Suggested caption behavior:

- “Motion envelope” title at the top
- optional sublabels like “head yaw”, “eye pitch”, “brows”, etc.

This helps investors understand that the opening is intentional, not random motion.

## Implementation notes

### Option 1 (preferred)

Create a `body_range_demo` cue kind handled directly by `PerformanceShowRunner`.

The cue builds and executes a deterministic set of raw target frames using calibration-aware bounds.

### Option 2 (acceptable fallback)

Create a dedicated demo-only body module that returns a `CompiledAnimation` or frame sequence, but keep it **outside** the general semantic library.

Do not hide this behind a normal social-expression name.

## Live-safety behavior

The range demo may run only when:

- live transport is confirmed
- a non-template live calibration is present
- motion is armed
- the show is not in preview-only body mode

Fallback behavior:

- if any prerequisite is missing, emit a degraded cue result and skip the live demo rather than pretending it ran

## Required artifact output

The range demo should emit a machine-readable summary including:

- calibration source path used
- per-joint demo low/high/neutral targets
- executed frame count
- any clamping notes
- final health/readback snapshot if available

## Acceptance criteria

1. The first embodied segment of the V1 show is the new range demo.
2. Every active joint’s usable range is visibly demonstrated.
3. The neck pair is shown through both pitch and roll behavior.
4. The demo uses near-full calibrated range rather than tiny smoke clamps.
5. The robot ends in a stable center pose before the normal script begins.
