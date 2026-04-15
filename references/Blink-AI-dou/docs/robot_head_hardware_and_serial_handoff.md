# Robot Head Hardware And Serial Handoff

This document is a branch-handoff summary of the real robot head hardware, the maintained Mac connection path, and the current serial communication model used by Blink-AI.

Use this as the high-level shareable reference when another branch needs to understand:

- what the hardware is
- how the Mac connects to it
- how Blink-AI sends motion and reads health
- which files define the current protocol and operator workflow
- which parts are stable versus which parts are currently hardware-fragile

## Scope

This document covers the current 11-servo robot head on the maintained Mac serial path.

It does not try to restate every calibration number inline. For the current calibrated limits and live range findings, use:

- [docs/robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md)
- [docs/robot_head_live_revalidation_2026-04-10.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_revalidation_2026-04-10.md)

## Hardware Summary

The current real head is an 11-servo Feetech/STS3032-based assembly driven from the Mac over a serial bus.

Active joints:

- `head_yaw`
- `head_pitch_pair_a`
- `head_pitch_pair_b`
- `eye_yaw`
- `eye_pitch`
- `upper_lid_left`
- `upper_lid_right`
- `lower_lid_left`
- `lower_lid_right`
- `brow_left`
- `brow_right`

The neck uses a coupled pair:

- `head_pitch_pair_a` and `head_pitch_pair_b` together produce pitch
- those same two servos also participate in tilt, so family-level usable motion is not always identical to raw per-servo hard bounds

The current executable live calibration authority is:

- [runtime/calibrations/robot_head_live_v1.json](/Users/sonics/project/Blink-AI/runtime/calibrations/robot_head_live_v1.json)

The template fallback profile is:

- [src/embodied_stack/body/profiles/robot_head_v1.json](/Users/sonics/project/Blink-AI/src/embodied_stack/body/profiles/robot_head_v1.json)

## Host And Connection Topology

The maintained host path is Mac-first, not Windows-first.

Current intended topology:

1. Mac host runs the body runtime, operator console, calibration CLI, and investor/demo performance runner.
2. Mac opens one serial device connected to the servo bus.
3. Blink-AI speaks Feetech/STS packet protocol directly over that serial link.
4. The live body layer compiles semantic motion into per-joint raw targets and writes them to the servos.

Current known bench/live path:

- host: Mac
- transport mode: `live_serial`
- known port used on this branch: `/dev/cu.usbmodem5B790314811`
- maintained baud: `1000000`

Important operational rule:

- the serial port is effectively single-owner
- only one tool or runtime should own `/dev/cu.*` at a time
- if `serial-doctor`, Servo Lab, the investor show, or another process is already attached, later commands can fail with open/read errors even if the hardware is otherwise healthy

## Communication Stack

The live communication path is:

1. semantic command or animation request enters the body layer
2. body compiler converts semantics into `CompiledBodyFrame` targets
3. serial bridge maps joint targets onto servo IDs and raw register payloads
4. transport writes Feetech packets over the Mac serial port
5. readback and bench-health polling confirm position, torque state, status, and electrical telemetry

Primary source files:

- [src/embodied_stack/body/serial/protocol.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/protocol.py)
- [src/embodied_stack/body/serial/transport.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/transport.py)
- [src/embodied_stack/body/serial/bench.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/bench.py)
- [src/embodied_stack/body/serial/health.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/health.py)
- [src/embodied_stack/body/serial/driver.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/driver.py)

Shared contract definitions:

- [src/embodied_stack/shared/contracts/body.py](/Users/sonics/project/Blink-AI/src/embodied_stack/shared/contracts/body.py)
- [docs/protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)

## Feetech Protocol Details

The current wire protocol is Feetech-style framed serial packets.

Packet framing:

- header: `0xFF 0xFF`
- broadcast ID: `0xFE`
- checksum: inverted byte-sum over the packet body

Implemented instructions:

- `PING = 0x01`
- `READ = 0x02`
- `WRITE = 0x03`
- `REG_WRITE = 0x04`
- `ACTION = 0x05`
- `RECOVERY = 0x06`
- `RESET = 0x0A`
- `SYNC_READ = 0x82`
- `SYNC_WRITE = 0x83`

Important registers used by this branch:

- `0x28` torque switch
- `0x29` start acceleration
- `0x2A` target position
- `0x2E` running speed
- `0x38` present position
- `0x3A` present speed
- `0x3C` present load
- `0x3E` present voltage
- `0x3F` present temperature
- `0x40` async flag
- `0x41` status
- `0x42` moving
- `0x45` present current

Key communication patterns:

- `PING` to detect whether a servo ID replies
- `READ` for single-servo register reads
- `SYNC_READ` to read the same register block from multiple servos
- `WRITE` for single-servo writes
- `SYNC_WRITE` for simultaneous multi-servo movement writes

The bridge uses `build_target_position_payload(position, duration_ms, speed)` to write target position, transition duration, and effective speed together.

## Motion Control Settings

On this branch, speed and acceleration are treated as real transport settings, not just planner metadata.

Current live verified defaults from the maintained Mac path:

- safe speed: `120`
- safe acceleration: `40`

The focused family bring-up demos that actually worked live used a slower, more readable lane:

- demo speed: `100`
- demo acceleration: `32`

That slower setting is now the maintained default for the V3-V7 focused hardware proofs because it was materially easier to observe and less aggressive on the head than the earlier faster versions.

Relevant docs:

- [docs/serial_head_mac_runbook.md](/Users/sonics/project/Blink-AI/docs/serial_head_mac_runbook.md)
- [docs/robot_head_live_revalidation_2026-04-10.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_revalidation_2026-04-10.md)
- [docs/investor_head_motion_v3_run_2026-04-11.md](/Users/sonics/project/Blink-AI/docs/investor_head_motion_v3_run_2026-04-11.md)

Relevant operator surfaces:

- `motion-config`
- `power-preflight`
- `usable-range`
- `range-demo --sequence servo_range_showcase_v1`
- `servo-lab-*`
- `investor-show-v3-live`
- `investor-show-v4-live`
- `investor-show-v5-live`
- `investor-show-v6-live`
- `investor-show-v7-live`
- `investor-show-v8-live`

## Safety, Calibration, And Live Gating

The planner does not talk in raw servo IDs. Raw control stays inside the body layer, serial bridge, operator APIs, and calibration tooling.

Normal live motion depends on:

- a head profile
- a saved non-template live calibration
- an active live-motion arm lease
- a live serial transport that can open and confirm the port

The arm-lease file is:

- [runtime/serial/live_motion_arm.json](/Users/sonics/project/Blink-AI/runtime/serial/live_motion_arm.json)

The lease is managed by:

- `arm-live-motion`
- `disarm-live-motion`

The lease prevents accidental live motion from unarmed processes and also couples the live run to the specific port, baud, and calibration file.

## Operator Commands

The most useful commands for another branch are:

List and diagnose the serial path:

```bash
cd /Users/sonics/project/Blink-AI
make serial-doctor BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

Read live power/health at idle:

```bash
cd /Users/sonics/project/Blink-AI
make investor-power-preflight BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

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

Write neutral before a live focused-demo run:

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

Disarm live motion:

```bash
cd /Users/sonics/project/Blink-AI
PYTHONPATH=src uv run python -m embodied_stack.body.calibration disarm-live-motion
```

Run the standalone servo showcase:

```bash
cd /Users/sonics/project/Blink-AI
make servo-showcase-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

Run the investor cue smoke:

```bash
cd /Users/sonics/project/Blink-AI
make investor-show-cue-smoke BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

Run the focused hardware proof series:

```bash
cd /Users/sonics/project/Blink-AI
make investor-show-v3-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v4-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v5-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v6-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
make investor-show-v7-live BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
```

