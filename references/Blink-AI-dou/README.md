# Blink-AI

Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.

The primary product is the AI presence living in the computer. Today that means the Mac-hosted `uv run local-companion` loop is the hero path, with `personal_local` as the default context and `companion_live` as the default daily-use profile. `uv run blink-appliance`, `/console`, and the Action Center remain secondary browser/operator surfaces around that same companion runtime.

Today the active runtime host is the local MacBook Pro. Camera, microphone, speaker, storage, operator tooling, memory, and most AI run on the computer. The robot body is optional embodiment that can be absent, virtualized, or connected later through a serial or tethered transport path.

The serial head, virtual body, and `venue_demo` concierge flows are explicit projections or modes of the same companion core rather than separate product identities. The Action Plane is the safe slow-loop capability substrate for digital side effects, not the product thesis.

The current repo already has a real terminal-first companion loop, a no-robot certification lane, a real Action Plane, and a real optional embodiment path. What is not complete yet is the full character presence runtime: the `fast loop / slow loop` split, explicit persona-manifest layer, and lightweight avatar shell remain the next major upgrade.

Current implementation checkpoints worth knowing:

- the no-robot certification lane is implemented: `uv run local-companion-certify`, `uv run local-companion-failure-drills`, `uv run local-companion-burn-in`, and readiness artifacts under `runtime/diagnostics/local_companion_certification/`
- the Stage 6 Action Plane baseline is implemented, including approvals, workflows, action bundles, replays, and the `/console` Action Center
- the Stage A through Stage E serial-head path is implemented and bench-validated on the real Mac-connected 11-servo Feetech/ST head, with a current known-good live setup of `live_serial` at `1000000` baud and a saved live calibration at `runtime/calibrations/robot_head_live_v1.json`

For the authoritative product definition, start with [docs/north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).
For the current direction and priority order, use [docs/current_direction.md](/Users/sonics/project/Blink-AI/docs/current_direction.md).
For the maintained product-layer summary, use [docs/product_direction.md](/Users/sonics/project/Blink-AI/docs/product_direction.md).
For a map of the maintained documentation set, use [docs/README.md](/Users/sonics/project/Blink-AI/docs/README.md).
For the fastest terminal-first daily-use walkthrough, use [docs/companion_quickstart.md](/Users/sonics/project/Blink-AI/docs/companion_quickstart.md).
For the 20 to 30 minute human acceptance walkthrough, use [docs/human_acceptance.md](/Users/sonics/project/Blink-AI/docs/human_acceptance.md).
For the maintained deterministic investor-show rehearsal and projector runbook, use [docs/investor_show_runbook.md](/Users/sonics/project/Blink-AI/docs/investor_show_runbook.md).
For the next major product layer, use [docs/character_presence_runtime.md](/Users/sonics/project/Blink-AI/docs/character_presence_runtime.md).
For bounded companion continuity, memory layers, and relationship-runtime rules, use [docs/relationship_runtime.md](/Users/sonics/project/Blink-AI/docs/relationship_runtime.md).
For contributor workflow and runtime debugging notes, use [docs/development_guide.md](/Users/sonics/project/Blink-AI/docs/development_guide.md).
For project evolution and historical plans, use [docs/evolution/README.md](/Users/sonics/project/Blink-AI/docs/evolution/README.md).
For a beginner-friendly walkthrough and append-only phase history, use [tutorial.md](/Users/sonics/project/Blink-AI/tutorial.md).

## Product thesis

- primary product: the local-first companion living on the Mac
- primary surface: terminal-first `uv run local-companion`
- next defining layer: the character presence runtime
- continuity layer: the relationship runtime
- slow-loop substrate: the Action Plane
- optional embodiment: bodyless, virtual body, or serial head
- explicit vertical/demo mode: `venue_demo` community concierge / guide deployments and investor demos

## Core architecture

```text
[ Person / operator / venue visitor ]
           |
           v
[ Desktop companion runtime + optional embodiment ]
  - webcam + mic + speaker
  - operator console + local UI
  - typed fallback + replay paths
  - runtime modes for bodyless / virtual / serial
           |
           v
[ Blink-AI brain ]
  - sessions + memory
  - dialogue + voice abstractions
  - multimodal perception
  - world model + traces
  - demo orchestration + reports
           |
           v
[ Body semantics + transport ]
  - expression / gaze / gesture / animation
  - virtual body preview
  - serial body landing zone
  - future tethered / Jetson bridge
```

## What is implemented

