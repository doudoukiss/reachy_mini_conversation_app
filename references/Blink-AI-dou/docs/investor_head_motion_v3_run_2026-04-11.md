# Investor Head Motion V3 Run Record (2026-04-11)

This document records the current investor-focused V3 head-motion proof and the latest slowed live run that was used as the maintained reference on 2026-04-11.

Use this document when another branch needs the exact V3 scope, playback settings, artifact paths, and the current interpretation of what happened on hardware.

## Scope

V3 is intentionally narrow. It is not a conversational investor show.

It exists to prove one thing clearly:

- the real head can execute a single atomic head-yaw-only motion proof lane under live serial control

The V3 motion scope is exactly:

- rotate the head as far left as possible
- rotate the head as far right as possible
- sweep the head strongly toward the left with the widest possible motion
- sweep the head strongly toward the right with the widest possible motion

Everything else is out of scope for V3.

## Implementation Files

The maintained V3 implementation lives in:

- [src/embodied_stack/body/range_demo.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/range_demo.py)
- [src/embodied_stack/demo/data/performance_investor_head_motion_v3.json](/Users/sonics/project/Blink-AI/src/embodied_stack/demo/data/performance_investor_head_motion_v3.json)
- [runtime/body/semantic_tuning/robot_head_investor_show_v3.json](/Users/sonics/project/Blink-AI/runtime/body/semantic_tuning/robot_head_investor_show_v3.json)
- [src/embodied_stack/demo/performance_show.py](/Users/sonics/project/Blink-AI/src/embodied_stack/demo/performance_show.py)
- [Makefile](/Users/sonics/project/Blink-AI/Makefile)

The V3 sequence name is:

- `investor_head_yaw_v3`

The V3 show name is:

- `investor_head_motion_v3`

## Why V3 Exists

V3 was created after investor V1 and V2 remained too abstract and too chatty for the current hardware.

The standalone servo showcase was materially more reliable because it used one atomic compiled animation under one live body transaction. V3 follows that same pattern:

- one atomic `body_range_demo` cue
- one head-yaw-only proof lane
- explicit center returns between major movements
- no narration-timed body beats
- no expression recipes
- no primitive playlists
- no broad multi-family coordination

## Final Maintained Timing

The first V3 version was too quick for easy operator observation, so it was slowed substantially.

The maintained slowed V3 timing is:

- target show duration: `48s`
- body motion control override:
  - speed: `100`
  - acceleration: `32`

This replaced the earlier shorter variant:

- earlier target duration: `12s`
- earlier motion control override:
  - speed: `120`
  - acceleration: `40`

The slower version was adopted because the operator reported that only the leftward motion was clearly visible in earlier passes.

## Executed Frame Plan

The canonical slowed V3 live sequence is an 11-frame atomic range-demo animation:

1. `neutral_settle`
2. `rotate_left_max`
3. `rotate_left_center`
4. `rotate_right_max`
5. `rotate_right_center`
6. `sweep_left_prep_right`
7. `sweep_left_max`
8. `sweep_left_center`
9. `sweep_right_prep_left`
10. `sweep_right_max`
11. `sweep_right_center`

The four investor-visible motions are therefore:

- max left rotation
- max right rotation
- strong left sweep
- strong right sweep

with explicit center recovery between them and a final center return at the end.

## Live Command Path Used

The maintained live execution path for the reference V3 run was:

Arm live motion:

```bash
cd /Users/sonics/project/Blink-AI
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --profile src/embodied_stack/body/profiles/robot_head_v1.json \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  arm-live-motion --ttl-seconds 300
```

Write neutral:

```bash
cd /Users/sonics/project/Blink-AI
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  --profile src/embodied_stack/body/profiles/robot_head_v1.json \
  --calibration runtime/calibrations/robot_head_live_v1.json \
  write-neutral --duration-ms 800 --confirm-live-write
```

Run V3:

```bash
cd /Users/sonics/project/Blink-AI
make investor-show-v3-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

Disarm after the run:

```bash
cd /Users/sonics/project/Blink-AI
PYTHONPATH=src uv run python -m embodied_stack.body.calibration disarm-live-motion
```

## Reference Live Run

The maintained slowed live reference run is:

- run id: `performance-b84fcfc34f61`
- artifact directory: [runtime/performance_runs/performance-b84fcfc34f61](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-b84fcfc34f61)
- run summary: [runtime/performance_runs/performance-b84fcfc34f61/run_summary.json](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-b84fcfc34f61/run_summary.json)
- cue results: [runtime/performance_runs/performance-b84fcfc34f61/cue_results.json](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-b84fcfc34f61/cue_results.json)

Run summary:

- `show_name=investor_head_motion_v3`
- `status=completed`
- `preview_only=false`
- `degraded=true`
- `elapsed_seconds=43.46`
- `body_fault_trigger_cue_id=head_motion_v3_run`
- `motion_outcome=live_applied`
- `worst_actuator_group=head_yaw`

Cue summary for `head_motion_v3_run`:

- `cue_kind=body_range_demo`
- `status=degraded`
- `success=true`
- `motion_outcome=live_applied`
- `actual_duration_ms=41116.04`
- `sequence_name=investor_head_yaw_v3`
- `speed=100`
- `acceleration=32`
- `executed_frame_count=11`

Final readback from the motion-margin record:

- the cue ended near head-yaw neutral
- `head_yaw` remained the limiting family with minimum remaining margin `-0.75%`

The saved head-yaw neutral in the current live calibration is:

- `2096`

So this run ended close to center, not parked at an extreme.

## What This Run Proved

This run proved the following on the software side:

- the V3 lane did execute as one atomic range-demo motion
- the live body path applied the command successfully
- the slowed sequence included both rightward and leftward motions
- the sequence returned close to neutral by the end of the cue

This run did not prove that the physical head visibly followed the rightward motions as clearly as the software commanded them.

That distinction matters.

The artifact proves that software sent the rightward frames. If an operator visually sees only leftward motion, the remaining problem is not “the rightward steps were omitted from the V3 sequence.” The remaining problem is hardware-following behavior under load, backlash, stalling, or some other physical effect on the real head.

## Health And Degradation Notes

The slowed reference run still degraded on live health:

- worst remaining margin group: `head_yaw`
- `head_yaw` minimum remaining margin in the motion-margin record: `-0.75%`
- the practical current interpretation is that V3 still executes correctly, but the maintained head is now yaw-limited on the latest pass

So the correct interpretation of the reference run is:

- motion path success: yes
- full clean health pass: no
- evidence that both directions were commanded: yes
- evidence that rightward motion is visually reliable on hardware: not yet

## Recommended Future Debug Order

If another branch needs to continue V3 debugging, use this order:

1. Verify serial health first with `make serial-doctor`.
2. Write neutral before every V3 run.
3. Run the slowed V3 lane exactly as documented here.
4. If the operator still sees only leftward motion, isolate a right-only proof lane next rather than broadening V3.

The next clean diagnostic would be:

1. center
2. right max
3. center
4. strong right sweep
5. center

That isolates whether rightward head-yaw motion is physically failing or only becoming unclear inside the four-motion V3 sequence.

## Status For Future Reference

As of 2026-04-11:

- V3 is the narrowest investor-facing live motion proof in the repo
- the maintained V3 reference is the slowed `48s` variant
- the canonical run record is `performance-b84fcfc34f61`
- the live-motion lease was disarmed after the reference run

Use this document as the branch-handoff truth for the current V3 lane unless a newer run record explicitly supersedes it.
