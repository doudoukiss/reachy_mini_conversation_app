# Desktop Runtime and Optional Embodiment

This document turns the planning notes in:

- [01_target_refactor_plan.md](/Users/sonics/project/Blink-AI/docs/evolution/01_desktop_first_refactor/01_target_refactor_plan.md)
- [02_robot_head_hardware_profile.md](/Users/sonics/project/Blink-AI/docs/evolution/01_desktop_first_refactor/02_robot_head_hardware_profile.md)
- [03_repo_refactor_map.md](/Users/sonics/project/Blink-AI/docs/evolution/01_desktop_first_refactor/03_repo_refactor_map.md)
- [04_validation_and_acceptance.md](/Users/sonics/project/Blink-AI/docs/evolution/01_desktop_first_refactor/04_validation_and_acceptance.md)

into the maintained current-state runtime and optional embodiment guidance for the repository.

The authoritative product definition lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md). This document explains only the embodiment side of that product.

## Current center of gravity

Blink-AI is currently a desktop-hosted local-first companion with optional embodiment.

That means:

- the local Mac host is the active runtime for camera, microphone, speaker, memory, operator tooling, and most AI behavior
- the terminal-first `local-companion` path is the primary product surface
- the browser appliance and `/console` are secondary operator/control surfaces
- the `desktop/` package is the default local entrypoint
- the `body/` package owns semantic embodiment and future body transport boundaries
- the robot head, virtual body, and bench tooling are optional embodiment layers around the same companion core, not separate product identities
- the `edge/` package remains important, but as an optional tethered or future Jetson path rather than the required default loop
- `venue_demo` remains an explicit vertical mode rather than the default identity of the runtime
- the same `fast loop / slow loop` companion runtime should project through bodyless, avatar, virtual-body, and serial-head paths rather than splitting into different products
- the character runtime now emits one shared semantic intent that can be inspected in the terminal and operator console and then projected into avatar-shell state, virtual preview state, and optional serial-head motion

## Runtime modes

These runtime modes are the first-class current operating model:

- `desktop_bodyless`
  - local runtime with no body attached
  - best for dialogue, perception, and operator-tool development
- `desktop_virtual_body`
  - local runtime with semantic body actions rendered into virtual body state
  - default current development mode
- `desktop_serial_body`
  - local runtime with serial-body landing zone enabled
  - for later powered head bring-up
- `tethered_future`
  - future remote body transport, including a Jetson or another controller
- `degraded_safe_idle`
  - explicit safe fallback when the system cannot continue normal embodied behavior

Legacy edge-oriented modes remain in the contract surface for compatibility, but they are not the main development story anymore.
These modes change embodiment and transport, not the baseline companion identity.

## Character projection model

The maintained embodiment model is now:

- character runtime first
  - the fast loop and relationship runtime resolve one `CharacterSemanticIntent`
  - that intent carries semantic expression, attention, optional gesture or animation, warmth, curiosity, source signals, and a projected `BodyPose`
- projection profile second
  - `no_body`
  - `avatar_only`
  - `robot_head_only`
  - `avatar_and_robot_head`
- body transport last
  - the same intent can update the optional avatar shell, the virtual body preview, and the serial head
  - the serial head remains downstream of the same intent rather than running a separate behavior tree

Important constraint:

- the mind does not plan in servo space
- servo targets remain compiled from semantic intent inside `body/`
- if live serial is unconfirmed, unarmed, or missing a saved calibration, the projection falls back to preview-only and logs the block reason instead of pretending motion happened

## Demo profile model

The desktop runtime now treats interaction quality and embodiment mode as separate profile layers.

Model/media backend routing is now a third explicit layer underneath the interaction profile so the Mac runtime can switch between cloud and local execution honestly.

Interaction profiles:

- `cloud_demo`
  - provider-backed dialogue, voice scaffold, and multimodal perception when credentials exist
  - best for operator-led demos and venue-mode walkthroughs
  - falls back honestly when credentials are missing