- first-class desktop runtime package and entrypoint for the local Mac development path
- first-class body package for semantic embodiment, head-profile loading, virtual-body preview, and serial-body landing zone
- FastAPI brain service with session, world-state, scenario replay, log, and trace endpoints
- voice turn endpoint with a stub voice path and an OpenAI-compatible scaffold that falls back cleanly
- persistent local memory store for sessions, optional user memory, and operator notes
- explicit companion relationship runtime for greeting/re-entry, unresolved-thread follow-up, day planning, observe-and-comment, and tone-bound handling
- pluggable dialogue engine interface with deterministic rule fallback plus provider-backed GRSai chat support
- explicit backend router for text reasoning, vision, embeddings, STT, and TTS across cloud and local profiles
- practical browser-based operator console served by the brain at `/console`
- local-first operator auth for the console and operator/demo control APIs
- explicit Agent OS runtime with runs, checkpoints, skill selection, subagent selection, typed tools, and inspectable traces
- Stage 6 Action Plane Stage A/B baseline plus Stage 6C bounded browser runtime, Stage 6D workflow runtime, Stage 6E action flywheel, and Stage 6F operator productization with typed action contracts, deterministic policy, approval lifecycle, replay support, idempotent execution records, connector health, connector runtime, reentrant workflow runs, runtime/operator snapshot visibility, unified Action Center UX, restart-review reconciliation, durable action bundles, and deterministic action replays
- structured multimodal perception layer with stub, manual-annotation, browser-snapshot, video-fixture replay, and optional multimodal-LLM modes
- embodied world-model tracking for participants, engagement, anchors, visible text, attention target, current speaker, and limited-awareness state
- deterministic participant/session router for likely-speaker routing, returning-visitor session resume, simple queueing, and crowd-mode reorientation
- deterministic social-interaction executive for greet suppression, clarification, interruption handling, shorter replies on disengagement, escalation, and safe-idle decisions
- deterministic shift supervisor for boot, ready/assist/follow-up flow, quiet-hours and closing behavior, bounded attract-mode prompts, degraded transport handling, and operator overrides
- pilot-ready operator handoff workflow with local incident tickets, assignee/note/resolution state, venue-aware staff suggestions, and auditable incident timelines
- venue-knowledge ingestion for pilot-site FAQs, schedules, rooms, staff contacts, markdown docs, and optional ICS calendars
- pilot-site operations packs for opening hours, quiet hours, closing windows, proactive greeting policy, announcement policy, escalation overrides, accessibility notes, and fallback instructions
- pilot-operations measurement layer with live shift metrics, pilot-shift report bundles, and a deterministic day-in-the-life simulator
- knowledge tools that combine imported venue data with live world-model and perception state
- local embedding-backed semantic retrieval for venue knowledge, operator notes, and user memory fallback
- semantic embodied action contract surface with `set_expression`, `set_gaze`, `perform_gesture`, `perform_animation`, and `safe_idle`
- fake robot edge runtime with driver boundary, telemetry log, heartbeat, safe idle, and unsupported-motion rejection retained for the future tethered path
- edge hardware-adapter landing zone with explicit actuator, input, and monitor boundaries plus Jetson-oriented driver profiles
- API-first demo orchestration with persisted report bundles, replayable seeded community scenarios, and explicit pass/fail metrics
- first-class native desktop runtime manager for local Mac conversation, webcam capture, device health, and honest fallback reporting
- native Mac microphone capture through AVFoundation + Apple Speech transcription, with typed and browser paths retained as fallback compatibility modes
- native Mac webcam snapshot capture for local perception submission, plus browser and fixture compatibility paths when live camera capture is unavailable
- local macOS `say` speech output path with explicit speaker health reporting in the operator snapshot
- replayable perception fixtures, structured scene events, latest-perception history APIs, and console visibility for confidence, provenance, and timestamps
- multimodal investor scenes with replay evidence, scorecards, world-model transitions, engagement timeline, and final-action inspection
- composed desktop runtime profiles that keep `companion_live` as the default daily companion path while preserving `m4_pro_companion`, `cloud_demo`, `local_dev`, and `offline_stub` for explicit alternates
- backend profiles that route media and model work explicitly across `companion_live`, `cloud_best`, `m4_pro_companion`, `local_balanced`, `local_fast`, and `offline_safe`
- one-command reset and story-running paths for the desktop-first investor demo flow
- visible operator reporting for active demo profile, provider state, body state, fallback events, and emitted embodied actions
- routed Action Plane execution for `write_memory`, `promote_memory`, `request_operator_help`, `log_incident`, `browser_task`, reminder tools, note tools, bounded local-file actions, and local calendar query/draft actions, while `body_command` remains on the existing embodiment path
- bounded browser execution for `browser_task` with `disabled`, `stub`, and `playwright` backends, per-session browser state, artifact capture under `runtime/actions/browser/`, and action-level approval for click, type, and submit steps
- code-defined Action Plane workflows for `capture_note_and_reminder`, `morning_briefing`, `event_lookup_and_open_page`, and `reminder_due_follow_up`, persisted under `runtime/actions/workflows/` and resumable across approvals and restart
- live Action Plane flywheel exports under `runtime/actions/exports/action_bundles/` and `runtime/actions/exports/action_replays/`, linked back into `blink_episode/v2` and `blink_research_bundle/v1`
- operator and CLI Action Plane inspection paths through `/api/operator/action-plane/*`, including the aggregated `/api/operator/action-plane/overview` Action Center surface, plus `connector-status`, `approval-list`, `approval-approve`, `approval-reject`, `action-history`, `replay-action`, `action-bundle-list`, `action-bundle-show`, `action-bundle-teacher-review`, `replay-action-bundle`, `workflow-list`, `workflow-runs`, `workflow-start`, `workflow-resume`, `workflow-retry`, and `workflow-pause`
- browser-console Action Center UX for approvals, blocked workflows, restart-review items, bundle inspection, deterministic replay, browser preview artifacts, and recent failures, with matching `/actions ...` commands inside `local-companion`
- schema-versioned episode export bundles that turn demo runs and live sessions into reusable multimodal data assets
- regression fixtures and a dedicated demo-check suite for greeting, attentive listening, wayfinding, events, memory follow-up, escalation, safe idle, virtual body behavior, camera fallback, bodyless conversation, serial fallback, and provider fallback
- a dedicated multimodal demo-check suite for approach, sign reading, social memory, disengagement, escalation, and honest limited-awareness fallback
- hardened HTTP brain↔edge gateway path with safe retries, duplicate-safe command application, degraded transport snapshots, and tethered smoke coverage
- readiness endpoints plus one-command tethered launch, status, and reset tooling for demo-day operation

## Quickstart

### 1. Sync the project environment with `uv`

```bash
brew install uv
uv sync --dev
```

`uv` manages the project environment for you, so there is no manual `venv` activation step in the normal workflow.

### 2. Run checkpoint validation

```bash
make validate
```

This runs the test suite plus the dry-run scenario path.

For milestone acceptance, use the maintained acceptance lanes:

```bash
make acceptance-quick
make acceptance-full
make acceptance-rc
```

- `acceptance-quick` is the fast high-yield lane for day-to-day regression checks.
- `acceptance-full` is the authoritative automated no-robot milestone lane.
- `acceptance-rc` is the stricter release-candidate lane.

Use [docs/acceptance.md](/Users/sonics/project/Blink-AI/docs/acceptance.md) for the full staged workflow, artifact locations, manual local-Mac checklist, and optional hardware lane.
Use [docs/human_acceptance.md](/Users/sonics/project/Blink-AI/docs/human_acceptance.md) for the realistic 20 to 30 minute terminal-first human session with companion, helpful-task, and interruption/failure scripts.

### 3. Start the daily companion

```bash
uv run local-companion
```

This is the primary terminal-first product surface. It defaults to `personal_local`, keeps the browser console optional, and uses the same memory, world-model, Action Plane, and embodiment stack as the rest of Blink-AI.

First commands to remember:

- type plain text directly
- `/listen`
- `/help`
- `/status`
- `/console`
- `/quit`

If you want the shortest daily-use walkthrough instead of the full repo guide, go straight to [docs/companion_quickstart.md](/Users/sonics/project/Blink-AI/docs/companion_quickstart.md).

### 4. Optional browser/operator surface

```bash
uv run blink-appliance
```

This is the canonical browser/operator appliance path on macOS. It:

- starts the existing desktop-first FastAPI service on `127.0.0.1`
- repairs the runtime directory layout and persists appliance setup in `runtime/appliance_profile.json`
- requests a short-lived localhost bootstrap session instead of asking you to copy a runtime token from disk
- opens the browser to the setup page until the local appliance profile is saved, then drops into `/console`
- keeps typed fallback available even when microphone or camera availability is degraded

Useful appliance commands:

```bash
uv run blink-appliance --doctor
uv run blink-appliance --reset-runtime
uv run blink-appliance --open-console
uv run blink-appliance --no-open-console
```

### 4a. Start the one-process desktop service directly

```bash
uv run uvicorn embodied_stack.desktop.app:app --reload --port 8000
```

