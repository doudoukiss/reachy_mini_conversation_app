# Target Refactor Plan

## Why Blink-AI was refactored this way

The current repo is organized around a software-first **Mac brain + Jetson edge** split. That was a good pre-hardware architecture, but the current physical reality is different:

- the robot body is only partially available
- the body is primarily an **expressive head / bust**, not a general mobile robot
- the robot currently lacks reliable power for the servo board
- the computer can already provide camera, microphone, speaker, display, storage, and the main AI runtime

Because of that, the refactor centered on **making the desktop runtime the real embodied product** instead of waiting on the body.

## Current product framing

Blink-AI is currently a:

> **Desktop-first embodied social robot runtime with an optional expressive body adapter**

That means the product already has embodiment through:

- live speech interaction
- gaze / attention logic
- webcam-based perception
- memory and social continuity
- visible state and operator tooling
- expression planning, even when not yet physically actuated

## What changed conceptually

### Old center of gravity
- `brain/` = high-level intelligence
- `edge/` = robot-side runtime
- fake robot used while hardware is absent

### New center of gravity
- `brain/` = high-level intelligence, memory, tool use, orchestration
- `desktop/` = first-class local runtime for webcam + mic + speaker + body adapter
- `body/` = semantic embodiment and optional servo transport
- `edge/` = future optional tether / Jetson bridge, no longer the default dev loop

## First-class runtime modes

Blink-AI now explicitly supports these modes:

1. `desktop_bodyless`
   - webcam, mic, speaker, local UI
   - no body attached
   - useful for dialogue and perception development

2. `desktop_virtual_body`
   - same as above
   - body actions go to a virtual expressive head / telemetry renderer
   - main mode for current development

3. `desktop_serial_body`
   - same as above
   - body actions go to Feetech/ST serial transport when power/control are ready

4. `tethered_future`
   - same semantic brain/body contracts
   - body transport can later move behind a Jetson or another controller

5. `degraded_safe_idle`
   - any voice/perception/body failure falls back here safely

## Architectural principle

The important split is no longer “Mac vs Jetson.”

The important split is now:

- **cognition and dialogue**
- **multimodal sensing**
- **semantic embodiment**
- **body transport**

That split works with:
- no hardware
- virtual hardware
- direct serial body control from the Mac
- future tethered body control through Jetson

## High-level target architecture

```text
[ User in front of laptop / robot ]
                |
                v
+-------------------------------------------------------------+
|                 DESKTOP EMBODIMENT RUNTIME                  |
|-------------------------------------------------------------|
| Webcam | Microphone | Speakers | Operator UI | Session UX   |
+-------------------------------------------------------------+
                |
                v
+-------------------------------------------------------------+
|                       BLINK-AI BRAIN                        |
|-------------------------------------------------------------|
| dialogue | memory | world model | knowledge | planning      |
+-------------------------------------------------------------+
                |
                v
+-------------------------------------------------------------+
|                SEMANTIC BODY / EXPRESSION LAYER             |
|-------------------------------------------------------------|
| gaze | blink | expression | head pose | animation timeline  |
+-------------------------------------------------------------+
                |
         +------+------+
         |             |
         v             v
+----------------+  +----------------------+
| Virtual body   |  | Feetech serial body  |
| preview/tele.  |  | later when powered   |
+----------------+  +----------------------+
```

## Brain outputs

The current repo preserves simple commands such as:
- `speak`
- `display_text`
- `set_led`
- `set_head_pose`
- `stop`

That is a good start, but for this new body the brain should emit **semantic embodied actions**, not device-specific primitives.

It now also supports semantic action families such as:

- `speak`
- `set_expression`
- `set_gaze`
- `perform_gesture`
- `perform_animation`
- `safe_idle`

The body layer should compile those into:
- neck yaw / pitch / roll
- eyelid positions
- eye pitch / yaw
- eyebrow motion
- coordinated blink / wink / listening / thinking / surprised patterns

## What not to do

Do **not**:
- hard-code servo IDs in the brain
- let dialogue code directly choose raw servo values
- bind the app too tightly to Jetson for this phase
- block progress on power or serial bring-up
- pretend the robot has mobility or manipulation it does not have

## Refactor milestones

### Milestone A — Desktop Embodiment Mode
Completed. The local computer is now the first-class runtime.

### Milestone B — Body Semantics
Completed. The semantic embodiment layer and virtual-body path now exist.

### Milestone C — Feetech Driver Path
Partially complete. The serial-body landing zone and head profile are present, but real powered-body bring-up is still deferred.

### Milestone D — Demo Profiles and Evals
Partially complete. Desktop-local and tethered profiles exist, with tests for runtime modes and config parsing. Broader serial-body eval depth is still future work.

## What success looks like

After the refactor, you should be able to:

- run Blink-AI as a local desktop program
- talk to it directly using the Mac’s mic/speaker
- use the Mac’s webcam for perception
- see embodied actions rendered through a virtual body even with no servo power
- later connect the physical head by swapping only the body transport layer