The focused V3-V7 targets now arm motion with a `300s` lease because the default short lease was long enough for single-step commands but too short for the slower multi-segment family demos.

## Grounded Expression Catalog

The maintained body-expression source of truth is now the hardware-grounded catalog:

- design reference: [hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md)
- implementation: [grounded_catalog.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/grounded_catalog.py)
- export endpoint: `GET /api/operator/body/expression-catalog`

The key branch-handoff rule is:

- do not infer expression capability from old semantic pose code
- inspect the grounded catalog instead

What the catalog defines:

- supported structural units
- supported expressive units
- supported persistent states
- supported motifs
- alias mapping
- evidence source
- safe tuning lane
- release and sequencing rules

Current maintained structural units:

- head turn left and right
- neck pitch up and down
- neck tilt left and right

Current maintained expressive units:

- eyes left and right
- eyes up and down
- both-lid close
- left wink
- right wink
- both-brow raise and lower
- left-brow raise and lower
- right-brow raise and lower

Current maintained persistent states:

- `neutral`
- `friendly`
- `listen_attentively`
- `thinking`
- `focused_soft`
- `concerned`
- `confused`
- `safe_idle`

Important rule:

- persistent states are eye-area-only held configurations
- structural motion belongs in motifs, not held expression states

## Maintained Runtime Surfaces

There are now three maintained live embodiment surfaces, and they should stay conceptually separate:

1. `robot_head_servo_range_showcase_v1`
   - standalone hardware/range proof
   - explicit near-limit or limit-oriented bench validation path
   - useful for bench truth, not the main investor expression surface

2. `investor_head_motion_v3` through `investor_neck_motion_v7`
   - focused family bring-up and operator-visible evidence ladder
   - one atomic `body_range_demo` per family unit
   - explicit neutral before and after
   - the current most reliable path for proving what each family can actually do

3. `investor_expressive_motion_v8`
   - motif-driven expressive proof lane
   - one atomic `body_expressive_motif` cue per segment
   - structural state held first, expressive units set and release afterward
   - the maintained proof that real sequential expression is achievable on the head

The old V1 and V2 investor shows are no longer maintained. Another branch should not rebuild on them.

This separation matters for handoff:

- V3-V7 are the family evidence ladder
- V8 is the expressive runtime proof built on top of that evidence

## Verified Focused Demo Series

As of 2026-04-11, the critical joint families have been brought up and verified through the focused V3-V7 sequence.

Shared pattern across the whole series:

- one atomic `body_range_demo` per family unit
- caption, then one live range-demo cue, then a pause
- no narration-timed body motion
- explicit neutral at the start and end of each animation
- slow live kinetics: `speed=100`, `acceleration=32`
- pre-show neutral write before the run
- `300s` live-motion arm lease for the whole demo

Reference live runs:

1. V3 head yaw
   - show: `investor_head_motion_v3`
   - reference run: [performance-b84fcfc34f61](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-b84fcfc34f61)
   - purpose: prove atomic head-yaw-only motion with explicit center returns
   - result: `live_applied`, final readback near neutral
   - current limiting margin: `head_yaw=-0.75%`

2. V4 eyes
   - show: `investor_eye_motion_v4`
   - reference run: [performance-cb00a731feb4](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-cb00a731feb4)
   - sequences: `investor_eye_yaw_v4`, `investor_eye_pitch_v4`
   - result: both segments `live_applied`
   - practical note: this family works, but it is still the tightest of the verified eye proofs, especially on `eye_pitch`
   - observed min margins:
     - `eye_yaw`: `1.5%`
     - `eye_pitch`: `0.7%`

3. V5 lids
   - show: `investor_lid_motion_v5`
   - reference run: [performance-565508ad7b31](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-565508ad7b31)
   - sequences: `investor_both_lids_v5`, `investor_left_eye_lids_v5`, `investor_right_eye_lids_v5`, `investor_blink_v5`
   - result: all four segments `live_applied`
   - observed min margins:
     - `both lids`: `10.14%`
     - `left eye lids`: `10.14%`
     - `right eye lids`: `10.57%`
     - `blink`: `10.14%`
   - practical note: this family only became reliable after backing lids off from the full showcase preset to the investor preset and extending the arm lease