This remains the lower-level local development path when you want direct service control without the appliance launcher.

Useful desktop-first configuration:

```bash
BLINK_RUNTIME_MODE=desktop_virtual_body
BLINK_MODEL_PROFILE=local_dev
BLINK_BACKEND_PROFILE=local_fast
BLINK_VOICE_PROFILE=desktop_local
BLINK_CAMERA_SOURCE=default
BLINK_BODY_DRIVER=virtual
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json
```

Useful serial landing-zone configuration:

```bash
BLINK_RUNTIME_MODE=desktop_serial_body
BLINK_BODY_DRIVER=serial
BLINK_SERIAL_TRANSPORT=live_serial
BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811
BLINK_SERVO_BAUD=1000000
BLINK_SERIAL_TIMEOUT_SECONDS=0.2
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json
```

Use that port as the current known-good default for the validated bench setup, but still rerun `body-calibration ports` or `blink-serial-doctor` first if the device node changes.

In Stage C and Stage D, `/console` also surfaces serial body connect, disconnect, scan, ping, read-health, arm, disarm, write-neutral, semantic smoke, teacher review, and honest degraded body state without taking the desktop runtime down.

Stage 6C also adds browser runtime settings:

```bash
BLINK_ACTION_PLANE_BROWSER_BACKEND=disabled
BLINK_ACTION_PLANE_BROWSER_HEADLESS=true
BLINK_ACTION_PLANE_BROWSER_STORAGE_DIR=runtime/actions/browser
BLINK_ACTION_PLANE_BROWSER_ALLOWED_HOSTS=
```

Supported browser actions are:

- `open_url`
- `capture_snapshot`
- `extract_visible_text`
- `summarize_page`
- `find_click_targets`
- `click_target`
- `type_text`
- `submit_form`

Read-first browser actions execute immediately when the connector is configured. Effectful browser actions remain approval-gated for user-turn and proactive paths, and operator-console browser actions execute with implicit operator approval through the same Action Plane policy layer.

Stage 6D also adds workflow runtime settings:

```bash
BLINK_WORKFLOW_MORNING_BRIEFING_TIME=09:00
BLINK_WORKFLOW_RUN_TIMEOUT_SECONDS=900
```

The current workflow library is:

- `capture_note_and_reminder`
- `morning_briefing`
- `event_lookup_and_open_page`
- `reminder_due_follow_up`

Workflows are code-defined and versioned in the repo, persisted under `runtime/actions/workflows/`, and executed one deterministic step at a time through the same Action Plane gateway used by connector actions. Proactive workflow evaluation runs on the existing `ShiftAutonomyRunner` tick; there is no separate Stage 6D daemon.

Stage 6E adds durable action flywheel artifacts:

- live `blink_action_bundle/v1` exports under `runtime/actions/exports/action_bundles/<bundle_id>/`
- deterministic action replay outputs under `runtime/actions/exports/action_replays/<replay_id>/`
- episode linkage through `derived_artifact_files["action_bundle_index"]`
- research/benchmark carry-through for linked action bundles, linked action replays, and action-quality metrics

Stage 6F productizes those Stage 6 surfaces:

- `/console` now treats Stage 6 as a single Action Center instead of scattered approval, workflow, browser, and bundle panes
- `GET /api/operator/action-plane/overview` provides one decision-ready payload for the Action Center queue, inspector, browser preview, recent bundles, and latest replays
- `blink-appliance` readiness now surfaces Action Plane health, browser degradation, pending approvals, waiting workflows, review-required restart items, and the next recommended operator step
- `local-companion` now supports `/actions status`, `/actions approvals`, `/actions approve <action_id> [note]`, `/actions reject <action_id> [note]`, `/actions history [limit]`, `/actions connectors`, `/actions workflows`, and `/actions bundle <bundle_id>`
- runtime boot now reconciles nonterminal Stage 6 work conservatively: uncertain side effects become `uncertain_review_required`, blocked workflows pause with `runtime_restart_review`, and nothing auto-replays or auto-approves after restart

Serial transport modes:

- `dry_run`
- `fixture_replay`
- `live_serial`

Canonical interaction profiles:

- `companion_live`
- `m4_pro_companion`
- `cloud_demo`
- `local_dev`
- `offline_stub`

Canonical backend profiles:

- `companion_live`
- `cloud_best`
- `m4_pro_companion`
- `local_balanced`
- `local_fast`
- `offline_safe`

Canonical embodiment profiles:

- `bodyless`
- `virtual_body`
- `serial_body`

Voice profiles:

- `desktop_local`
- `browser_live`
- `offline_stub`

Supported runtime modes:

- `desktop_bodyless`
- `desktop_virtual_body`
- `desktop_serial_body`
- `tethered_future`
- `degraded_safe_idle`

### 3a. Local companion details

```bash
uv run local-companion
```

This is the maintained terminal-first companion path. It starts the always-on local companion supervisor that:

- runs terminal-first by default and keeps the browser console as an explicit secondary surface
- exposes `/console` from the same runtime when you opt in with `--open-console` or when terminal stdin is unavailable
- defaults to `personal_local` context for a personal desktop companion unless a demo or site flow explicitly overrides it
- keeps the scene observer active in the background when camera input is enabled
- defaults to push-to-talk through explicit `/listen`
- also supports explicit streaming local audio through `--audio-mode open_mic` or `/open-mic on`
- routes the turn through the same world-model, skill, memory, and body-semantics stack used everywhere else
- speaks replies through the Mac speaker when local speech output is available
- keeps typed fallback available through plain text or `/type <text>`
- prints inspectable runtime status with model profile, active skill, perception freshness, memory status, device health, body mode, fallback state, audio mode, voice-loop state, turn latency telemetry, scene-cache age, reminder count, model residency, scene-observer state, and trigger state through `/status`
- surfaces relationship continuity in `/status`, including returning-user state, tone bounds, planning style, and open follow-ups when present
- exports a local evidence bundle automatically when the loop exits, unless `--no-export` is passed

Useful local companion controls:

- `/help`
- `/listen`
- `/type <text>`
- `/open-mic on|off`
- `/camera`
- `/interrupt`
- `/status`
- `/console`
- `/export`
- `/actions status`
- `/actions approvals`
- `/actions approve <action_id> [note]`
- `/actions reject <action_id> [note]`
- `/actions history [limit]`
- `/actions connectors`
- `/actions workflows`
- `/actions bundle <bundle_id>`
- `/quit`

Terminal note:

- blank `Enter` is a no-op in `local-companion`
- this avoids accidental voice capture from arrow-key escape noise or prompt redraw artifacts
- use `/listen` when you want one voice turn
- `/camera` now persists the captured frame under `runtime/perception_frames/` and prints the saved path
- the most recent camera frame is also mirrored to `runtime/perception_frames/latest_camera_snapshot.<ext>`

