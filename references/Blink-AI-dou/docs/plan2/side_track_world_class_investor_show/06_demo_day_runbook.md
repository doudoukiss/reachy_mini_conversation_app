# Demo-Day Runbook

## Goal

Run the ten-minute investor show with:
- minimal manual work,
- zero hidden wizardry,
- local-first reliability,
- and a clear recovery path.

## Recommended demo profile

For the ten-minute scripted show, prefer a reliability-first stack:

- `desktop_serial_body`
- serial head connected through the current known-good live serial path
- local voice via `macos_say`
- silent proof scenes
- perception fixtures instead of live camera dependence
- operator console running on a side monitor
- projector on the clean performance page

After the scripted show ends, the team can switch back to the main live track for Q&A if desired.

## Recommended environment

Start from the existing known-good live serial assumptions unless the hardware path changes:

- port: `/dev/cu.usbmodem5B790314811`
- baud: `1000000`
- profile: `src/embodied_stack/body/profiles/robot_head_v1.json`
- calibration: `runtime/calibrations/robot_head_live_v1.json`

Recommended launch environment:

```bash
BLINK_RUNTIME_MODE=desktop_serial_body \
BLINK_BODY_DRIVER=serial \
BLINK_SERIAL_TRANSPORT=live_serial \
BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811 \
BLINK_SERVO_BAUD=1000000 \
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json \
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json \
BLINK_CHARACTER_PROJECTION_PROFILE=avatar_and_robot_head \
BLINK_TTS_BACKEND=macos_say \
BLINK_CONTEXT_MODE=venue_demo \
uv run blink-appliance
```

Once the configurable tuning path exists, add:

```bash
BLINK_BODY_SEMANTIC_TUNING_PATH=runtime/body/semantic_tuning/robot_head_investor_show_v1.json
```

## Preflight checklist

### 45 to 60 minutes before the meeting
- power the head
- connect serial
- verify speaker route
- open projector surface
- open operator console on side monitor
- confirm room lighting and robot sightline

### 30 minutes before the meeting
Run:

```bash
make serial-doctor
```

Then:

```bash
BLINK_CONFIRM_LIVE_WRITE=1 make serial-neutral
```

Then execute the minimal cue smoke:
- `friendly`
- `look_left`
- `look_right`
- `nod_small`

### 20 minutes before the meeting
- reset the demo runtime to a known state
- clear any stale session memory if the show requires a clean session
- open the performance page with the intended session id
- verify the projector is showing the correct surface

### 10 minutes before the meeting
- run a narration-only dry check
- verify caption copy
- verify volume level
- set the console to the correct session id
- verify there is no active degraded transport state

## Recommended operator roles

### Operator A — show runner
- starts the show
- advances recovery if something degrades
- watches the main rhythm

### Operator B — proof monitor
- watches `/console`
- confirms escalation, safe idle, and export behavior
- calls stop if the body path becomes unsafe

For a smaller team, one operator can do both, but two is cleaner.

## Recommended commands to add

Once Codex implements the performance mode, the ideal operator commands are:

```bash
uv run local-companion performance-catalog
uv run local-companion performance-dry-run investor_ten_minute_v1
uv run local-companion performance-show investor_ten_minute_v1
```

Optional Make targets:

```bash
make investor-show-dry
make investor-show
```

## During the show

### Main rule
Do not improvise over the top of the robot.

The point of this side-track is reliability and polish.

### If a segment degrades
Use the prepared fallback line and keep moving.

### If the head path degrades
Switch to preview-only and keep the show going.
Do not stop the entire performance unless the software stack itself is no longer coherent.

### If audio fails
Keep captions on screen and continue the proof flow.
The presence shell and body cues will still carry the segment.

## Fallback ladder

Use this exact order.

### Level 1 — proof still good, audio or body cosmetic issue
- keep the show running
- use captions
- continue with the prepared narration

### Level 2 — live body blocked or unsafe
- force preview-only
- keep the main screen alive
- continue the scripted show without live head motion

### Level 3 — individual proof cue fails
- use the segment's fallback line
- surface the actual verified output on screen
- proceed to the next chapter

### Level 4 — escalation or safe-idle proof path fails
- invoke the operator-safe simplified path directly
- keep the thesis the same

### Level 5 — runtime severely degraded
- stop the live body path
- hold safe idle if available
- continue only if the presence / performance surface is still coherent
- otherwise end cleanly rather than scrambling

## Post-show flow

As soon as the ten-minute show ends:

1. export the session artifact
2. capture the run path
3. keep the performance page on the artifact summary for a beat
4. transition to live Q&A only after the artifact path is visible

This makes the close feel real and disciplined.

## Recommended transition into Q&A

Use a simple bridge line from the operator or robot:

> That concludes the deterministic performance mode. We can now return to the live companion path for questions.

This keeps the audience aware that:
- the scripted show was deliberate
- the main product path is still the live companion

## Reset between investor meetings

After each meeting:

1. export artifacts
2. reset demo state
3. clear session-specific memory if the same show session id is reused
4. re-run neutral and two smoke-safe body cues
5. verify the head still looks symmetric and calm

## Dress rehearsal standard

Do not present publicly until the team can do all of the following three times in a row:

- complete the show within `9:30` to `10:30`
- complete without unsafe body intervention
- produce the end-of-run artifact summary
- handle at least one injected degraded step gracefully
