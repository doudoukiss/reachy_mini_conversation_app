# Investor Expressive Motion V8 Reference Run (2026-04-11)

## Scope

`investor_expressive_motion_v8` is now the maintained expressive-motif proof lane.

It is also the maintained dynamic layer inside the hardware-grounded expression architecture described in [hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md). Another branch should pair this run record with the machine-readable catalog export from `GET /api/operator/body/expression-catalog` instead of inferring support from older semantic pose code.

The governing runtime rule is:

- structural head or neck motion moves first
- the structural pose holds
- expressive units then set, hold, and release one controlled action at a time
- expressive groups return to neutral before structural return begins
- every cue ends with an explicit full-neutral confirm frame

This lane no longer uses `body_staged_sequence` as its primary authoring model. It now runs through `body_expressive_motif`.

## Runtime And Tuning

- show: `investor_expressive_motion_v8`
- session id: `investor-expressive-motion-v8`
- tuning: `runtime/body/semantic_tuning/robot_head_investor_show_v8.json`
- motion control: `speed=90`, `acceleration=24`
- target duration: `216s`
- segment duration: `18s`
- actual full-run elapsed time: about `274s`
- runtime mode: `desktop_serial_body`
- body driver: `serial`
- transport: `live_serial`
- port: `/dev/cu.usbmodem5B790314811`
- calibration: `runtime/calibrations/robot_head_live_v1.json`

## Motif Set

The maintained V8 lane currently uses these 12 motifs:

1. `attentive_notice_right`
2. `attentive_notice_left`
3. `guarded_close_right`
4. `guarded_close_left`
5. `curious_lift`
6. `reflective_lower`
7. `skeptical_tilt_right`
8. `empathetic_tilt_left`
9. `playful_peek_right`
10. `playful_peek_left`
11. `bright_reengage`
12. `doubtful_side_glance`

## Acceptance Cue-Smokes

The live acceptance sequence was run in the planned order.

### 1. Guarded close right

- run id: `performance-ff4b6d13bde8`
- artifact: `/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-ff4b6d13bde8`
- status: `completed`
- projection outcome: `live_applied`
- degraded: `false`

Recorded cue order from the artifact:

1. `structural_set`
2. `expressive_set` -> `close_both_eyes_slow`
3. `expressive_set` -> `brows_lower_both_slow`
4. `expressive_release` -> brows
5. `expressive_release` -> lids
6. `return_to_neutral`

Important result:

- this is the first maintained live proof that the head can turn, both eyes can stay closed, the brows can frown while the eyes stay closed, the brows can release while the eyes remain closed, the eyes can reopen, and only then the head returns

### 2. Guarded close left

- run id: `performance-d92191a96cd3`
- artifact: `/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-d92191a96cd3`
- status: `completed`
- projection outcome: `live_applied`
- degraded: `false`

Important result:

- the symmetric guarded-close motif also works live under the new motif runtime

### 3. Skeptical tilt right

- final tuned cue-smoke run id: `performance-8dc68cfeac61`
- artifact: `/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-8dc68cfeac61`
- status: `completed`
- projection outcome: `live_applied`
- degraded: `true`

Current limiting family:

- `brows`

Interpretation:

- the motif runtime is correct
- the remaining issue is pure expressive-family margin, not sequencing, transport, or an inability to hold state

### 4. Playful peek right

- final tuned cue-smoke run id: `performance-595c7a25d725`
- artifact: `/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-595c7a25d725`
- status: `completed`
- projection outcome: `live_applied`
- degraded: `true`

Current limiting families after motif-only trims:

- `brows`
- `eye_yaw`

Important tuning result:

- wink-related lid margin improved enough to clear the floor after the motif-local trims
- the remaining limiter is the side-eye plus raised-brow combination, not the held wink itself

## Full V8 Live Run

- run id: `performance-0d7a47c35d4f`
- artifact: `/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-0d7a47c35d4f`
- status: `completed`
- overall projection outcome: `live_applied`
- preview only: `false`

All 12 motifs executed live.

Two motifs are now clean end to end:

- `guarded_close_right`
- `guarded_close_left`

The remaining 10 motifs are still margin-degraded, but they all completed `live_applied` and stayed on the intended motif runtime path.

Current degraded motifs on the maintained run:

- `attentive_notice_right`
- `attentive_notice_left`
- `curious_lift`
- `reflective_lower`
- `skeptical_tilt_right`
- `empathetic_tilt_left`
- `playful_peek_right`
- `playful_peek_left`
- `bright_reengage`
- `doubtful_side_glance`

## Current Outcome

What is now solved:

- V8 no longer depends on the old flat staged-accent model
- V8 now supports held expressive state and staged group release
- the guarded-close behavior requested by the user is implemented on real hardware
- the full 12-cue show executes end to end without falling into `preview_only`
- remaining failures are attributable to specific expressive families, not to a sequencing bug

What is still tight:

- overall worst families on the full run were `lower_lids`, `upper_lids`, `eye_yaw`, `eye_pitch`, and `brows`
- structural families stayed comparatively conservative:
  - `head_yaw` floor: `10.0%`
  - `head_pitch_pair` floor: `33.67%`
- eye-area floors on the maintained run were:
  - `lower_lids`: `0.25%`
  - `upper_lids`: `0.43%`
  - `eye_yaw`: `1.5%`
  - `eye_pitch`: `2.2%`
  - `brows`: `3.0%`

This confirms the architectural decision:

- head and neck are no longer the primary blocker in V8
- exact expression on this lane is now constrained mainly by eye-area amplitude stacking

## Practical Lessons

- `body_expressive_motif` is the correct long-term runtime shape for intentional expression on this head
- held expressive state matters; the old auto-recover accent model could not achieve the guarded-close behavior
- the strongest live result so far comes from:
  - conservative structural motion
  - expressive state held in sequence
  - explicit group-by-group release
- motif-local trimming works better than global show retuning
- the guarded-close motifs are already production-usable as proof behaviors
- the next quality step for V8 is motif-by-motif eye-area tuning, not another architecture rewrite