Useful local companion host flags:

- `--terminal-ui auto|on|off`
- `--console-port <port>`
- `--open-console`
- `--no-open-console`

Discoverability shortcuts:

- `uv run local-companion --help`
- `/help`
- [docs/companion_quickstart.md](/Users/sonics/project/Blink-AI/docs/companion_quickstart.md)

Context control:

- `--context-mode personal_local|venue_demo`
- `BLINK_CONTEXT_MODE=personal_local|venue_demo`

`uv run local-companion` defaults to `personal_local`. Story, scene replay, and demo-oriented commands force `venue_demo` so venue-demo behavior remains deterministic and explicit.

### 3b. Run the local doctor harness

```bash
uv run local-companion-doctor
```

This probes the actual Mac-local stack and writes `runtime/diagnostics/local_mbp_config_report.md`. The report distinguishes:

- `machine_blocker` issues such as unreachable Ollama, missing local models, or denied camera access
- `repo_or_runtime_bug` issues such as backend/profile mismatches or wrong runtime routing
- `degraded_but_acceptable` issues where the companion remains usable but is still below the intended local-product bar

It also prints explicit next actions so the result is decision-ready: fix the machine, fix the repo/runtime, rerun certification, or treat the Mac as safe to demo.

### 3c. Run the no-robot certification lane

```bash
uv run local-companion-certify
uv run local-companion-failure-drills
uv run local-companion-burn-in
```

Or through maintained Make targets:

```bash
make local-companion-certify
make local-companion-failure-drills
make local-companion-burn-in
make local-companion-stress
```

`uv run local-companion-certify` aggregates:

- `local-companion-doctor`
- `local-companion-checks`
- `always-on-local-checks`
- `continuous-local-checks`
- the maintained `local_companion_story`
- the maintained `desktop_story` regression lane

The aggregate certification bundle is written under `runtime/diagnostics/local_companion_certification/<cert_id>/` and separates:

- machine readiness on the actual Mac
- repo/runtime correctness
- companion behavior quality
- operator UX quality
- final verdict, blocking issues, rubric scores, and next actions

`uv run local-companion-failure-drills` is the deterministic failure-injection lane for provider failure, malformed tool output, tool exceptions, device denial, approval denial, unsupported actions, memory conflict resolution, and serial safety gates.

`uv run local-companion-burn-in` is the bounded long-run regression lane for repeated text turns, reminder/workflow continuity, interruption recovery, trigger stability, repeated startup or shutdown, repeated mode switching, and export linkage.

Use [local_companion_certification_runbook.md](/Users/sonics/project/Blink-AI/docs/local_companion_certification_runbook.md) for the decision workflow.

### 3d. Run the native desktop-local loop

```bash
uv run desktop-local-loop
```

This remains the lower-level CLI entrypoint underneath `uv run local-companion`.

Useful local-companion configuration:

```bash
BLINK_RUNTIME_MODE=desktop_virtual_body
BLINK_MODEL_PROFILE=companion_live
BLINK_BACKEND_PROFILE=companion_live
BLINK_VOICE_PROFILE=desktop_local
BLINK_CAMERA_SOURCE=default
BLINK_CAMERA_DEVICE=default
BLINK_MIC_DEVICE=default
BLINK_SPEAKER_DEVICE=system_default
BLINK_DEVICE_PRESET=internal_macbook
BLINK_APPLIANCE_PROFILE_FILE=runtime/appliance_profile.json
BLINK_NATIVE_CAPTURE_SECONDS=6.0
BLINK_NATIVE_TRANSCRIPTION_LOCALE=en-US
BLINK_ALWAYS_ON_ENABLED=true
BLINK_CONTEXT_MODE=personal_local
BLINK_AUDIO_MODE=push_to_talk
BLINK_LOCAL_MODEL_PREWARM=false
BLINK_OBSERVER_INTERVAL_SECONDS=2.5
BLINK_SCENE_CHANGE_THRESHOLD=0.08
BLINK_SEMANTIC_REFRESH_MIN_INTERVAL_SECONDS=20.0
BLINK_VOICE_ARM_TIMEOUT_SECONDS=12.0
BLINK_VAD_SILENCE_MS=900
BLINK_VAD_MIN_SPEECH_MS=250
BLINK_MODEL_IDLE_UNLOAD_SECONDS=120
BLINK_MEMORY_DIGEST_INTERVAL_MINUTES=10
WHISPER_CPP_BINARY=/path/to/whisper-cli
WHISPER_CPP_MODEL_PATH=/path/to/ggml-base.en.bin
PIPER_BINARY=/path/to/piper
PIPER_MODEL_PATH=/path/to/model.onnx
OLLAMA_KEEP_ALIVE=5m
OLLAMA_TEXT_TIMEOUT_SECONDS=12
OLLAMA_TEXT_COLD_START_TIMEOUT_SECONDS=30
OLLAMA_VISION_TIMEOUT_SECONDS=30
OLLAMA_EMBED_TIMEOUT_SECONDS=5
```

If `WHISPER_CPP_MODEL_PATH` is unset, Blink-AI now searches common local model locations in this order: `~/.cache/berserker/whisper-cpp/`, `~/.cache/whisper.cpp/`, `/opt/homebrew/share/whisper.cpp/models/`, and the Homebrew `share/whisper-cpp/` directory. An explicit env value still wins.

For local camera capture on this MBP, Blink-AI now prefers the terminal-local `ffmpeg` path. If `/camera` reports a camera-permission timeout, grant camera access to the terminal app you are using and to Homebrew `ffmpeg` when macOS prompts.

### 3f. Run the local typed shell

```bash
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli shell
```

This starts a one-machine typed-input loop on top of the same desktop-local runtime services. It supports text turns, fixture replay, manual presence or scene notes, voice cancel, and safe-idle commands.

Useful one-command demo helpers:

```bash
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli reset
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli scene attentive_listening --reset-first
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli story --story-name desktop_story
uv run local-companion-story
uv run local-companion-checks
uv run always-on-local-checks
uv run continuous-local-checks
uv run local-companion-certify
uv run local-companion-burn-in
```

`story --story-name desktop_story` runs the current desktop-first investor sequence:

- `greeting_presence`
- `attentive_listening`
- `wayfinding_usefulness`
- `memory_followup`
- `safe_fallback_failure`

`uv run local-companion-story` runs the maintained local companion sequence:

- `natural_discussion`
- `observe_and_comment`
- `companion_memory_follow_up`
- `knowledge_grounded_help`
- `safe_degraded_behavior`

`uv run local-companion-checks` runs the focused local companion eval suite for:

- mic and speaker loop closure
- webcam-grounded reply behavior
- backend/profile fallback honesty
- memory retrieval
- relationship continuity with bounded tone and follow-up behavior
- uncertainty honesty
- bodyless and virtual-body continuity

