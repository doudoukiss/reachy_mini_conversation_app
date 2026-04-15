# Repo Refactor Map

This file translated the desktop-first plan into a concrete repository shape.

## Keep these existing areas

Keep and evolve:
- `src/embodied_stack/brain/`
- `src/embodied_stack/shared/`
- `tests/`
- `docs/`

Do **not** throw away the current brain logic, memory, or traces.

## Reframe `edge/`

The current `edge/` directory should stop being the mandatory development center.

Recommended future meaning of `edge/`:
- optional tether / remote body transport
- future Jetson bridge
- future robot-side runtime if needed

For the current phase, **do not force the desktop app through the old edge assumptions**.

## Added top-level packages

```text
src/embodied_stack/
  desktop/
  multimodal/
  voice/
  body/
```

### `desktop/`
Purpose:
- local desktop runner
- webcam / mic / speaker glue
- body adapter wiring
- app-level runtime profiles

Current modules:
- `desktop/app.py`
- `desktop/runtime.py`
- `desktop/profiles.py`
- `desktop/cli.py`

### `multimodal/`
Purpose:
- webcam capture
- image/frame ingestion
- event extraction
- scene summaries
- presence / attention signals

Current modules:
- `multimodal/camera.py`
- `multimodal/perception.py`
- `multimodal/events.py`

### `voice/`
Purpose:
- STT/TTS abstraction
- typed-input fallback
- push-to-talk / streaming loop
- transcript events

Current modules:
- `voice/stt.py`
- `voice/tts.py`
- `voice/pipeline.py`

### `body/`
Purpose:
- semantic embodiment
- robot profile
- virtual body
- Feetech protocol
- serial transport
- calibration tools

Current modules:
- `body/models.py`
- `body/profile.py`
- `body/compiler.py`
- `body/driver.py`
- `body/profiles/robot_head_v1.json`

## Shared contract changes

The current shared models are a good start but should be extended.

### Keep
- sessions
- traces
- world state
- telemetry
- acknowledgements

### Added / refactored
- semantic embodied actions
- body pose models
- driver capability profile
- runtime profile metadata
- perception event schemas

## Recommended command model refactor

Instead of letting high-level code emit raw `set_head_pose` only, add semantic command types such as:

- `set_expression`
- `set_gaze`
- `perform_gesture`
- `perform_animation`
- `safe_idle`

You may keep `speak`, `display_text`, and `stop`.

If backwards compatibility matters, keep the old commands for now and adapt them internally.

## Configuration refactor

Add explicit configuration for:

- runtime mode
- model provider profile
- voice profile
- camera source
- body driver mode
- serial port
- servo bus baud rate
- robot head profile path
- dry-run vs live transport

Example environment variables:

```bash
BLINK_RUNTIME_MODE=desktop_virtual_body
BLINK_MODEL_PROFILE=cloud_demo
BLINK_VOICE_PROFILE=desktop_local
BLINK_CAMERA_SOURCE=0
BLINK_BODY_DRIVER=virtual
BLINK_HEAD_PROFILE=profiles/robot_head_v1.yaml
BLINK_SERIAL_PORT=/dev/tty.usbserial-xxxx
BLINK_SERVO_BAUD=115200
BLINK_SERVO_AUTOSCAN=1
```

## What to de-emphasize right now

- `MOVE_BASE`
- any navigation assumptions
- any community demo that depends on locomotion
- any architecture that assumes on-robot camera/microphone as the default

## What to emphasize right now

- voice interaction
- webcam perception
- semantic gaze and expression
- social presence
- demo replay
- provider flexibility
- virtual-body preview
- hardware-safe bring-up tools

## Migration sequence status

### Step 1
Completed. `desktop/` and `body/` were added without deleting current modules.

### Step 2
Completed. The desktop runtime now calls into the current brain orchestrator.

### Step 3
Completed. Embodiment-specific logic now lives behind `body/`.

### Step 4
Completed. Virtual body is the default driver.

### Step 5
Completed as a landing zone. The serial-body path now has Feetech/ST packet handling, dry-run and fixture replay transports, a live serial transport abstraction, safety gating, and calibration tooling behind the same `BodyDriver` interface. Powered bench verification is still future work.

### Step 6
Completed at the configuration/runtime level. Desktop and tethered profiles exist; demo docs and checks now describe both.

## Testing strategy

Add tests in four layers.

### Unit tests
- protocol frame encode/decode
- servo clamping
- semantic pose compilation
- coupling rules
- runtime config parsing

### Integration tests
- desktop runtime with typed input
- bodyless mode
- virtual-body mode
- provider fallback behavior

### Fixture tests
- camera/perception fixture replay
- investor scenario replay
- expression timeline replay

### Hardware-safe tests
- serial dry-run
- packet capture / playback
- “no serial device available” fallback

## Done means

The refactor is successful when:
- Blink-AI can run as a local desktop app
- the brain never needs to know raw servo IDs
- the virtual body is useful before hardware power is fixed
- the physical head can later be activated by changing only the body driver configuration
