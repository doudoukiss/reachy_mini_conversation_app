# Hardware-Grounded Expression Architecture

This document is the maintained design reference for the robot-head expression layer.

Use it when another branch needs to understand what the hardware can actually do, how that capability is represented in software, and how to avoid the old mismatch where expression-side logic invented poses the hardware could not sustain.

## Design Goal

The expression layer is now driven backward from validated hardware capability.

That means:

- the software does not invent public expressions from unconstrained composite poses
- the maintained catalog lists only what the hardware has evidence for
- structural motion and eye-area motion are sequenced explicitly
- unsupported names must resolve through explicit aliases or reject

## Canonical Source Of Truth

The canonical catalog lives in:

- [grounded_catalog.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/grounded_catalog.py)

It exports:

- supported structural units
- supported expressive units
- supported persistent states
- supported motifs
- alias mapping
- evidence source
- safe tuning lane
- per-entry constraints

Machine-readable export:

- API: `GET /api/operator/body/expression-catalog`
- implementation entrypoint: [app.py](/Users/sonics/project/Blink-AI/src/embodied_stack/brain/app.py)

## Supported Structural Units

These are the only maintained structural units:

- `head_turn_left_slow`
- `head_turn_right_slow`
- `head_pitch_up_slow`
- `head_pitch_down_slow`
- `head_tilt_left_slow`
- `head_tilt_right_slow`

Structural units are conservative by design and must not change concurrently with eye-area motion.

## Supported Expressive Units

These are the only maintained expressive units:

- `eyes_left_slow`
- `eyes_right_slow`
- `eyes_up_slow`
- `eyes_down_slow`
- `close_both_eyes_slow`
- `blink_both_slow`
- `double_blink_slow`
- `wink_left_slow`
- `wink_right_slow`
- `brows_raise_both_slow`
- `brows_lower_both_slow`
- `brow_left_raise_slow`
- `brow_left_lower_slow`
- `brow_right_raise_slow`
- `brow_right_lower_slow`

These units are grounded in the V4-V6 family proofs and are the main expressive surface on current hardware.

## Grounded Persistent States

Public held expressions are now grounded states, not direct composite pose truth.

Maintained states:

- `neutral`
- `friendly`
- `listen_attentively`
- `thinking`
- `focused_soft`
- `concerned`
- `confused`
- `safe_idle`

Rules:

- persistent states are eye-area-only held configurations
- no persistent state depends on concurrent structural-plus-eye-area motion
- structural behavior belongs in motifs, not persistent states

Legacy semantic names remain compatible through explicit aliases. Examples:

- `warm_greeting -> friendly`
- `curious -> focused_soft`
- `brow_knit_soft -> concerned`

## Dynamic Expressive Motifs

Dynamic expression is authored through named motifs.

Current maintained motifs:

- `attentive_notice_right`
- `attentive_notice_left`
- `guarded_close_right`
- `guarded_close_left`
- `curious_lift`
- `reflective_lower`
- `skeptical_tilt_right`
- `skeptical_tilt_left`
- `empathetic_tilt_left`
- `empathetic_tilt_right`
- `playful_peek_right`
- `playful_peek_left`
- `bright_reengage`
- `doubtful_side_glance`

The motif registry lives in:

- [expressive_motifs.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/expressive_motifs.py)

## Runtime Model

The maintained dynamic runtime is `body_expressive_motif`.

Request contract:

- [operator.py](/Users/sonics/project/Blink-AI/src/embodied_stack/shared/contracts/operator.py)

Compiler/runtime:

- [compiler.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/compiler.py)
- [driver.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/driver.py)

The runtime tracks:

- `structural_state`
- `expressive_state`

Allowed step kinds:

- `structural_set`
- `expressive_set`
- `expressive_release`
- `hold`
- `return_to_neutral`

## Sequencing Rules

These rules are the core of the architecture:

1. Structural motion first.
   - Only one structural family changes at a time.
2. Structural hold before eye-area change.
   - Head or neck motion must settle before eyes, lids, or brows change.
3. One expressive unit change at a time.
   - No arbitrary multi-unit changes in a single expressive step.
4. Expressive state may persist.
   - A later expressive step must not implicitly release earlier expressive state.
5. Expressive release before structural return.
   - Eye-area groups return to neutral while structural pose is still held.
6. Final neutral confirm is mandatory.

Example maintained ordering:

1. head turns right
2. both eyes close and hold
3. brows lower and hold
4. brows release while eyes stay closed
5. lids reopen
6. head returns to neutral

That pattern is now implemented directly in the runtime, not approximated through auto-recover accents.

## Evidence Model

Every catalog entry carries hardware evidence.

Current evidence ladder:

- V3 head yaw proof
- V4 eye proof
- V5 lid proof
- V6 brow proof
- V7 neck proof
- V8 expressive motif proof

Clean live references for the strongest sequential-expression evidence:

- guarded close right:
  - [performance-ff4b6d13bde8](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-ff4b6d13bde8)
- guarded close left:
  - [performance-d92191a96cd3](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-d92191a96cd3)
- full V8 motif lane:
  - [performance-0d7a47c35d4f](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-0d7a47c35d4f)

## Implementation Flow

The maintained resolution path is:

1. planner-facing request or operator cue enters through semantic names
2. name resolves through the grounded catalog
3. compiler chooses one implementation kind:
   - `state`
   - `unit`
   - `motif`
4. runtime applies one atomic compiled animation
5. outcome records preserve:
   - grounding
   - evidence source
   - alias source
   - structural units used
   - expressive units used
   - release policy
   - whether the action returned to neutral

Unsupported names must not silently invent a pose.

## Integration Checklist For Another Branch

To connect quickly and avoid the old integration bugs:

1. Fetch the catalog:

```bash
curl -sS http://127.0.0.1:8000/api/operator/body/expression-catalog | jq
```

2. Confirm live transport:

```bash
make serial-doctor
```

3. Write neutral.

4. Reconfirm the hardware evidence ladder:

```bash
make investor-show-v3-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v4-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v5-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v6-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v7-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

5. Reconfirm grounded states with semantic smoke.

6. Run motif cue-smokes.

7. Run full V8 only after the ladder is green.

## What Not To Do

Do not reintroduce these patterns:

- direct public expression truth from `expression_pose()` composites
- concurrent structural and expressive changes
- narration-timed micro-beats as the main live expression path
- free-form expression synthesis without catalog support
- assuming head and neck can be pushed as hard as eyes, lids, or brows

## Related Docs

- [investor_demo.md](/Users/sonics/project/Blink-AI/docs/investor_demo.md)
- [investor_show_runbook.md](/Users/sonics/project/Blink-AI/docs/investor_show_runbook.md)
- [body_motion_tuning.md](/Users/sonics/project/Blink-AI/docs/body_motion_tuning.md)
- [robot_head_hardware_and_serial_handoff.md](/Users/sonics/project/Blink-AI/docs/robot_head_hardware_and_serial_handoff.md)
- [investor_expressive_motion_v8_run_2026-04-11.md](/Users/sonics/project/Blink-AI/docs/investor_expressive_motion_v8_run_2026-04-11.md)