`uv run always-on-local-checks` runs deterministic always-on coverage for:

- canonical M4 Pro local profile resolution
- honest Ollama fallback state reporting
- push-to-talk voice-loop transitions and interrupt handling
- cheap scene-observer refresh behavior
- visual-question-triggered semantic refresh
- memory continuity across bodyless and virtual-body modes

`uv run continuous-local-checks` runs the streaming local companion coverage for:

- open-mic turn transitions and partial transcript evidence
- barge-in interruption handling
- reminder, note, and digest promotion
- local model residency and idle vision unload behavior

`uv run local-companion-failure-drills` runs the deterministic failure and degraded-mode coverage for:

- slow-model presence and provider timeout classification
- malformed tool output and tool-exception containment
- mic, camera-permission, and speaker failure surfaces
- conflicting-memory correction and honest no-hit retrieval
- approval denial and unsupported action handling
- serial port, calibration, and live-write safety gates

`uv run local-companion-certify` is the maintained no-robot release lane for the Mac-local companion path. It writes:

- `runtime/diagnostics/local_companion_certification/latest.json`
- `runtime/diagnostics/local_companion_certification/latest_readiness.json`
- `runtime/diagnostics/local_companion_certification/<cert_id>/...`

`uv run local-companion-burn-in` writes bounded long-run artifacts under `runtime/diagnostics/local_companion_burn_in/<suite_id>/...`.

`make local-companion-soak` is a convenience alias for the burn-in lane, and `make local-companion-stress` runs failure drills plus burn-in back-to-back.

### 3c. Run the Feetech/ST calibration tool

Mac Stage A doctor:

```bash
uv run blink-serial-doctor --ids 1-11 --auto-scan-baud
```

Stage E maintained Mac bench suite:

```bash
uv run blink-serial-bench \
  --transport dry_run \
  --report-root runtime/serial/bench_suites
```

This is the preferred read-only bring-up workflow on macOS. It enumerates ports, prefers `/dev/cu.*`, scans baud candidates, pings IDs, reads position plus richer health, and writes `runtime/serial/bringup_report.json`.

Dry-run scan:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport dry_run scan --ids 1-11
```

Fixture replay:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport fixture_replay \
  --fixture src/embodied_stack/body/fixtures/robot_head_serial_fixture.json \
  ping --ids 1
```

Live serial bring-up when hardware is ready:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  doctor --ids 1-11 --auto-scan-baud
```

Read-only Stage A commands:

- `ports`
- `doctor`
- `scan`
- `ping`
- `read-position`
- `read-health`
- `suggest-env`
- `health`

Motion and calibration-capture commands remain separate from Stage A. Use `docs/serial_head_mac_runbook.md` for the exact Mac bench workflow and failure order.

The maintained real-head observation workflow is now also in the repo:

```bash
BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811 \
BLINK_SERVO_BAUD=1000000 \
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json \
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json \
bash scripts/serial_head_live_observation.sh
```

That sequence exercises the current direct probes, sync groups, and semantic actions one by one, writes per-step artifacts under `runtime/serial/manual_validation/`, and now ends with a neutral-hold tolerance check instead of only a torque-off recovery.

Stage B bench commands are now available on `body-calibration`:

- `capture-neutral`
- `arm-live-motion`
- `disarm-live-motion`
- `list-semantic-actions`
- `semantic-smoke`
- `teacher-review`
- `move-joint`
- `sync-move`
- `write-neutral`
- `torque-on`
- `torque-off`
- `safe-idle`
- `bench-health`

The default live calibration path is `runtime/calibrations/robot_head_live_v1.json`, the live arm lease is `runtime/serial/live_motion_arm.json`, each Stage B write saves a motion artifact under `runtime/serial/motion_reports/`, and Stage D semantic tuning artifacts now live under `runtime/body/semantic_tuning/`.

Stage E adds a maintained bench-suite artifact root under `runtime/serial/bench_suites/`. Each suite writes:

- `suite.json`
- `doctor_report.json`
- `scan_report.json`
- `position_report.json`
- `health_report.json`
- `calibration_snapshot.json`
- `motion_reports_index.json`
- `console_snapshot.json`
- `body_telemetry.json`
- `failure_summary.json`
- `request_response_history.json`

The maintained live-Mac convenience targets are:

- `make serial-doctor`
- `make serial-bench`
- `make serial-neutral`
- `make serial-companion`

`make serial-bench` and `make serial-neutral` require `BLINK_CONFIRM_LIVE_WRITE=1` when they target live hardware.

The opt-in hardware pytest tiers are:

```bash
BLINK_RUN_LIVE_SERIAL_TESTS=1 uv run pytest -m live_serial
BLINK_RUN_LIVE_SERIAL_TESTS=1 BLINK_RUN_LIVE_SERIAL_MOTION_TESTS=1 uv run pytest -m live_serial_motion
```

The live head has already passed the maintained read-only marker, motion smoke marker, and Stage E bench suite on the current Mac wiring. The maintained docs still keep those gates explicit because live motion must remain operator-gated and calibration-dependent.

### 4. Start the optional edge / fake robot API

```bash
uv run uvicorn embodied_stack.edge.app:app --reload --port 8010
```

The edge path is still available for compatibility, demos, and future Jetson/tethered work. The default edge profile is `fake_robot_full`. You can switch the edge runtime profile with `EDGE_DRIVER_PROFILE`:

- `fake_robot_full` for the main simulation-first path
- `jetson_simulated_io` for a Jetson-shaped runtime with simulated adapters
- `jetson_landing_zone` for an honest hardware landing zone with unwired adapters surfaced as unavailable

### 5. Open the operator console

If you launched `uv run blink-appliance`, the browser should already be on the correct localhost URL. Appliance mode now trusts the local browser on localhost and opens `/console` directly with no token prompt.

If you launched the service directly, the console still requires local operator auth. Either:

- open [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console), then
- set `OPERATOR_AUTH_TOKEN` before starting the brain, or
- use `uv run local-companion-token`, or
- read the persistent local token from `runtime/operator_auth.json`

If you launched the full two-process stack with `make demo-up`, use the token recorded in `runtime/tethered_demo/live/stack_info.json`.

In appliance mode, `/console` shows the setup flow first when `runtime/appliance_profile.json` is missing or has not been confirmed yet. That setup surface exposes:

- runtime-directory health and setup issues
- auth mode and config-source status
- selected native microphone, camera, and speaker-routing note
- the current device preset (`internal_macbook` or `external_monitor`)
- Ollama reachability plus missing-model visibility before you rely on voice or perception paths

If `/console` shows a blank or flashing page in appliance mode, refresh once and make sure you are on the direct console URL rather than an older cached `/appliance/bootstrap/...` link. Appliance mode no longer needs bootstrap URLs or operator tokens.

From there you can:
- create or inspect sessions
- send typed visitor input through the existing `speech_transcript` path
- use browser microphone capture in `browser_live` modes when supported
- use browser camera preview for snapshot capture, manual presence fallback, or local image submission
- reset to a clean investor-demo state or use `Reset + Run Desktop Story` for the default replayable walkthrough
- inspect desktop runtime mode, body driver mode, active expression, gaze target, and virtual-body state
- inspect the composed desktop demo profile, provider state, latest perception status, fallback events, and emitted embodied actions
- submit manual annotations or replay built-in perception fixtures
- inspect the latest structured perception snapshot with confidence, source metadata, and history
- inspect the current embodied world model, engagement state, attention target, and executive decision reasons
- inspect the current shift state, timer snapshot, recent reason codes, and transition history
- inspect live shift metrics such as greetings, conversation completion, escalation follow-through, degraded time, fallback rate, and limited-awareness rate
- inspect the loaded venue operations policy, including proactive greeting settings and next scheduled prompt
- inspect open and closed incident tickets, operator assignments, suggested staff contacts, and incident timelines
- inspect recent pilot shift reports generated by the day-in-the-life simulator
- inspect replay mode with frame or clip source, extracted scene facts, engagement timeline, final chosen action, and scene scorecard
- run investor scenes and seeded scenarios
- inject presence, touch, heartbeat, and low-battery events
- watch transcript, telemetry, command history, and trace summaries update in one place
- operate against the sample pilot-site packs in [pilot_site/README.md](/Users/sonics/project/Blink-AI/pilot_site/README.md) or point the brain at another venue pack with `VENUE_CONTENT_DIR`

### 6. Run the dry-run scenario sequence

```bash
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