- `local_companion`
  - default companion interaction profile on the Mac
  - native desktop-local conversation profile
  - defaults to `personal_local` context on the Mac unless a demo or site flow explicitly forces `venue_demo`
  - prefers Mac microphone, Mac speaker, native webcam capture, and no-servo bodyless or virtual-body startup
  - falls back honestly to limited camera awareness or typed input when local devices or permissions are unavailable
- `local_dev`
  - Ollama/browser/fixture-oriented development profile
  - keeps typed and deterministic fallback paths available
- `offline_stub`
  - fully local deterministic fallback with no cloud dependency

Embodiment profiles:

- `bodyless`
- `virtual_body`
- `serial_body`

The active operator-facing summary is the composition of both layers, for example:

- `local_dev + virtual_body`
- `offline_stub + bodyless`
- `cloud_demo + serial_body`

This is what the console and CLI now report as the active desktop demo profile.

Backend profiles:

- `cloud_best`
  - cloud-first text and vision with local media services and local embedding fallback
- `m4_pro_companion`
  - canonical Apple-Silicon local companion preset
  - prefers Ollama text, Ollama vision, Ollama embeddings, Apple Speech STT, and `say` TTS on the Mac
  - defaults to `qwen3.5:9b` for text and vision plus `embeddinggemma:300m` for embeddings
- `local_balanced`
  - primary M4 Pro profile with local Ollama text, optional local Ollama vision, local embeddings, and native Mac STT/TTS when available
- `local_fast`
  - lower-memory local profile that avoids a resident local vision model and prefers cheap retrieval fallback
- `offline_safe`
  - deterministic no-provider profile with honest degraded media and retrieval behavior

## Package ownership

### `desktop/`

Owns:

- default local app entrypoint
- local embodiment runtime wiring
- desktop runtime profiles
- in-process embodiment gateway behavior

### `brain/`

Owns:

- cognition
- memory
- dialogue
- world model
- perception-driven orchestration
- traces, reports, and operator-facing reasoning visibility

### `body/`

Owns:

- semantic embodiment commands
- normalized body-state and capability models
- head-profile loading
- expression and gesture compilation
- virtual-body behavior and preview state
- future serial or tethered transport boundaries

### `edge/`

Owns:

- optional remote command application
- safety-focused deterministic execution
- heartbeat
- acknowledgements
- remote adapter and monitor boundaries

## Body semantics boundary

The brain must not know about raw servo IDs or vendor-specific register details.

The maintained semantic contract is:

- `set_expression`
- `set_gaze`
- `perform_gesture`
- `perform_animation`
- `safe_idle`

The maintained Stage 4 canonical semantic names inside those commands are:

- expression
  - `neutral`
  - `friendly`
  - `thinking`
  - `concerned`
  - `confused`
  - `listen_attentively`
  - `safe_idle`
- gaze
  - `look_at_user`
  - `look_forward`
  - `look_left`
  - `look_right`
  - `look_up`
  - `look_down_briefly`
- gesture
  - `blink_soft`
  - `nod_small`
  - `tilt_curious`
  - `wink_left`
  - `wink_right`
- animation and safety
  - `micro_blink_loop`
  - `speak_listen_transition`
  - `scan_softly`
  - `recover_neutral`

Compatibility aliases remain accepted at the body boundary for one stable iteration, but planner-facing code should emit the canonical names.

Stage D also adds a hardware-specific semantic tuning layer and teacher-review artifact path under `runtime/body/semantic_tuning/` so expressive corrections remain outside the planner and outside the raw-servo profile.

The maintained typed body models now also include:

- `ExpressionRequest`
- `GazeRequest`
- `GestureRequest`
- `AnimationRequest`
- `AnimationTimeline`
- `CompiledAnimation`
- `VirtualBodyPreview`
- `JointCalibrationRecord`
- `HeadCalibrationRecord`
- `ServoHealthRecord`
- `BodyCommandOutcomeRecord`
- `BodyCommandAuditRecord`
- `SemanticTuningRecord`
- `CharacterSemanticIntent`
- `CharacterProjectionStatus`

Older commands like `set_head_pose`, `speak`, `display_text`, and `stop` are still supported for compatibility, but new embodiment behavior should prefer the semantic body surface.

