# Body Motion Tuning

This note describes the maintained tuning model for the real head after the hardware-grounded expression redesign.

## Calibration Authority

Hardware authority:

- `runtime/calibrations/robot_head_live_v1.json`

Human-facing limits:

- [robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md)

The body layer derives usable motion from calibration plus per-lane tuning. It does not assume the template profile is the real head.

## Active Tuning Lanes

Maintained tuning files:

- `runtime/body/semantic_tuning/robot_head_live_v1.json`
- `runtime/body/semantic_tuning/robot_head_investor_show_v3.json`
- `runtime/body/semantic_tuning/robot_head_investor_show_v4.json`
- `runtime/body/semantic_tuning/robot_head_investor_show_v5.json`
- `runtime/body/semantic_tuning/robot_head_investor_show_v6.json`
- `runtime/body/semantic_tuning/robot_head_investor_show_v7.json`
- `runtime/body/semantic_tuning/robot_head_investor_show_v8.json`

Operationally, the maintained lanes are:

- `default_live`
  - general companion behavior
  - held expressions only
  - conservative envelope
- focused proof lanes `V3-V7`
  - one family per atomic `body_range_demo`
  - explicit neutral before and after
  - `speed=100`, `acceleration=32`
- expressive proof lane `V8`
  - one atomic `body_expressive_motif` per cue
  - conservative structure, stronger eye area
  - `speed=90`, `acceleration=24`

## Hardware-Grounded Design Rules

The expression layer is now grounded in the maintained catalog described in [hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md).

The practical rules are:

- structural units are limited to head turn, neck pitch, and neck tilt
- expressive units are limited to eyes, lids, winks, and brows
- public held states are eye-area-only configurations
- dynamic expression is authored as motifs, not arbitrary composite poses
- structural motion and eye-area motion must be sequenced, not changed concurrently
- expressive groups release before structural return

## Family Priorities

The body should read larger mainly through:

- head yaw for presence and direction
- neck tilt and pitch for deliberate structural change
- eyes for directional refinement
- lids and brows for emotional readability

The current hardware truth is:

- head and neck should remain comparatively conservative
- eyes, lids, and brows provide most of the expressive read
- the eye area is the main margin-limited region on the current head

## Verified Evidence Ladder

The current tuning model is backed by the live proof ladder:

- V3: head yaw
- V4: eye yaw and eye pitch
- V5: lids and blink
- V6: brows
- V7: neck tilt and pitch
- V8: expressive motifs using the grounded runtime

That ladder is important because V8 tuning should inherit from verified family capability rather than inventing unsupported expressions.

## Current Safe Patterns

These are the maintained motion patterns:

- `body_range_demo`
  - use for V3-V7 family proofs
  - one atomic animation
  - best transport shape for proving one family
- grounded persistent states
  - held eye-area configurations only
  - no structural dependency
- `body_expressive_motif`
  - use for sequential expressive behavior
  - structural hold first
  - expressive units set and release in sequence
  - full neutral at cue end

## Current Unsafe Or Unsupported Patterns

These patterns are not part of the maintained surface:

- narration-timed micro-beats as the primary expressive path
- direct public composite expressions that invent unsupported poses
- simultaneous structural and eye-area change
- free-form multi-servo composition without explicit sequencing rules
- using full raw neck limits for expressive behavior

## Practical Tuning Lessons

- one atomic animation per cue is materially more reliable than a chatty stream of body writes
- neutral writes before live runs are mandatory
- a `300s` live-motion lease is the maintained choice for slow multi-segment live demos
- family-specific backoff matters more than one global preset
- neck pitch still needs more protection than eyes, lids, or brows
- V8 failures are now mostly eye-area margin issues, not architecture issues

## Current Maintained Evidence References

- V3 head-yaw lane:
  - [performance-b84fcfc34f61](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-b84fcfc34f61)
  - limiting family: `head_yaw`
  - minimum remaining margin: `-0.75%`
- V8 expressive motif lane:
  - [performance-0d7a47c35d4f](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-0d7a47c35d4f)
  - clean motifs:
    - `guarded_close_right`
    - `guarded_close_left`
  - main limiting families:
    - `lower_lids`
    - `upper_lids`
    - `eye_yaw`
    - `eye_pitch`
    - `brows`

## Capability Export

Use the machine-readable grounded catalog instead of guessing what the hardware supports:

```bash
curl -sS http://127.0.0.1:8000/api/operator/body/expression-catalog | jq
```

That export is the maintained source of truth for:

- supported units
- supported persistent states
- supported motifs
- alias mapping
- evidence source
- safe tuning lane