### 7. Run the in-process smoke path

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.smoke
```

This runs the main investor-style demo flow end-to-end through the API-first demo coordinator and writes a report artifact under `runtime/`.

### 8. Run the investor demo checks

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.checks
```

Or:

```bash
make demo-checks
```

This runs the most important investor-path regressions in-process and writes a check-suite artifact under `runtime/demo_checks/`.

### 9. Run the real tethered HTTP smoke path

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.tethered
```

Or:

```bash
make tethered-smoke
```

This launches the brain and edge as separate processes, waits for health checks, runs reset plus a demo run through the real HTTP gateway, and prints the resulting artifact paths.

### 10. Run the multimodal demo checks

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.multimodal_checks
```

Or:

```bash
make multimodal-demo-checks
```

This replays the multimodal investor scenes, scores them, and writes a dedicated evidence bundle under `runtime/demo_checks/multimodal/`.

### 11. Run the day-in-the-life pilot shift simulator

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.shift_simulator
```

This replays the built-in community-center pilot day and writes a pilot evidence bundle under `runtime/shift_reports/`.

You can also point it at another JSON fixture:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.shift_simulator path/to/pilot_day.json
```

### 12. Export reusable multimodal episodes

After a demo run or session, export an append-only multimodal episode bundle:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.episodes export-run <run_id>
```

Or export a single live session:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.episodes export-session <session_id>
```

You can also browse what has already been exported:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.episodes list
```

Episodes are written under `runtime/episodes/`. See [docs/data_flywheel.md](/Users/sonics/project/Blink-AI/docs/data_flywheel.md) for the schema and the future training/eval mapping.
The local companion loop also auto-exports a session episode on exit by default, and those live-session bundles now include `runtime_snapshot.json`, `console_snapshot.json`, `body_telemetry.json`, `serial_failure_summary.json`, `serial_request_response_history.json`, `audio_loop.json`, `partial_transcripts.json`, `scene_cache.json`, `memory_promotions.json`, and `model_residency.json`.

Pilot-shift reports can also be exported into the same episode format:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.episodes export-shift-report <report_id>
```

### 13. Run the optional one-command local tethered demo stack

```bash
make demo-up
```

This is the compatibility path, not the default first run. It starts a known-good two-process tethered stack with:

- brain on `127.0.0.1:8000`
- edge on `127.0.0.1:8010`
- edge profile `jetson_simulated_io`
- brain runtime mode `tethered_future`
- runtime artifacts under `runtime/tethered_demo/live/`

Operational helpers:

- `make demo-status` for health, readiness, and auth status
- `make demo-reset` to reset the running stack
- `Ctrl-C` in the `make demo-up` terminal to stop both services

`runtime/tethered_demo/live/stack_info.json` is the quickest place to confirm URLs, the active edge profile, and the local operator token for that launched stack.

## Demo evidence pack

Each `POST /api/demo-runs` call now writes a report bundle under `runtime/demo_runs/<run_id>/`:

- `summary.json` with pass/fail, timing, backend, fallback, and final world state
- `sessions.json` with session metadata and transcript-bearing session records for that run
- `traces.json` with the trace records for that run
- `telemetry_log.json` with the edge telemetry history
- `command_history.json` with emitted commands and acknowledgements
- `perception_snapshots.json` with any structured perception results captured during the run
- `world_model_transitions.json` with before/after embodied-state transitions
- `executive_decisions.json` with the explicit control-policy decisions
- `shift_transitions.json` with long-horizon operating-state transitions and reasons
- `incidents.json` with local handoff tickets and current status
- `incident_timeline.json` with auditable incident create/acknowledge/assign/resolve events
- `grounding_sources.json` with the final reply grounding sources
- `manifest.json` with the file map

The dedicated demo-check suite writes a parallel bundle under `runtime/demo_checks/<suite_id>/`, with one subdirectory per regression check plus a suite `summary.json`.

Episode exports write a separate append-only bundle under `runtime/episodes/<episode_id>/`:

- `summary.json` with schema version, source type, counts, and artifact pointers
- `episode.json` with the full exported multimodal episode
- `sessions.json`
- `transcript.json`
- `traces.json`
- `tool_calls.json`
- `perception_snapshots.json`
- `world_model_transitions.json`
- `executive_decisions.json`
- `incidents.json`
- `incident_timeline.json`
- `commands.json`
- `acknowledgements.json`
- `telemetry.json`
- `episodic_memory.json`
- `semantic_memory.json`
- `profile_memory.json`
- `grounding_sources.json`
- `asset_refs.json`
- `annotations.json`
- `runtime_snapshot.json` for live local session exports
- `voice_loop.json`, `audio_loop.json`, `partial_transcripts.json`, `scene_cache.json`, `memory_promotions.json`, `scene_observer.json`, `trigger_history.json`, `model_residency.json`, and `ollama_runtime.json` for always-on local session exports
- `manifest.json`

## Clean demo reset

Before an investor session, start from a known state:

```bash
curl -X POST http://127.0.0.1:8000/api/reset \
  -H 'Content-Type: application/json' \
  -d '{"reset_edge": true, "clear_user_memory": true, "clear_demo_runs": true}'
```