## Robot head assumptions

The current robot body should be treated as an expressive bust/head, not as a mobile robot.

Software assumptions:

- emphasize gaze, blink, expression, listening, and attention cues
- do not imply locomotion or manipulation
- preserve a meaningful experience when there is no powered body attached

The current head profile in the repo is:

- `src/embodied_stack/body/profiles/robot_head_v1.json`

That profile is the landing zone for:

- servo limits
- neutral values
- semantic direction
- joint coupling
- safe ranges for the expressive head
- pending bench-confirmation notes for baud rate, neutral alignment, and mirrored mechanics

The current bench-confirmed live calibration path is:

- `runtime/calibrations/robot_head_live_v1.json`

The current known-good Mac bench link is:

- transport: `live_serial`
- baud: `1000000`
- validated adapter path: `/dev/cu.usbmodem5B790314811`

The planning and hardware profile docs remain the source of truth for why those assumptions exist. This document is the maintained summary of how they affect day-to-day repository work.

## Configuration surface

The desktop-first runtime should stay boring and explicit.

Current important config variables:

- `BLINK_APPLIANCE_MODE`
- `BLINK_APPLIANCE_PROFILE_FILE`
- `BLINK_RUNTIME_MODE`
- `BLINK_MODEL_PROFILE`
- `BLINK_BACKEND_PROFILE`
- `BLINK_VOICE_PROFILE`
- `BLINK_CAMERA_SOURCE`
- `BLINK_CAMERA_DEVICE`
- `BLINK_MIC_DEVICE`
- `BLINK_SPEAKER_DEVICE`
- `BLINK_DEVICE_PRESET`
- `BLINK_NATIVE_CAPTURE_SECONDS`
- `BLINK_NATIVE_TRANSCRIPTION_LOCALE`
- `BLINK_ALWAYS_ON_ENABLED`
- `BLINK_CONTEXT_MODE`
- `BLINK_LOCAL_MODEL_PREWARM`
- `BLINK_OBSERVER_INTERVAL_SECONDS`
- `BLINK_SCENE_CHANGE_THRESHOLD`
- `BLINK_SEMANTIC_REFRESH_MIN_INTERVAL_SECONDS`
- `BLINK_VOICE_ARM_TIMEOUT_SECONDS`
- `OLLAMA_KEEP_ALIVE`
- `OLLAMA_TEXT_TIMEOUT_SECONDS`
- `OLLAMA_TEXT_COLD_START_TIMEOUT_SECONDS`
- `OLLAMA_VISION_TIMEOUT_SECONDS`
- `OLLAMA_EMBED_TIMEOUT_SECONDS`
- `BLINK_BODY_DRIVER`
- `BLINK_SERIAL_PORT`
- `BLINK_SERIAL_TRANSPORT`
- `BLINK_SERIAL_FIXTURE`
- `BLINK_SERIAL_TIMEOUT_SECONDS`
- `BLINK_SERVO_BAUD`
- `BLINK_SERVO_AUTOSCAN`
- `BLINK_HEAD_PROFILE`
- `BLINK_HEAD_CALIBRATION`

The defaults should continue to favor local desktop operation over tethered assumptions.

For `whisper.cpp`, `WHISPER_CPP_MODEL_PATH` remains the highest-priority override, but the desktop-local runtime now also auto-discovers common local model caches such as `~/.cache/berserker/whisper-cpp/`, `~/.cache/whisper.cpp/`, and Homebrew share directories when the env var is unset.

## Current implementation status

Implemented now:

- desktop runtime package and entrypoint
- first-class native desktop runtime manager
- explicit desktop device boundaries for microphone input, speaker output, and webcam capture
- browser/operator appliance launcher through `uv run blink-appliance`
- persisted appliance setup profile under `runtime/appliance_profile.json`
- localhost bootstrap auth flow for the browser appliance path
- setup/status browser flow before `/console` when appliance setup is incomplete
- polished local companion command through `uv run local-companion`
- local machine doctor harness through `uv run local-companion-doctor`
- always-on local companion supervisor that owns observer polling, turn state, proactive eligibility, cooldowns, and bounded trigger evaluation
- native local conversation loop command through `uv run desktop-local-loop`
- maintained local companion story through `uv run local-companion-story`
- focused local companion eval suite through `uv run local-companion-checks`
- deterministic always-on regression suite through `uv run always-on-local-checks`
- body semantics package
- virtual-body path
- robot-head JSON/YAML profile loading
- semantic registry with canonical semantic names plus compatibility aliases at the body boundary
- expanded Lane 1 semantic vocabulary for attentiveness, listening vs thinking states, blink styles, nod/tilt variants, micro reorientation, and `safe_idle`
- semantic head/eye/lid/brow pose compilation for the uploaded 11-servo head
- canonical animation timelines for `look_down_briefly`, `nod_small`, `tilt_curious`, `scan_softly`, `boot_sequence`, `idle_breathing_head`, `micro_blink_loop`, `speak_listen_transition`, and `recover_neutral`
- operator-visible virtual preview state with canonical semantic name, alias source, gaze summary, transition profile, safe-idle compatibility, clamp notes, and coupling notes
- Feetech/ST packet encode/decode for ping, read, write, sync write, sync read, recovery, and reset
- serial transport modes for `dry_run`, `fixture_replay`, and `live_serial`
- higher-level Feetech driver bridge for sync writes, torque sequencing, health polling, safe speed ceilings, and last-command outcomes
- serial-body driver safety gates, torque-off safe idle, neutral recovery, stable transport reason codes, and readback support
- `blink_head_calibration/v2` calibration records with v1 read compatibility
- calibration and bring-up CLI for scan, ping, read-position, write-neutral, dump-profile-calibration, capture-neutral, set-range, validate-coupling, save-calibration, and health
- Stage E bench-suite runner and make-target workflow for Mac hardware validation
- live hardware pytest gates for `live_serial` and `live_serial_motion`
- action-based semantic smoke, semantic library inspection, teacher review, and runtime/operator serial-body controls
- in-repo live observation workflow for direct probes, sync groups, and semantic actions with final neutral tolerance checks
- explicit live-write gating on `body-calibration` for powered `write-neutral` and live `capture-neutral`, while dry-run and fixture-replay remain the maintained pre-power paths
- runtime-mode aware config and operator visibility
- composed desktop demo-profile reporting for operator tools and CLI
- operator snapshot visibility for microphone, speaker, and camera device health
- operator snapshot visibility for appliance setup state, config source, auth mode, device preset, and speaker-routing support
- operator and CLI visibility for always-on supervisor state, voice-loop state, scene-observer state, trigger-engine state, and Ollama warm/cold runtime details
- operator and CLI visibility for model profile, active skill, perception freshness, memory status, body mode, and fallback state
- operator and CLI visibility for body calibration status, live-motion enable state, last body command outcome, per-joint feedback, and per-servo health
- one-click browser story runner and one-command CLI story runner for the default desktop investor walkthrough
- automatic local session episode export with runtime snapshot, voice-loop, scene-observer, trigger-history, and Ollama-runtime artifacts for companion sessions
- persisted image-frame storage for local and browser snapshot inputs under `runtime/perception_frames/`, including `latest_camera_snapshot.<ext>` for direct inspection
- shared semantic body commands
- tests for config parsing, desktop runtime behavior, body compilation safety/coupling, protocol fixtures, transport replay, and serial failure handling

Still intentionally deferred:

- production-grade remote body transport beyond the current tethered compatibility path
- broader multi-day hardware endurance characterization beyond the current Stage E bench and observation workflows
- any planner-facing raw-servo or non-semantic motion surface

## Local companion and browser/operator behavior

`uv run local-companion` is the primary daily-use product path on the MacBook.

`uv run blink-appliance` is the primary browser/operator control path around that same runtime.

The appliance launcher:

- starts the existing one-process desktop runtime on `127.0.0.1`
- repairs the runtime layout before startup and persists setup state in `runtime/appliance_profile.json`
- opens `/console` directly on localhost with no token prompt
- shows `/setup` before `/console` until the appliance profile is saved
- keeps typed fallback available even when microphone or camera health is degraded

