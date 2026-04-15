# Pre-Hardware Solution

## Executive summary

Blink-AI should keep moving before final hardware arrives because the primary product is the AI presence living in the computer, not the robot body.

The practical setup today is:

- M4 Pro 24GB MacBook Pro for current local development and testing
- desktop-local camera, microphone, speaker, and operator UI as the active embodiment runtime
- optional expressive head/body adapter that may be absent, virtual, or serial later
- nearby Mac Studio as the intended higher-capacity host later when heavier workloads matter
- Jetson Nano retained as a future tether or robot-side transport option, not the current blocker

That keeps the long-term path open while making the local-first companion runtime the honest center of gravity right now.

## What is already worth building pre-hardware

### 1. The Mac-side companion platform
Build the real application center of gravity now:

- session management
- dialogue engine interface
- voice pipeline interface
- live operator console
- rule-based fallback behavior
- bounded initiative that can suggest or ask first without requiring full always-on full-duplex voice
- optional local Ollama backend
- structured perception provider layer with browser/image ingestion, fixture replay, and optional multimodal analysis
- embodied world model and deterministic social-interaction executive
- world state tracking
- memory and operator notes
- knowledge retrieval
- scenario replay
- demo run orchestration
- logs and traces

### 2. The body and tether contract
Keep the embodiment contract simple and stable:

- semantic embodied actions such as expression, gaze, gesture, animation, and safe idle
- command acknowledgement
- telemetry history and heartbeat inspection
- safe idle fallback
- body capability profiles and normalized pose models
- a virtual-body path that stays useful with no powered hardware
- a serial-body landing zone and future Jetson bridge behind interfaces

### 3. Venue knowledge packs
Use ingestible venue content that is commercially believable:

- FAQ and hours
- event schedule
- room directions and visible-signage hints
- staff contacts and escalation rules
- structured feedback prompts
- markdown operational notes

### 4. Replayable investor demos
Every demo path should be inspectable and deterministic:

- scenario replay endpoint
- demo run endpoint with persisted reports
- exportable local evidence bundles for demo runs and check suites
- a tethered two-process smoke path that validates the real HTTP brain↔edge route
- operator console with visible transcript, telemetry, commands, and traces
- operator console with visible perception snapshots, confidence, provenance, and history
- visible trace IDs
- world state endpoint
- session inspection
- graceful operator handoff
- safe fallback scenario with visible degraded mode

## Why the current MBP is now the real runtime

The current M4 Pro 24GB MacBook Pro is no longer just a development stand-in. It is the real host for the immediate local-first companion loop.

What stays constant:

- the brain remains on a nearby Mac-class machine
- high-level intelligence stays off the future robot-side controller
- shared contracts remain the integration boundary

What changes later:

- heavier models can move to a nearby Mac Studio if needed
- body transport can move behind serial or a Jetson bridge without changing brain semantics

## Responsibilities split

## Desktop runtime responsibilities
- local camera, microphone, speaker, and typed-input fallback
- local operator console and replay tooling
- local runtime profiles for bodyless, virtual body, and serial body
- local execution of semantic body commands when no Jetson path is present

## Mac brain responsibilities
- community dialogue
- speech orchestration and demo voice runtime
- multimodal perception providers, perception event bus, and perception history
- embodied world-model tracking and social interaction policy
- memory and personalization
- FAQ, event, and wayfinding tools
- venue knowledge ingestion and retrieval
- operator escalation logic
- session and trace management
- scenario replay, demo logging, and demo evidence packs
- tethered HTTP transport hardening and failure classification

## Future tether / Jetson responsibilities
- optional remote device I/O
- optional future servo transport and watchdog path
- command acknowledgement and heartbeat when the body is externally hosted
- rejecting unsupported or unsafe low-level commands

## What to defer until hardware arrives

- motor tuning
- sensor calibration
- real acoustics and microphone placement
- real battery behavior
- physical networking issues on the platform
- final voice latency tuning against the deployed Mac Studio
- real camera transport, calibration, and on-robot perception adapters

## Success criteria before hardware

Before real hardware is required, Blink-AI should already have:

- at least 4 seeded community scenarios
- session and user memory behavior
- voice turn handling that still works without provider credentials
- traceable reasoning logs
- replayable demo checks with pass/fail scoring and exportable artifacts
- a fake robot path that still works
- safe edge behavior that rejects unsupported movement and degrades on disconnect or low battery
- a Jetson-shaped adapter profile that still works with simulated I/O before final hardware arrives
- a clean migration path from the MBP dev host to the Mac Studio
- perception that can already be demoed honestly without final robot hardware
- initiative that feels alive in the terminal-first companion path without becoming spammy or unsafe