That clears brain runtime state, resets the simulated edge, and removes prior demo report bundles so the next run starts cleanly.

If you launched the stack with `make demo-up`, `make demo-reset` uses the local runtime stack metadata and operator token automatically.

## Tethered demo runbook

For the real two-process compatibility path, use two terminals:

```bash
EDGE_DRIVER_PROFILE=jetson_simulated_io uv run uvicorn embodied_stack.edge.app:app --host 127.0.0.1 --port 8010
```

```bash
EDGE_BASE_URL=http://127.0.0.1:8010 OPERATOR_AUTH_TOKEN=choose-a-local-token uv run uvicorn embodied_stack.brain.app:app --host 127.0.0.1 --port 8000
```

Then open `/console` on the brain service. The runtime banner now shows:

- `edge_transport_mode`: `http` or `in_process`
- `edge_transport_state`: `healthy` or `degraded`
- `edge_transport_error` when the tether is down or responses are malformed

When the HTTP path degrades, Blink-AI preserves a degraded safe-idle heartbeat and telemetry snapshot instead of silently pretending the edge is still reachable.

`/ready` is the stronger operational check for both services. It reports whether the current brain config, edge profile, provider config, voice mode, and watchdog surfaces are actually usable for a demo.

## Perception demo modes

Blink-AI now supports a structured pre-hardware perception layer on the Mac brain.

- `stub`: honest limited-awareness fallback with no scene claims
- `manual_annotations`: operator-entered structured observations that still publish into the normal session/trace flow
- `browser_snapshot`: real browser image ingestion with provenance, but no semantic claims unless you use another analysis mode
- `video_file_replay`: deterministic replay from local fixture files
- `multimodal_llm`: optional OpenAI-compatible multimodal adapter for semantic frame analysis

The browser console exposes all of these as operator-friendly controls. If no camera or provider is available, typed input and non-perception demo paths continue to work normally.

## Embodied world model and social executive

Blink-AI now uses the perception layer to drive a deterministic embodied interaction policy instead of behaving like a plain chatbot with robot commands.

- the world model tracks who is in view, likely active speaker/session, engagement state, visual anchors, recent visible text, recent named objects, and the current attention target
- ephemeral social state carries confidence plus time-to-live semantics so old scene facts expire instead of silently becoming permanent truth
- the interaction executive decides when to auto-greet, suppress repeated greetings, ask for clarification, keep listening, shorten a reply because engagement is dropping, escalate to a human, or stop speaking on interruption
- executive decisions are logged in traces and shown in the operator console with explicit reason codes

This stays policy-based and inspectable. LLMs can help generate replies, but they are not the sole source of control behavior.

## Venue knowledge packs

Blink-AI now uses a file-backed venue knowledge layer instead of relying only on seeded Python constants.

The default sample pack lives in:

- [pilot_site/demo_community_center](/Users/sonics/project/Blink-AI/pilot_site/demo_community_center)

Supported ingestion formats:

- FAQs in `json`, `yaml`, or `yml`
- event schedules in `csv` or `json`
- markdown venue docs
- plain-text room lists
- plain-text staff contacts
- optional `.ics` calendar files

The brain loads this pack from `VENUE_CONTENT_DIR`, keeps source references in tool metadata, and uses the same imported data in both deterministic fallback mode and provider-backed dialogue mode.

If a room, event, sign, or schedule entry is missing or conflicting, Blink-AI now says that clearly instead of inventing a venue fact.

## Secrets hygiene

- Do not store live provider keys in tracked files.
- `keys.txt` is no longer part of the repo workflow.
- Use env vars such as `GRSAI_API_KEY` and `OPERATOR_AUTH_TOKEN`.
- Runtime-local auth and launch metadata are written under ignored `runtime/` paths.
- Keep `.env`, `.env.local`, and any local secret files out of version control.
- Keep venue content packs under local directories like `pilot_site/` rather than hard-coding site facts into Python modules.

## Edge driver profiles

The edge runtime is now adapter-driven rather than a single opaque stub.

- actuator boundaries: speaker trigger, display, LED, head pose
- input boundaries: touch, button, presence, transcript relay
- monitor boundaries: network, battery, heartbeat

`GET /api/capabilities` declares which adapters are enabled for the current profile. `GET /api/telemetry` exposes runtime adapter health so the operator can see whether an adapter is `active`, `simulated`, `unavailable`, `degraded`, or `disabled`.

Profiles:

- `fake_robot_full`: everything needed for simulation is present as simulated adapters
- `jetson_simulated_io`: same brain contract, but under a Jetson-shaped adapter profile for pre-hardware tethered demos
- `jetson_landing_zone`: actuator and sensor boundaries are declared, but unwired adapters stay visibly unavailable until a real Jetson implementation plugs them in

## Main API surface