Optional embodiment remains important here because the same loop can stay bodyless, drive the virtual body, or project into the serial head through shared semantic actions and bench tooling. That embodiment layer strengthens the product without being required for Blink-AI to be useful.

The current loop is:

- a single always-on supervisor owns low-rate scene observation, proactive eligibility, shift/autonomy integration, and voice-loop state
- `blink-appliance` is the browser/operator path, while `local-companion` starts a terminal-first local host process and keeps the browser console as an explicit secondary surface
- the shared runtime exposes `/console` when `--open-console` is requested or when terminal stdin is not healthy
- `local-companion` also exposes `/console` as an in-loop opt-in command so the operator surface stays available without becoming the default startup mode
- terminal controls run through a main-thread `prompt_toolkit` session and degrade cleanly to browser-console-only if stdin is not healthy
- `local-companion` defaults to `personal_local` context, while story, scene replay, and demo flows force `venue_demo`
- camera observation stays active in the background when a local camera is enabled
- push-to-talk remains the default through explicit `/listen`
- explicit open-mic is available through `uv run local-companion --audio-mode open_mic` or `/open-mic on`
- plain text or `/type <text>` remains the honest fallback when speech capture is unavailable or inconvenient
- `/help` is the built-in terminal command map for the maintained daily-use loop
- blank `Enter` is intentionally a no-op in `local-companion` so terminal control-sequence noise does not accidentally start voice capture
- `/interrupt` stops current speech immediately and records the interruption in runtime status
- `/status` shows the current model profile, active skill, perception freshness, memory status, device health, body mode, fallback state, audio mode, voice-loop state, scene-cache age, reminder count, scene-observer state, trigger decision, and backend warm/cold details
- `/status` also exposes the active context mode plus per-backend Ollama failure metadata such as last failure reason, last failure time, last timeout used, and whether a cold-start retry was consumed

The doctor harness exists for machine-specific validation:

- `uv run blink-appliance --doctor`
- `uv run local-companion-doctor`
- `uv run local-companion-token`
- probes hardware and local binaries on the Mac
- checks Ollama reachability and installed models
- checks the discovered Whisper binary and model path
- runs a raw Whisper smoke
- runs status plus a typed local-turn probe through Blink-AI
- writes `runtime/diagnostics/local_mbp_config_report.md`

The current voice-loop states are:

- `idle`
- `armed`
- `vad_waiting`
- `capturing`
- `endpointing`
- `transcribing`
- `thinking`
- `speaking`
- `barge_in`
- `interrupted`
- `cooldown`
- `degraded_typed`

The current observer and trigger behavior is intentionally bounded:

- cheap scene watching uses low-rate camera polling with frame-difference as the required baseline
- MediaPipe face detection and attention hints are optional when installed
- heavy semantic vision is only refreshed when scene change is meaningful, a visual question was asked, fresh semantic facts are missing or stale, or proactive speech needs true grounded context
- proactive speech is never justified from `native_camera_snapshot` alone; it requires a fresh semantic provider such as `ollama_vision` or another true multimodal analyzer

## Validation expectation

When changing runtime, body, or contract behavior, the baseline checks remain:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

If a change materially affects the demo surface, also verify the relevant demo or tethered path rather than assuming the desktop runtime covers everything.

## Current local companion story

The default polished local product walkthrough is:

- `natural_discussion`
- `observe_and_comment`
- `companion_memory_follow_up`
- `knowledge_grounded_help`
- `safe_degraded_behavior`

In the browser console this is exposed through `Reset + Run Local Companion Story`.

From the terminal:

```bash
uv run local-companion
uv run local-companion-story
uv run local-companion-checks
uv run continuous-local-checks
```

## Current desktop demo story

The default replayable desktop-first story is:

- `greeting_presence`
- `attentive_listening`
- `wayfinding_usefulness`
- `memory_followup`
- `safe_fallback_failure`

In the browser console this is exposed through `Reset + Run Desktop Story`.

From the terminal:

```bash
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli reset
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli story --story-name desktop_story
```