4. V6 brows
   - show: `investor_brow_motion_v6`
   - reference run: [performance-b0b5d0fb439a](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-b0b5d0fb439a)
   - sequences: `investor_brows_both_v6`, `investor_brow_left_v6`, `investor_brow_right_v6`
   - result: all three segments `live_applied`
   - observed min margins:
     - `both brows`: `10.0%`
     - `left brow`: `10.0%`
     - `right brow`: `10.0%`
   - practical note: the first V6 run hit `0.0%` brow margin. V6 only became acceptable after moving brows off the full showcase preset and onto the investor preset

5. V7 neck
   - show: `investor_neck_motion_v7`
   - reference run: [performance-1f5472ad5a3f](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-1f5472ad5a3f)
   - sequences: `investor_neck_tilt_v7`, `investor_neck_pitch_v7`
   - result: both segments `live_applied`
   - observed min margins with the final protective preset:
     - `neck tilt`: `14.92%`
     - `neck pitch`: `8.92%`
   - practical note: the generic investor preset was still too aggressive for neck pitch. V7 now uses its own neck-specific protective preset

## Practical Lessons From V3-V7

These are the main implementation lessons another branch should reuse instead of rediscovering:

1. Atomic family demos work better than chatty expressive shows
   - The real head was materially more reliable when one family was exercised through one compiled `body_range_demo` animation under one live body transaction.
   - This is the same basic reason the standalone servo showcase was more reliable than the earlier investor shows.

2. Neutral first is mandatory
   - The head should be driven to a real neutral pose before every live show.
   - If the head starts from an unknown pose, later directional steps are harder to interpret and can leave the operator unsure whether the command or the hardware failed.

3. The default short live arm lease is not enough for slow family demos
   - The `300s` lease is now the maintained choice for V3-V7.
   - The old short lease was sufficient for quick commands but caused multi-segment demos to expire before the later cues.

4. Family-specific backoff matters more than one global preset
   - Eyes, lids, brows, and neck do not all tolerate the same envelope in practice.
   - The final working series uses:
     - full showcase-style proof for V3 and V4
     - investor backoff for V5 lids and V6 brows
     - a neck-specific protective preset for V7

5. The neck pair needs special handling
   - Neck tilt and pitch should be evaluated separately.
   - Neck pitch is still the most sensitive family even after backoff.
   - Do not assume the neck can use the same envelope as lids or brows.

6. Serial-port ownership still matters
   - Only one live serial tool should own `/dev/cu.*` at a time.
   - Doctor, Servo Lab, cue-smoke, and performance-show runs must not overlap.

7. Health warnings and operational success are different questions
   - The V3-V7 reference runs still report degraded live health.
   - That does not mean the demos failed.
   - The right branch-handoff truth is:
     - focused family demos are now operational and verified
     - the physical head still reports electrical-health warnings during many live runs

## Verified Expressive Motif Runtime (V8)

As of 2026-04-11, the branch also has a maintained expressive proof lane beyond the family demos:

- show: `investor_expressive_motion_v8`
- reference full run: [performance-0d7a47c35d4f](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-0d7a47c35d4f)
- canonical run record: [docs/investor_expressive_motion_v8_run_2026-04-11.md](/Users/sonics/project/Blink-AI/docs/investor_expressive_motion_v8_run_2026-04-11.md)

What changed architecturally:

- V8 no longer depends on the old flat staged-accent model
- V8 now uses one atomic `body_expressive_motif` cue per segment
- the runtime keeps structural and expressive state separately
- expressive groups can persist, then release in sequence, before structural return begins

What was proven on hardware:

- the guarded-close motifs now work in the exact structural-first order that was previously blocked
- clean live references:
  - [performance-ff4b6d13bde8](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-ff4b6d13bde8) for `guarded_close_right`
  - [performance-d92191a96cd3](/Users/sonics/project/Blink-AI/runtime/performance_runs/performance-d92191a96cd3) for `guarded_close_left`
- these runs prove:
  - head turns first
  - both eyes can close and stay closed
  - brows can frown while eyes remain closed
  - brows can return to neutral while eyes remain closed
  - lids can reopen after that
  - head can return only after the expressive groups are neutral

Current maintained V8 operating pattern:

- slower kinetics than V3-V7: `speed=90`, `acceleration=24`
- 12 motif cues
- explicit neutral confirm at the end of every cue
- conservative head and neck motion, stronger eye-area expression

Current practical interpretation:

- the architecture for real sequential expression is now proven
- the remaining limits are no longer sequencing or transport limits
- the remaining limits are eye-area family margins inside specific motifs

Observed current V8 truth:

- full V8 run completes `live_applied` and stays `preview_only=false`
- two guarded-close motifs are currently clean
- the rest of the motifs are still margin-degraded, mostly on:
  - `lower_lids`
  - `upper_lids`
  - `eye_yaw`
  - `eye_pitch`
  - `brows`
- current full-run floors:
  - `lower_lids: 0.25%`
  - `upper_lids: 0.43%`
  - `eye_yaw: 1.5%`
  - `eye_pitch: 2.2%`
  - `brows: 3.0%`
  - `head_yaw: 10.0%`
  - `head_pitch_pair: 33.67%`

This means another branch should treat V8 as:

1. a successful runtime architecture for expressive sequencing
2. a motif-by-motif eye-area tuning problem, not a structural-motion problem

## Health And Telemetry Reads

Bench-health polling currently reads:

- position
- speed
- load
- voltage
- temperature
- moving
- torque state
- current when available
- packet error bits

`ServoHealthRecord` and related audits also carry:

- `voltage_raw`
- `voltage_volts`
- `power_health_classification`
- error bits like `input_voltage`

Voltage scaling currently used by the code:

- `voltage_volts = voltage_raw * 0.1`

That scaling is implemented in:

- [src/embodied_stack/body/serial/health.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/health.py)

## Current Stable Facts

These points are safe to share as current branch truth:

- the maintained hardware host path is Mac live serial
- the maintained baud is `1000000`
- the current head has 11 active servo-backed joints
- raw servo control stays inside the body layer; planner-facing interfaces remain semantic
- the branch already supports:
  - serial doctor
  - live arm/disarm
  - motion-config audit
  - power preflight
  - usable-range audit
  - standalone servo showcase
  - Mac Servo Lab raw-joint operations
  - focused live family demos V3-V7
- speed and acceleration are real body-layer transport settings on the Mac path
- the checked-in numeric live truth lives in `runtime/calibrations/robot_head_live_v1.json` plus the mirrored human-facing limits doc
- all critical joint families now have a verified focused live proof lane:
  - head yaw
  - eye yaw and eye pitch
  - lids and blink
  - brows
  - neck tilt and neck pitch

## Current Known Problems And Caveats

The focused V3-V7 demos are now working, but another branch should still understand the remaining caveats.

Observed failure modes during the broader bring-up process included:

- `checksum_mismatch`
- `frame_too_short:4`
- `serial_timeout`
- bus-wide `input_voltage` error bits
- intermittent loss of responsive servo IDs
- runs where live writes appear to execute physically while post-write readback becomes noisy or partially corrupt

Current practical interpretation:

- the software communication model is stable enough to share
- the focused hardware-proof workflow is stable enough to share
- the broad expressive investor-show path remains more fragile than the atomic family demos
- the expressive-motif V8 lane is now real and reusable, but it is still more fragile than the focused family demos because multiple eye-area families can stack inside one motif
- the physical head can still report degraded electrical-health conditions even when the focused family demos complete successfully

In other words, there is a difference between:

1. the maintained architecture and proven focused-demo path, which are real and reusable
2. the still-imperfect live health condition of the current physical head

## Current Software Mitigations

This branch already contains some important hardening that another branch should preserve:

- successful live writes are no longer discarded just because a later readback poll is noisy
- live transport confirmation retries transient timeout and invalid-reply conditions
- performance-show normalization keeps executed live writes marked as `live_applied` even if later confirmation becomes degraded
- pre-show neutral write is now part of the performance-show path
- the focused family demos use explicit atomic range-demo sequences instead of narration-timed micro-beats
- the expressive V8 lane now uses a stateful motif runtime instead of flat staged accents, so held eye closure, staged brow release, and delayed structural return are all first-class compiled behaviors
- V5, V6, and V7 now use safer family-specific presets rather than one uniform aggressive envelope

These mitigations live primarily in:

- [src/embodied_stack/body/serial/driver.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/driver.py)
- [src/embodied_stack/body/serial/bench.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/bench.py)
- [src/embodied_stack/demo/performance_show.py](/Users/sonics/project/Blink-AI/src/embodied_stack/demo/performance_show.py)

## Recommended Handoff Reading Order

If another branch only has time to read a few files, start here:

1. [docs/robot_head_hardware_and_serial_handoff.md](/Users/sonics/project/Blink-AI/docs/robot_head_hardware_and_serial_handoff.md)
2. [docs/hardware_grounded_expression_architecture.md](/Users/sonics/project/Blink-AI/docs/hardware_grounded_expression_architecture.md)
3. [docs/investor_head_motion_v3_run_2026-04-11.md](/Users/sonics/project/Blink-AI/docs/investor_head_motion_v3_run_2026-04-11.md)
4. [docs/investor_expressive_motion_v8_run_2026-04-11.md](/Users/sonics/project/Blink-AI/docs/investor_expressive_motion_v8_run_2026-04-11.md)
5. [docs/serial_head_mac_runbook.md](/Users/sonics/project/Blink-AI/docs/serial_head_mac_runbook.md)
6. [docs/robot_head_live_limits.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_limits.md)
7. [docs/robot_head_live_revalidation_2026-04-10.md](/Users/sonics/project/Blink-AI/docs/robot_head_live_revalidation_2026-04-10.md)
8. [docs/protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)
9. [src/embodied_stack/body/grounded_catalog.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/grounded_catalog.py)
10. [src/embodied_stack/body/range_demo.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/range_demo.py)
11. [src/embodied_stack/body/expressive_motifs.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/expressive_motifs.py)
12. [src/embodied_stack/body/serial/protocol.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/protocol.py)
13. [src/embodied_stack/body/serial/transport.py](/Users/sonics/project/Blink-AI/src/embodied_stack/body/serial/transport.py)

## Short Branch-Handoff Summary

If you need to explain the current state in one paragraph:

Blink-AI currently drives a real 11-servo Feetech/ST robot head from the Mac over a maintained `live_serial` path at `1000000` baud, with semantics compiled in the body layer and sent over Feetech packet protocol using direct read/write, sync-read, and sync-write operations. The live calibration authority is `runtime/calibrations/robot_head_live_v1.json`, the checked-in human-facing numeric mirror is `docs/robot_head_live_limits.md`, and the maintained software source of truth for supported expression is the grounded catalog exported by `GET /api/operator/body/expression-catalog`. The most important operator workflows are `serial-doctor`, neutral write, `power-preflight`, Servo Lab, the standalone servo showcase, the focused V3-V7 family demos, and the newer V8 expressive-motif proof lane. V3-V7 remain the practical family-proof workflow for head yaw, eyes, lids, brows, and neck motion because they use one atomic animation per family, explicit neutral recovery, slow `100/32` kinetics, and safer family-specific envelopes. V8 now proves that real structural-first sequential expression is achievable on the hardware through a stateful motif runtime with held expressive state and staged release. The remaining V8 work is motif-by-motif eye-area tuning, not another architecture rewrite.