### Brain
- `GET /ready`
- `POST /api/reset`
- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/operator-notes`
- `POST /api/sessions/{session_id}/response-mode`
- `POST /api/events`
- `POST /api/voice/turn`
- `GET /api/world-state`
- `GET /api/world-model`
- `GET /api/executive/decisions`
- `GET /api/scenarios`
- `POST /api/scenarios/{scenario_name}/replay`
- `POST /api/demo-runs`
- `GET /api/demo-runs`
- `GET /api/demo-runs/{run_id}`
- `GET /api/operator/auth/status`
- `POST /api/operator/auth/login`
- `POST /api/operator/auth/logout`
- `GET /api/operator/snapshot`
- `GET /api/operator/incidents`
- `GET /api/operator/incidents/{ticket_id}`
- `POST /api/operator/incidents/{ticket_id}/acknowledge`
- `POST /api/operator/incidents/{ticket_id}/assign`
- `POST /api/operator/incidents/{ticket_id}/notes`
- `POST /api/operator/incidents/{ticket_id}/resolve`
- `POST /api/operator/text-turn`
- `POST /api/operator/inject-event`
- `POST /api/operator/safe-idle`
- `POST /api/operator/voice/cancel`
- `POST /api/operator/perception/snapshots`
- `POST /api/operator/perception/replay`
- `GET /api/operator/perception/latest`
- `GET /api/operator/perception/history`
- `GET /api/operator/perception/fixtures`
- `GET /api/logs`
- `GET /api/traces`
- `GET /api/traces/{trace_id}`

### Edge
- `GET /ready`
- `POST /api/commands`
- `GET /api/telemetry`
- `GET /api/telemetry/log`
- `GET /api/heartbeat`
- `POST /api/sim/events`
- `POST /api/safe-idle`
- `GET /api/capabilities`
- `POST /api/reset`

## Backend routing

Blink-AI now routes five backend kinds explicitly:

- text reasoning
- vision understanding
- embeddings
- speech-to-text
- text-to-speech

The backend router resolves a backend profile first, then optional per-kind overrides, and reports each selected backend as `configured`, `warm`, `unavailable`, `degraded`, or `fallback_active` in `/health`, `/ready`, and the operator snapshot. Ollama-backed status also exposes reachability, requested model, active model, warm/cold state, keep-alive policy, the last successful latency, the last failure reason and time, the last timeout used, and whether a cold-start retry was consumed.

The latest live-turn diagnostics in the operator snapshot and `/status` now surface STT latency, reasoning latency, TTS-start latency, end-to-end turn latency, and Ollama warm-vs-cold-start signals when a local text model is involved.

Useful default daily companion configuration:

```bash
export BLINK_MODEL_PROFILE=companion_live
export BLINK_BACKEND_PROFILE=companion_live
export BLINK_CONTEXT_MODE=personal_local
export BLINK_AUDIO_MODE=push_to_talk
export GRSAI_API_KEY=YOUR_REAL_KEY
export GRSAI_BASE_URL=https://grsai.dakka.com.cn
export GRSAI_TEXT_BASE_URL=https://grsai.dakka.com.cn
export GRSAI_MODEL=gpt-4o-mini
```

Useful local M4 Pro configuration:

```bash
export BLINK_BACKEND_PROFILE=m4_pro_companion
export BLINK_CONTEXT_MODE=personal_local
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_TEXT_MODEL=qwen3.5:9b
export OLLAMA_VISION_MODEL=qwen3.5:9b
export OLLAMA_EMBEDDING_MODEL=embeddinggemma:300m
export OLLAMA_TEXT_TIMEOUT_SECONDS=12
export OLLAMA_TEXT_COLD_START_TIMEOUT_SECONDS=30
export OLLAMA_VISION_TIMEOUT_SECONDS=30
export OLLAMA_EMBED_TIMEOUT_SECONDS=5
export BLINK_STT_BACKEND=apple_speech_local
export BLINK_TTS_BACKEND=macos_say
```

Useful cloud-first configuration:

```bash
export BLINK_BACKEND_PROFILE=cloud_best
export GRSAI_API_KEY=YOUR_REAL_KEY
export GRSAI_BASE_URL=https://grsai.dakka.com.cn
export GRSAI_TEXT_BASE_URL=https://grsai.dakka.com.cn
export GRSAI_MODEL=gpt-4o-mini
export PERCEPTION_MULTIMODAL_API_KEY=YOUR_REAL_KEY
export PERCEPTION_MULTIMODAL_BASE_URL=https://api.openai.com
export PERCEPTION_MULTIMODAL_MODEL=gpt-4.1-mini
```

Notes:
- `GRSAI_TEXT_BASE_URL` is used for chat calls when set; otherwise Blink-AI falls back to `GRSAI_BASE_URL`.
- either GRSai base URL style is accepted with or without a trailing `/v1`.
- `companion_live` is the flagship day-to-day profile: local memory, orchestration, and media stay on-device, dialogue prefers the fast provider path, and semantic vision escalates only for explicit visual questions or supervised refresh.
- `m4_pro_companion` is the canonical local preset on this Mac and prewarms text plus embeddings on startup; vision stays on-demand.
- `local_balanced` prefers one local Ollama text or vision model at a time plus local embeddings and native media services.
- `local_fast` avoids a resident local vision model and defaults embeddings to the deterministic hash path to reduce unified-memory pressure.
- `offline_safe` keeps the system usable with rule-based text, typed STT fallback, stub TTS, and deterministic local retrieval only.

## Perception defaults

The raw config fallback perception mode is `stub`, which means Blink-AI stays honest about limited situational awareness instead of inventing scene facts when no richer path is composed.

For `companion_live`, the default camera path stays on `native_camera_snapshot` so day-to-day conversation is not paying semantic-vision cost on every turn. Semantic vision is still available through explicit visual questions and supervised refresh paths when `multimodal_llm` or `ollama_vision` is configured.

To keep local perception replayable before final hardware, Blink-AI also supports:

- `manual_annotations` through the console
- `browser_snapshot` for real image capture and provenance logging
- `video_file_replay` through built-in local fixtures
- `multimodal_llm` through an optional OpenAI-compatible multimodal adapter
- `ollama_vision` through a local Ollama multimodal model when configured

Environment variables:

```bash
export PERCEPTION_DEFAULT_PROVIDER=stub
export PERCEPTION_FIXTURE_DIR=src/embodied_stack/demo/data
export PERCEPTION_MULTIMODAL_API_KEY=
export PERCEPTION_MULTIMODAL_BASE_URL=https://api.openai.com
export PERCEPTION_MULTIMODAL_MODEL=gpt-4.1-mini
export PERCEPTION_MULTIMODAL_TIMEOUT_SECONDS=8.0
```

## Voice defaults

The default `desktop_local` voice profile now resolves to `desktop_native` when the local Mac has:

- `ffmpeg` available for AVFoundation audio/video capture
- the bundled Apple Speech helper compiled successfully
- the macOS `say` command available for reply playback

That gives Blink-AI a browser-free local loop with Mac microphone input, Mac speaker output, and optional webcam capture. If any of those pieces are unavailable, Blink-AI degrades honestly to `macos_say` typed input or `stub_demo`.

Useful native local settings:

```bash
export BLINK_VOICE_PROFILE=desktop_local
export BLINK_MIC_DEVICE=default
export BLINK_NATIVE_CAPTURE_SECONDS=6.0
export BLINK_NATIVE_TRANSCRIPTION_LOCALE=en-US
export MACOS_TTS_VOICE=Samantha
export MACOS_TTS_RATE=185
```

Notes:

- native microphone capture is bounded single-turn capture, not continuous VAD
- the first live run may trigger macOS microphone and speech-recognition permission prompts
- if native capture is unavailable or permission is denied, Blink-AI stays usable through `/type <text>`, `stub_demo`, and the typed shell

For a real live input loop in the browser console, switch the voice mode to:

- `browser_live` for browser speech recognition plus stubbed reply audio
- `browser_live_macos_say` for browser speech recognition plus local macOS spoken replies

These browser modes remain supported, but they are now compatibility paths rather than the primary live desktop loop.

## Key docs

- [Documentation Guide](docs/README.md)
- [Product Direction](docs/product_direction.md)
- [Architecture](docs/architecture.md)
- [Pre-Hardware Solution](docs/pre_hardware_solution.md)
- [Protocol Notes](docs/protocol.md)
- [Development Guide](docs/development_guide.md)
- [Investor Demo](docs/investor_demo.md)
- [Plan](PLAN.md)

For the deterministic investor show lane, use the canonical `investor_ten_minute_v1` commands documented in [Investor Demo](docs/investor_demo.md) and [Investor Show Runbook](docs/investor_show_runbook.md). The terminal-first companion remains the primary product path.
