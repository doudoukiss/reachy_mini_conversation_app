# Robot Head Hardware Profile

This file captures the robot-body assumptions the software should use.

## Mechanical product shape

From the uploaded photos, the robot is best treated as an **expressive social bust/head** rather than a mobile robot or manipulator.

The visible motion system supports:
- neck yaw
- coupled head pitch / roll
- upper and lower eyelids
- eyeball vertical and horizontal gaze
- left and right eyebrows

This is ideal for:
- greeting
- eye contact
- attention cues
- listening behavior
- blink / wink
- expressive face animation
- subtle social presence

It is **not** currently a platform for:
- navigation
- arm manipulation
- locomotion-heavy demos

That should shape the software.

## Servo family and bus assumptions

The uploaded vendor documents show a Feetech STS/SMS-style protocol with:
- packet-based serial communication
- unique servo IDs on a shared bus
- low byte first for multi-byte values
- support for read/write, sync read, and sync write
- target position, speed, torque, and state registers
- torque on/off and feedback registers
- current position at address `0x38`
- target position at address `0x2A`
- running speed at address `0x2E`
- torque switch at address `0x28`

The tutorial also indicates:
- STS/SMS servos are configured on a shared serial bus
- each servo must have a unique ID before chaining
- an external power supply is required
- the URT-1 board is the expected signal-conversion/debug path for TTL servo control

## Important baud-rate note

The uploaded Feetech tutorial and protocol materials are not perfectly consistent in all places about default baud rates.

For safety, the software should:
- treat **115200** as the most likely STS default
- also support auto-scan / manual override for **1000000**
- make baud rate configurable in the profile and calibration tools

Do not hard-code a single assumption without bench verification.

## Body servo map from the uploaded robot note

The uploaded note states that the head uses **11 STS3032 servos** with:
- position range `0..4095`
- neutral at `2047`
- neutral meaning “looking forward with a normal expression”

### Recommended normalized software joints

| Semantic joint | Servo ID(s) | Neutral | Raw min | Raw max | Positive semantic direction |
|---|---:|---:|---:|---:|---|
| head_yaw | 1 | 2047 | 1647 | 2447 | look right |
| head_pitch_pair_a | 2 | 2047 | 1447 | 2647 | raw + contributes to head up |
| head_pitch_pair_b | 3 | 2047 | 1447 | 2647 | raw - contributes to head up |
| lower_lid_left | 4 | 2047 | 1947 | 2347 | close |
| upper_lid_left | 5 | 2047 | 1547 | 2247 | open |
| lower_lid_right | 6 | 2047 | 1747 | 2147 | open |
| upper_lid_right | 7 | 2047 | 1847 | 2547 | close |
| eye_pitch | 8 | 2047 | 1447 | 2447 | look up |
| eye_yaw | 9 | 2047 | 1747 | 2347 | look right |
| brow_left | 10 | 2047 | 1897 | 2197 | raise brow |
| brow_right | 11 | 2047 | 1897 | 2197 | lower brow raw+, raise brow raw- |

## Coupling rules from the uploaded note

These rules should be built into the software embodiment layer.

### Neck
- Servo 1 controls head yaw.
- Servos 2 and 3 together control head pitch.
- Increasing servo 2 while decreasing servo 3 by the same amount = head up.
- Decreasing servo 2 while increasing servo 3 by the same amount = head down.
- Increasing only servo 2 = right head tilt.
- Decreasing only servo 3 = left head tilt.

### Eyelids
- Left and right upper lids usually move together.
- Left and right lower lids usually move together.
- Because right-side and left-side mechanics are mirrored, raw directions are not identical.
- Therefore the software should expose semantic controls like:
  - `eyes_open`
  - `eyes_closed`
  - `blink`
  - `wink_left`
  - `wink_right`
- The compiler should map those semantics to raw servo directions.

### Eyes
- Servo 8 controls both eyes up/down together.
- Servo 9 controls both eyes left/right together.
- When the eyes move strongly up or down, the upper lids should follow by a matched amount.

### Eyebrows
- Brows usually move symmetrically.
- Wink is the main intentional asymmetric face expression that should be supported early.

## What the software should expose

The body layer should not expose raw servo IDs to the rest of the app.

It should expose semantic primitives like:

- `look_forward`
- `look_left`
- `look_right`
- `look_up`
- `look_down`
- `listen_pose`
- `thinking_pose`
- `blink`
- `wink_left`
- `wink_right`
- `soft_smile_equivalent` (through eyes/brows/head posture)
- `surprised`
- `sleepy`
- `curious`
- `affirm_nod`
- `head_tilt_left`
- `head_tilt_right`

## Recommended software representation

### 1. Robot profile
A YAML or JSON profile should hold:
- servo IDs
- min / neutral / max
- semantic direction
- coupled-joint formulas
- safe default speed / acceleration
- enabled / disabled state

### 2. Semantic pose
A normalized pose object should express:
- head_yaw in `[-1, 1]`
- head_pitch in `[-1, 1]`
- head_roll in `[-1, 1]`
- eye_yaw in `[-1, 1]`
- eye_pitch in `[-1, 1]`
- upper_lids_open in `[0, 1]`
- lower_lids_open in `[0, 1]`
- brow_raise_left in `[0, 1]`
- brow_raise_right in `[0, 1]`

### 3. Animation timeline
Embodied actions should compile to a short time-ordered sequence of servo frames rather than a single jump.

## Safety rules

The body layer must clamp all outputs to per-servo limits.

It should also support:
- dry-run mode
- virtual-body mode
- torque-off safe idle
- neutral pose reset
- “do not move” when serial/power transport is unavailable

## Calibration expectations

When power is available later, calibration should include:
- confirming IDs
- confirming baud rate
- confirming neutral values
- confirming mirrored lid/brow directions
- confirming pitch/roll formulas for servos 2 and 3
- recording safe motion speed/acceleration
