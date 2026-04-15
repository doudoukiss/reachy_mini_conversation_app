# Blink-AI Tutorial

This file is the beginner-friendly, phase-by-phase guide for Blink-AI.

It has two jobs:

1. help a new person understand what Blink-AI is and how to run it
2. preserve the project’s development history in a format that is easy to extend after each major update

If you are a human reader, start with:

- `Current Snapshot`
- `Beginner Mental Model`
- `Current First Run`

If you are Codex or another coding agent, use this file as high-level project context first, then confirm details against:

- [AGENTS.md](/Users/sonics/project/Blink-AI/AGENTS.md)
- [PLAN.md](/Users/sonics/project/Blink-AI/PLAN.md)
- [README.md](/Users/sonics/project/Blink-AI/README.md)
- [docs/architecture.md](/Users/sonics/project/Blink-AI/docs/architecture.md)
- [docs/protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)

## Tutorial Contract

This file is intentionally append-friendly.
Treat it as an append-only project history plus a current-state onboarding guide.

### Stable Rules

- never renumber old phases
- always append new work as the newest phase at the end
- keep the exact phase section headings in the same order
- keep `Current Snapshot`, `Current First Run`, and `Phase Index` aligned with the latest repo reality
- explain both:
  - what changed
  - why those decisions were made
- prefer concrete explanations over roadmap slogans
- preserve the Mac-brain / future-edge split in every explanation while keeping the desktop runtime as the current center of gravity

### Codex Update Protocol

When updating this file after a major project change:

1. read the latest:
   - `AGENTS.md`
   - `PLAN.md`
   - `README.md`
   - `docs/architecture.md`
   - `docs/protocol.md`
2. update `Current Snapshot` if the current system behavior changed
3. update `Current First Run` if the recommended beginner path changed
4. append one new phase section at the end
5. update `Phase Index`
6. do not delete old phases unless they are factually wrong

### Required Phase Headings

Every new phase must use exactly these headings:

- `Goal`
- `What Was Completed`
- `What Changed In The Repo`
- `Why These Decisions Were Made`
- `What A Beginner Should Understand`
- `Validation At The Time`
- `What Stayed Deferred`

## How To Maintain This File

After each major project update:

1. add one new section at the end using the `Phase Template`
2. update `Current Snapshot` if the current operating reality changed
3. update `Phase Index` with the new phase title
4. keep the language beginner-friendly and concrete
5. explain both:
   - what changed in the repo
   - why the team chose that direction

Do not rewrite older phases unless they are materially inaccurate.
Append new phases so the project history stays readable over time.

## Current Snapshot

Blink-AI is a terminal-first, local-first personal companion operating system with optional embodiment.

The venue-guide flow remains available as an explicit `venue_demo` vertical rather than the default repo identity.

Today, the project works primarily as a desktop-first embodied runtime with:

- a desktop runtime entrypoint that runs the Mac-side brain plus a local embodiment runtime in one process
- a first-class body package that owns semantic expression, gaze, gesture, animation, head profiles, and future transport boundaries
- a strong fake-robot and simulation-first workflow, so most product work can happen before final hardware arrives
- a practical browser operator console with auth, status, reset controls, transcript, telemetry, traces, and investor demo scenes
- a structured perception layer on the Mac brain for manual annotations, browser snapshots, local fixture replay, and optional multimodal analysis
- an embodied world model and deterministic social executive that turn perception into visible greeting, interruption, disengagement, and escalation behavior
- a participant/session router that handles likely active visitors, bounded queueing, and returning-visitor session resume without pretending to know identity
- a shift-level supervisor that tracks long-horizon operating state such as ready, assisting, follow-up, degraded, quiet-hours, and closing
- a local-first incident workflow that turns escalation into real handoff tickets with assignees, notes, suggested staff contacts, and auditable status history
- a file-backed venue knowledge layer that can ingest pilot-site FAQs, schedules, room data, contacts, markdown docs, and optional calendar files
- a data-driven venue-operations layer that lets each pilot site configure opening hours, quiet hours, closing windows, proactive prompts, escalation overrides, accessibility notes, and fallback instructions
- local-first operational tooling for launching the desktop runtime, checking readiness, resetting the stack, exporting demo artifacts, and optionally validating the tethered compatibility path

The edge package still exists, but it is now an optional compatibility and future transport path rather than the main first run.

The current development brain host is an M4 Pro 24GB MacBook Pro.
The intended production brain host is a nearby Mac Studio.

## Beginner Mental Model

Think of Blink-AI as four cooperating layers:

### 1. The desktop runtime

This is the default way to run the project now.
It owns:

- the local process entrypoint
- camera, microphone, speaker, and typed fallback wiring
- desktop runtime modes such as bodyless, virtual body, and serial body
- the in-process embodiment gateway used for everyday development

### 2. The brain

This runs on a nearby Mac.
It owns the “smart” parts:

- conversation
- session memory
- user memory
- FAQ and event lookup
- operator escalation
- demo orchestration
- traces and logs
- voice orchestration

### 3. The body layer

This keeps embodiment semantic instead of device-specific.
It owns:

- normalized body pose/state
- expression, gaze, gesture, and animation semantics
- head-profile loading
- virtual-body behavior
- future serial or tethered transport boundaries

### 4. The edge

This is now optional.
It can run on the robot-side Jetson or another remote controller later.
It stays simple and deterministic.
It owns:

- device I/O
- sensor capture
- heartbeat
- command acknowledgement
- safe idle behavior
- hardware adapter boundaries

### Why the split matters

The project is intentionally designed so the desktop runtime stays productive with no powered body, and any future Jetson does not become a second AI application.
That keeps the system safer, easier to test, and easier to migrate from virtual body to real hardware.

## Stable Rules That Have Stayed True Across Phases

- High-level intelligence stays on the Mac brain.
- The edge stays thin and safety-focused.
- Shared contracts live in `src/embodied_stack/shared/`.
- Simulation-first development is a feature, not a temporary shortcut.
- Investor demos must stay honest.
- The no-credentials local path must keep working.

## Repository Map

- `src/embodied_stack/brain/`: Mac-side runtime
- `src/embodied_stack/desktop/`: default local runtime entrypoint
- `src/embodied_stack/body/`: semantic embodiment and body-driver layer
- `src/embodied_stack/edge/`: optional tethered or future Jetson-side runtime
- `src/embodied_stack/shared/`: shared Pydantic contracts
- `src/embodied_stack/demo/`: demo orchestration, smoke paths, tethered tooling
- `src/embodied_stack/sim/`: simulation utilities and scenario runner
- `docs/`: architecture, protocol, investor flow, and supporting product notes
- `tests/`: automated regression coverage

## Current First Run

### Install and validate

```bash
brew install uv
uv sync --dev
make validate
```

### Run the default local desktop stack

```bash
uv run uvicorn embodied_stack.desktop.app:app --reload --port 8000
```

This starts the brain plus the local desktop embodiment runtime with `desktop_virtual_body` as the default mode.

Useful desktop-first environment variables:

```bash
BLINK_RUNTIME_MODE=desktop_virtual_body
BLINK_MODEL_PROFILE=desktop_local
BLINK_VOICE_PROFILE=desktop_local
BLINK_CAMERA_SOURCE=default
BLINK_BODY_DRIVER=virtual
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json
```

### Optional tethered compatibility stack

```bash
make demo-up
```

This starts:

- brain on `127.0.0.1:8000`
- edge on `127.0.0.1:8010`
- edge profile `jetson_simulated_io`

Useful follow-up commands:

```bash
make demo-status
make demo-reset
make demo-checks
make multimodal-demo-checks
```

### Open the operator console

Open [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)

If you launched the default desktop path and did not set `OPERATOR_AUTH_TOKEN`, read the local operator token from:

- `runtime/operator_auth.json`

If you launched with `make demo-up`, read the operator token from:

- `runtime/tethered_demo/live/stack_info.json`

If you launched the brain manually and did not set `OPERATOR_AUTH_TOKEN`, Blink-AI can generate a local runtime token under:

- `runtime/operator_auth.json`

## Phase Index

- Phase 0: Architecture intent and simulation-first startup
- Phase 1: Shared contracts and basic brain/edge services
- Phase 2: Real brain platform with memory and community tools
- Phase 3: Voice abstractions and replayable demo scenarios
- Phase 4: Operator console and investor demo flow
- Phase 5: Evals, observability, and demo evidence packs
- Phase 6: Provider-backed dialogue and live local interaction loop
- Phase 7: Multi-process tethered path and edge hardware landing zone
- Phase 8: Operational tooling, auth, and demo-day safety
- Phase 9: Multimodal perception and scene-grounded demo inputs
- Phase 10: World model and social interaction executive
- Phase 11: Venue knowledge packs and perception-grounded venue intelligence
- Phase 12: Multimodal demo evidence and replay scorecards
- Phase 13: Data flywheel episode export
- Phase 14: Shift-level supervisor and bounded autonomy
- Phase 15: Multi-visitor participant and session routing
- Phase 16: Operator handoff and incident workflow
- Phase 17: Venue operations packs and site-driven behavior
- Phase 18: Pilot operations measurement and day-in-the-life evidence
- Phase 19: Checkpoint review and stabilization
- Phase 20: Desktop-first embodiment refactor

## Phase Template

Copy this template when appending a new phase:

```md
## Phase X - Title

### Goal
- What problem this phase was meant to solve

### What Was Completed
- Main features or systems added

### What Changed In The Repo
- Important files, modules, or endpoints that changed

### Why These Decisions Were Made
- Architectural reasons
- Product or demo reasons
- Safety or operational reasons

### What A Beginner Should Understand
- The simplest correct explanation of what this phase means

### Validation At The Time
- Commands or tests that mattered for this phase

### What Stayed Deferred
- Important limits that were intentionally not solved yet
```

## Phase 0 - Architecture Intent And Simulation-First Startup

### Goal

- lock the core product shape before final hardware arrived
- keep the Mac brain / Jetson edge split clear from the beginning
- make pre-hardware progress possible

### What Was Completed

- the initial repository structure
- the software-first robotics direction
- the venue-guide product wedge
- the simulation-first workflow expectation

### What Changed In The Repo

- initial docs and repo structure around `brain`, `edge`, `shared`, `sim`, and `tests`

### Why These Decisions Were Made

- the team needed to build product value before the physical robot was complete
- keeping the Mac and Jetson responsibilities separate reduces future rewrite risk
- early simulation makes the investor story measurable and repeatable

### What A Beginner Should Understand

Blink-AI was never meant to be “just a chatbot in a robot shell.”
From the start, it was designed as a split system where the nearby Mac handles intelligence and the robot-side Jetson handles safe device behavior.

### Validation At The Time

- basic importability and service startup

### What Stayed Deferred

- real hardware drivers
- production operations
- live voice transport

## Phase 1 - Shared Contracts And Basic Brain/Edge Services

### Goal

- create a stable protocol between brain and edge
- stand up the first real services
- prove simple end-to-end flow through a fake robot

### What Was Completed

- shared Pydantic contracts for events, commands, telemetry, acknowledgements, sessions, and traces
- FastAPI brain service
- FastAPI edge service
- fake robot state and command handling
- safety rejection for unsupported movement

### What Changed In The Repo

- `src/embodied_stack/shared/`
- `src/embodied_stack/brain/`
- `src/embodied_stack/edge/`
- starter tests and scenario runner

### Why These Decisions Were Made

- shared contracts reduce ambiguity between services
- a fake robot path lets the team test command behavior immediately
- safety rejection needed to exist before richer behavior was added

### What A Beginner Should Understand

This phase made Blink-AI a real distributed application instead of a loose idea.
The brain and edge could already talk through typed events and simple robot commands.

### Validation At The Time

- service `/health` endpoints
- scenario runner
- tests for command safety and basic API behavior

### What Stayed Deferred

- real memory
- knowledge tools
- operator console
- voice

## Phase 2 - Real Brain Platform With Memory And Community Tools

### Goal

- turn the brain into the actual application center of gravity
- support believable venue-guide interactions
- keep the offline fallback path intact

### What Was Completed

- session management
- world state tracking
- structured command batches
- per-session memory
- optional user memory
- operator notes
- FAQ, event, wayfinding, and escalation tools
- local persistence
- reasoning traces and logs

### What Changed In The Repo

- the brain orchestrator
- memory store
- tool layer
- trace and world-state endpoints

### Why These Decisions Were Made

- investor credibility comes from continuity, not one-shot answers
- venue-guide use cases need local knowledge, not generic chat only
- separating reasoning traces from public robot responses keeps the edge contract clean

### What A Beginner Should Understand

After this phase, Blink-AI could remember what was happening in a conversation and use local community knowledge instead of only replying with generic fallback text.

### Validation At The Time

- seeded scenarios
- session and memory tests
- no-API-key fallback behavior

### What Stayed Deferred

- live operator console
- realistic voice I/O
- stronger deployment tooling

## Phase 3 - Voice Abstractions And Replayable Demo Scenarios

### Goal

- add a real voice-oriented architecture without requiring final hardware
- make demo paths replayable and inspectable

### What Was Completed

- voice pipeline abstraction
- stub voice path
- provider fallback scaffold
- richer scenario definitions
- replay-friendly demo orchestration hooks

### What Changed In The Repo

- voice request/response contracts
- voice pipeline code
- expanded scenario and replay logic

### Why These Decisions Were Made

- the project needed voice-ready architecture before the final microphone and speaker path existed
- replayable scenarios are better for demos and regressions than one-off manual scripts

### What A Beginner Should Understand

This phase did not magically create perfect live speech.
It created the structure needed so future speech input and output could still land in the same session, memory, and trace system.

### Validation At The Time

- voice-turn API tests
- scenario replay tests

### What Stayed Deferred

- real browser/operator surface
- strong demo-day observability
- real microphone transport

## Phase 4 - Operator Console And Investor Demo Flow

### Goal

- give operators one place to run and inspect the demo
- make Blink-AI feel like a product instead of a collection of APIs

### What Was Completed

- browser-based operator console
- transcript view
- session list
- world state view
- telemetry view
- command history view
- trace summary view
- investor scene buttons
- safe-idle controls

### What Changed In The Repo

- console service
- browser UI assets
- operator APIs
- investor scene definitions

### Why These Decisions Were Made

- non-technical operators need a single control surface
- investor demos are stronger when status, traces, and recovery controls are visible
- the console had to drive the real backend paths, not a separate fake UI path

### What A Beginner Should Understand

This is the phase where Blink-AI started to feel like a real embodied AI product in a demo setting.
Operators could watch what the system was doing, not just hope it was working.

### Validation At The Time

- operator API tests
- scene replay tests

### What Stayed Deferred

- stronger regression scoring
- real multi-process ops workflow
- local auth and operational safety

## Phase 5 - Evals, Observability, And Demo Evidence Packs

### Goal

- make demo performance measurable
- catch regressions early
- produce exportable evidence after demo runs

### What Was Completed

- demo run reports
- structured latency and outcome fields
- regression eval fixtures
- demo-check suite
- local artifact bundles with summaries, traces, telemetry, and command history

### What Changed In The Repo

- demo coordinator
- report storage
- demo checks
- regression tests

### Why These Decisions Were Made

- investor credibility improves when results are repeatable and scored
- local evidence packs are simpler and more honest than a heavy observability platform
- the team needed to detect regressions in greetings, wayfinding, escalation, and safe fallback behavior

### What A Beginner Should Understand

Blink-AI stopped being “demo magic” here.
The main demo paths became measurable, replayable, and exportable.

### Validation At The Time

- `demo-checks`
- report bundle generation
- eval and regression tests

### What Stayed Deferred

- stronger operational tooling
- local auth
- real tethered deployment defaults

## Phase 6 - Provider-Backed Dialogue And Live Local Interaction Loop

### Goal

- add a more realistic hosted dialogue backend
- make the live demo feel more embodied than typed-only interaction

### What Was Completed

- provider-backed GRSai dialogue backend
- grounded prompt construction using tools, session topic, operator notes, and remembered user identity
- browser microphone path using browser speech recognition
- macOS `say` speech output option
- visible live voice states such as listening, transcribing, thinking, and speaking

### What Changed In The Repo

- dialogue engine factory and provider adapter
- voice runtime code
- console controls for browser-live modes

### Why These Decisions Were Made

- provider-backed replies improved realism for Mac-brain demos
- the system still needed a strict offline fallback
- using browser speech recognition avoided heavy new dependencies while the real hardware path remained unfinished

### What A Beginner Should Understand

This phase made Blink-AI feel more like a live embodied assistant, but it still stayed honest:

- typed input still works
- the rule-based fallback still works
- browser voice is a practical demo path, not a claim of final robot autonomy

### Validation At The Time

- dialogue backend tests
- live voice path tests
- demo checks

### What Stayed Deferred

- production-grade realtime STT/TTS
- real robot audio hardware
- stronger multi-process operations

## Phase 7 - Multi-Process Tethered Path And Edge Hardware Landing Zone

### Goal

- make the real HTTP brain↔edge path first-class
- turn the edge into a credible landing zone for future Jetson hardware adapters

### What Was Completed

- hardened HTTP brain↔edge gateway with timeout, retry, and failure classification
- duplicate-safe command handling via `command_id`
- separate-process tethered smoke path
- explicit edge adapter boundaries for actuators, inputs, and monitors
- Jetson-shaped simulated profile
- honest unwired Jetson landing-zone profile

### What Changed In The Repo

- HTTP edge gateway behavior
- tethered launcher/smoke helper
- edge adapter model
- edge driver profiles and readiness semantics

### Why These Decisions Were Made

- the project needed a believable deployment path beyond in-process helpers
- future hardware work is easier when adapter boundaries are already explicit
- the same brain protocol should survive the jump from fake robot to real robot

### What A Beginner Should Understand

The important idea is that the edge is no longer “just a stub.”
It now has real slots where future hardware code can be plugged in, while the brain protocol stays stable.

### Validation At The Time

- HTTP-path smoke tests
- edge profile tests
- duplicate command tests

### What Stayed Deferred

- real GPIO, serial, or hardware drivers
- production network security
- stronger operator auth and launch tooling

## Phase 8 - Operational Tooling, Auth, And Demo-Day Safety

### Goal

- make the tethered demo stack safer, easier to launch, and easier to recover
- improve local secrets hygiene
- make operational readiness obvious

### What Was Completed

- local-first operator auth for the console and operator/demo control APIs
- login/logout/status endpoints for operator auth
- protected console login page
- brain and edge `/ready` endpoints
- one-command demo stack launch with `make demo-up`
- `make demo-status` and `make demo-reset`
- predictable runtime artifact directory for the launched stack
- stronger secrets hygiene and tracked-key cleanup

### What Changed In The Repo

- local operator auth manager
- brain auth and readiness wiring
- edge readiness endpoint
- tethered launch/status/reset tooling
- docs and repo ignores for secret handling

### Why These Decisions Were Made

- open control surfaces are not credible for real demos
- operators need a reliable startup and recovery path, not just a set of manual commands
- local runtime metadata is a safer pattern than tracked plaintext secrets
- `/health` alone is too weak for demo-day operations; `/ready` should show whether the current stack is actually usable

### What A Beginner Should Understand

This phase did not try to build enterprise security.
It added practical local safety:

- the control surface is no longer wide open
- the demo stack can be launched and reset in a repeatable way
- readiness now means more than “the process started”

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`

### What Stayed Deferred

- multi-user auth and authorization
- TLS and production network hardening
- production-grade secrets management
- real hardware supervision and recovery on the final robot

## Phase 9 - Multimodal Perception And Scene-Grounded Demo Inputs

### Goal

- make Blink-AI perception-grounded before final robot hardware arrives
- keep perception on the Mac brain instead of drifting into Jetson business logic
- add honest scene understanding inputs without breaking the no-camera fallback

### What Was Completed

- a new `PerceptionProvider` abstraction with:
  - `stub`
  - `manual_annotations`
  - `browser_snapshot`
  - `video_file_replay`
  - `multimodal_llm`
- structured perception observations, events, confidence, source-frame metadata, timestamps, and session linkage
- a perception event bus that publishes:
  - `person_visible`
  - `person_left`
  - `people_count_changed`
  - `engagement_estimate_changed`
  - `visible_text_detected`
  - `named_object_detected`
  - `location_anchor_detected`
  - `scene_summary_updated`
- endpoints for snapshot submission, fixture replay, latest perception lookup, perception history, and fixture catalog
- operator-console support for:
  - camera snapshot capture
  - local image submission
  - manual annotations
  - built-in perception fixture replay
  - latest structured perception output and history
- prompt grounding and rule-based replies that can now admit limited visual awareness honestly

### What Changed In The Repo

- shared perception contracts were added to `src/embodied_stack/shared/`
- the brain gained a new perception runtime module and storage/history support
- the browser console gained new perception controls and visibility panels
- local replay fixtures were added under `src/embodied_stack/demo/data/`
- docs and env examples were updated to describe the new setup

### Why These Decisions Were Made

- the team needed a real perception-shaped layer before final hardware, but it had to stay inspectable and replayable
- keeping perception on the Mac preserves the architecture rule that the Jetson should stay deterministic and thin
- using structured observation and event contracts now reduces future migration work when USB, RTSP, or Jetson camera bridges arrive later
- adding manual and fixture-driven modes keeps the demo usable even when no live multimodal provider is configured

### What A Beginner Should Understand

Blink-AI can now accept camera-like scene inputs, but it still stays honest about what it actually knows.

If a real scene-analysis provider is not available, the system does not pretend it recognized a person or read a sign.
Instead, it records limited awareness, keeps provenance visible, and falls back to manual annotations or replay fixtures.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`

### What Stayed Deferred

- real USB / RTSP / Jetson camera transport
- production multimodal provider tuning
- face recognition, identity recognition, and any unsupported physical claims
- on-robot perception sensors and final hardware calibration

## Phase 10 - World Model And Social Interaction Executive

### Goal

- turn perception and session state into embodied behavior instead of stopping at structured observations
- make social interaction policy visible, deterministic, and replayable
- help Blink-AI feel like an embodied guide before final hardware exists

### What Was Completed

- a structured embodied world model that tracks:
  - active participants in view
  - likely current speaker and likely active session user
  - engagement state
  - visual anchors
  - recent visible text
  - recent named objects
  - current attention target
  - limited-awareness state
  - confidence and time-to-live on ephemeral scene state
- a deterministic `InteractionExecutive` that now decides when to:
  - greet automatically
  - suppress repeated greetings
  - ask a clarifying question
  - keep listening instead of replying
  - shorten replies when engagement is dropping
  - escalate accessibility-sensitive requests to a human
  - stop speech on interruption
  - preserve honest degraded behavior when perception is limited
- world-model and executive-decision visibility in the operator console
- new brain endpoints for:
  - `GET /api/world-model`
  - `GET /api/executive/decisions`
- regression tests for greeting, greeting suppression, interruption, disengagement-aware reply shaping, escalation, and honest limited-awareness fallback

### What Changed In The Repo

- shared contracts gained embodied world-model and executive-decision models
- the brain gained:
  - `world_model.py`
  - `executive.py`
  - orchestrator wiring that updates the world model on each event and records executive decisions in traces
- the console snapshot now includes:
  - `world_model`
  - `executive_decisions`
- the browser console gained visible world-model and executive-decision panels
- docs and protocol notes were updated to describe the new state and endpoints

### Why These Decisions Were Made

- perception by itself does not make the robot feel embodied; the system needed a bridge from “what is seen” to “what should happen now”
- the team did not want social behavior to disappear into prompt text, because investor and operator trust depends on inspectable policy
- a world model with TTL and confidence prevents stale scene observations from silently becoming permanent truth
- interruption, engagement, and escalation are product-critical behaviors for a public-facing guide robot, so they needed deterministic coverage before final hardware

### What A Beginner Should Understand

Before this phase, Blink-AI could see structured scene inputs and answer questions.
After this phase, it can also use that information to behave more like a real social robot.

That does not mean the robot suddenly has magical autonomy.
It means there is now an explicit control layer that decides things like:

- “someone approached, greet them”
- “I just greeted them, do not spam the greeting again”
- “the person interrupted me, stop current speech”
- “engagement is dropping, keep the answer short”
- “this is an accessibility request, get a human involved”

The important point is that these decisions are inspectable in traces and the operator console.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`
- `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`

### What Stayed Deferred

- real person tracking and turn-taking sensors on final hardware
- microphone-array or beamforming logic
- physical gaze, body orientation, or locomotion behaviors
- final tuning against a real camera stack and robot acoustics

## Phase 11 - Venue Knowledge Packs And Perception-Grounded Venue Intelligence

### Goal

- move Blink-AI beyond a seeded script demo and toward a real pilot-site knowledge workflow
- let imported venue data and live scene context work together in one grounded answer path
- keep uncertainty obvious when a venue fact or perception cue is missing

### What Was Completed

- a new venue-knowledge layer that can ingest:
  - FAQ files in JSON or YAML
  - event schedules in CSV or JSON
  - markdown venue docs
  - plain-text room lists
  - plain-text staff contacts
  - optional ICS calendar files
- a sample pilot-site pack under `pilot_site/demo_community_center/`
- updated knowledge tools that now use:
  - imported venue data first
  - live world-model and perception context for direction grounding
  - seeded Python data only as a fallback path
- prompt grounding that now includes imported venue context alongside tool results, world model, operator notes, remembered user facts, and embodiment limits
- honest insufficiency handling for:
  - unknown rooms
  - missing schedules
  - conflicting venue directions
  - limited visual grounding

### What Changed In The Repo

- the brain gained `venue_knowledge.py`
- `tools.py` now wraps venue-pack retrieval plus the older seeded fallback
- the sample pilot content pack was added under `pilot_site/`
- env/config support was added for `VENUE_CONTENT_DIR`
- tests were added for ingestion, venue answers, perception-grounded directions, conflict handling, and fallback behavior

### Why These Decisions Were Made

- investor confidence improves when the robot can operate from a real site pack instead of only from developer-seeded constants
- a file-backed venue pack reduces pilot setup friction and makes knowledge updates a content operation instead of an engineering change
- keeping the tool outputs structured and source-referenced makes the system easier to debug and safer under uncertainty
- preserving the seeded fallback keeps local development stable even when a pilot-site pack is incomplete

### What A Beginner Should Understand

Before this phase, Blink-AI mainly answered from code-defined demo content.
After this phase, the brain can load a site pack from files and answer from that imported venue knowledge.

That means a future pilot can be onboarded by creating content files like:

- venue FAQ
- event schedule
- room list
- staff contacts
- operational notes

The robot can then combine those files with current perception and the world model.
For example: it can repeat directions and mention a visible sign only when that sign is actually grounded.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`

### What Stayed Deferred

- richer semantic search over large venue document sets
- external CMS sync
- recurrent ICS expansion and more advanced calendar semantics
- production operator tools for editing venue packs live

## Phase 12 - Multimodal Demo Evidence And Replay Scorecards

### Goal

- prove that Blink-AI’s multimodal and socially-aware behaviors are replayable instead of anecdotal
- make investor demos inspectable at the frame, world-model, executive, and action-selection layers
- keep all of that local, deterministic in structure, and easy to export

### What Was Completed

- new multimodal investor scenes for:
  - approach and greet
  - visible-sign reading
  - remembered person context
  - disengagement-aware shorter replies
  - confusion plus accessibility escalation
  - honest perception-unavailable fallback
- replay support for:
  - single-frame image-style fixtures
  - short local clip-style fixtures
  - manual console-triggered perception snapshots
- richer demo bundles that now include:
  - perception snapshots
  - world-model transitions
  - executive decisions
  - final grounding sources
  - phase-level latency breakdowns
- a dedicated `multimodal-demo-checks` command and matching `make multimodal-demo-checks` target
- operator-console replay inspection for:
  - frame or clip source
  - extracted scene facts
  - engagement timeline
  - final chosen action
  - scene scorecard

### What Changed In The Repo

- shared contracts gained:
  - latency-breakdown records
  - grounding-source records
  - world-model transition records
  - engagement timeline points
  - scene scorecards and final-action records
- the operator console service and browser UI now expose replay-focused multimodal evidence
- new perception fixture files were added under `src/embodied_stack/demo/data/`
- a new `src/embodied_stack/demo/multimodal_checks.py` suite was added
- demo report bundles now persist richer multimodal artifacts

### Why These Decisions Were Made

- investor trust improves when the team can show the exact frame or clip source behind a behavior instead of narrating “the AI noticed something”
- future model and data work needs structured local evidence, not just pass/fail anecdotes
- keeping the scorecards local and file-backed avoids turning demo validation into a cloud observability project
- phase-level latencies make it easier to diagnose whether a slowdown came from perception, tools, dialogue, or executive policy

### What A Beginner Should Understand

Before this phase, Blink-AI could already demo perception, world modeling, and social policy.
After this phase, the project can also prove those behaviors happened in a repeatable way.

That means a demo operator can now point to:

- the source frame or replay clip
- the extracted scene facts
- the engagement timeline
- the final chosen robot action
- a scorecard that says whether the scene met expectations

This is a product-quality demo improvement, not a robotics-hardware change.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.multimodal_checks`

### What Stayed Deferred

- live camera calibration on final robot hardware
- physically mounted microphones, speakers, and embodied timing in the final enclosure
- larger-scale multimodal dataset management and offline evaluation workflows

## Phase 13 - Data Flywheel Episode Export

### Goal

- turn demo runs and live sessions into reusable multimodal episode assets
- keep the export local, explicit, and versioned so future training and eval work has clean source material
- add a practical bridge from operator demos to later dataset pipelines without pretending the repo is already a full ML platform

### What Was Completed

- a versioned Blink-native episode schema was added for:
  - session metadata
  - transcript entries
  - tool calls
  - perception snapshots
  - world-model transitions
  - executive decisions
  - emitted commands
  - acknowledgements
  - telemetry
  - grounding sources
  - asset references
  - annotation-ready labels
- a new exporter was added that can export:
  - a demo run
  - a live session
- append-only episode bundles now write under `runtime/episodes/<episode_id>/`
- the operator console now has an episode-export browser with:
  - export current session
  - export latest demo run
  - inspect exported episode JSON
- run report bundles now also persist `sessions.json` so later exports can reconstruct transcript-bearing session data from a stored demo run

### What Changed In The Repo

- shared contracts gained episode export request, summary, detail, manifest, asset, telemetry, acknowledgement, and annotation-label models
- a new `src/embodied_stack/demo/episodes.py` module was added for:
  - episode export
  - local episode storage
  - CLI inspection
- the brain app now exposes operator endpoints for:
  - listing episodes
  - fetching an episode
  - exporting a session episode
  - exporting a demo-run episode
- the operator console browser UI now includes a lightweight episode browser and inspector
- docs now explain how the Blink-native episode format could later map into LeRobot-style or other training pipelines

### Why These Decisions Were Made

- high-quality robot data is easier to build if the export format is explicit early, before ad hoc artifacts sprawl
- append-only local bundles are safer and simpler than inventing a dataset service before the product loop is stable
- versioning and manifests reduce future migration pain when the team eventually changes what an episode contains
- annotation-ready labels let today’s demos become tomorrow’s eval and training review queue instead of staying trapped as one-off reports

### What A Beginner Should Understand

Before this phase, Blink-AI already produced good demo evidence.
After this phase, it can also package that evidence into a reusable multimodal episode.

That matters because future learning work usually needs one clean unit that contains:

- what the user said
- what the robot perceived
- what tools and policies fired
- what the robot did
- whether the behavior looked correct

Blink-AI now has that bridge, even though it does not yet have a full training platform.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.episodes list`

### What Stayed Deferred

- dataset deduplication and curation workflows
- external labeling services or web annotation tooling
- format-specific exporters for LeRobot, RLDS, or other downstream pipelines
- privacy policy and redaction workflows beyond the current local export hooks

## Phase 14 - Shift-Level Supervisor And Bounded Autonomy

### Goal

- make Blink-AI feel like a persistent venue agent instead of a single-turn demo
- add explicit long-horizon operating state above the interaction executive
- keep proactive behavior bounded, deterministic, and reviewable

### What Was Completed

- a shift-level supervisor above the existing interaction executive
- explicit operating states such as:
  - `booting`
  - `ready_idle`
  - `attracting_attention`
  - `assisting`
  - `waiting_for_follow_up`
  - `operator_handoff_pending`
  - `degraded`
  - `safe_idle`
  - `quiet_hours`
  - `closing`
- state transitions driven by:
  - perception and person presence
  - recent interaction history
  - venue hours
  - low battery and degraded transport
  - operator override
  - inactivity timers
- a periodic autonomy tick so the brain can make small proactive decisions even when no new speech turn arrives
- trace, report, and operator-console visibility for shift state, timers, transitions, and reason codes

### What Changed In The Repo

- the brain gained a dedicated shift-supervisor runtime and background tick path
- shared contracts gained shift-state, timer, and transition models
- the operator console gained visible shift state and transition history
- report bundles started storing shift-transition artifacts

### Why These Decisions Were Made

- a real venue robot must explain why it is idle, proactive, degraded, or closing
- proactive behavior should not be hidden inside LLM prompts
- schedule-aware and degraded-state behavior is easier to trust when it is explicit and inspectable
- keeping autonomy in the Mac brain preserves the architecture rule that the Jetson should stay simple

### What A Beginner Should Understand

Before this phase, Blink-AI mostly reacted turn by turn.
After this phase, it can also manage its whole shift.

That means the system can now say, in effect:

- “I just booted”
- “I am ready and waiting”
- “someone is here, I can greet them”
- “I am waiting for a follow-up”
- “the venue is closing”
- “transport or battery is degraded, so I am holding safe idle”

Those are explicit software states, not hidden assumptions.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.multimodal_checks`

### What Stayed Deferred

- richer long-horizon venue scheduling logic
- more advanced proactive behavior across a whole day
- real hardware-backed autonomous embodiment beyond safe, bounded prompts and state changes

## Phase 15 - Multi-Visitor Participant And Session Routing

### Goal

- stop Blink-AI from feeling single-user only
- route speech turns and perception updates to the most likely active visitor
- keep queueing simple, honest, and deterministic when multiple people appear or interrupt

### What Was Completed

- a participant/session router that can:
  - associate speech and perception with likely active participants
  - resume sessions for returning likely participants within a bounded window
  - mark sessions as active, paused, handed off, or complete
- explicit turn-taking rules for:
  - one active speaker at a time
  - interruption handling
  - crowd mode vs one-on-one mode
  - polite reorientation when multiple people speak
- queue and attention policy for:
  - first-visible or first-speaker default ownership
  - active-speaker retention windows
  - short wait prompts for secondary visitors
  - accessibility and escalation priority
- operator-console visibility for:
  - active participant
  - queued participants
  - session-to-participant mapping
  - wait timing and last-seen timing

### What Changed In The Repo

- the brain gained a participant-router runtime ahead of the interaction executive
- shared contracts gained likely-participant bindings, queue records, and routing snapshots
- session and world-model records gained participant-routing fields
- traces and operator snapshots started exposing routing state directly

### Why These Decisions Were Made

- public venue interaction rarely happens one person at a time
- the team needed bounded continuity for returning visitors without making fake identity claims
- queue behavior should be inspectable and easy for operators to understand
- “likely participant” semantics are safer and more honest than pretending the robot knows who someone is

### What A Beginner Should Understand

Blink-AI still does not do face recognition or real identity tracking.
Instead, it keeps temporary “likely participant” handles and uses those to make simple decisions like:

- “I am currently serving this person”
- “that second person is waiting”
- “this looks like the same likely participant who just came back”
- “this handed-off visitor should stay prioritized”

That is enough to make the system feel much more realistic in a small crowd.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`

### What Stayed Deferred

- any real identity resolution
- face recognition
- richer crowd-behavior policy for large groups
- physical body-orientation and locomotion behavior tied to multi-visitor attention

## Phase 16 - Operator Handoff And Incident Workflow

### Goal

- make escalation operationally real after Blink-AI decides to hand off to a human
- replace the old “I’ll get someone” path with auditable local incident objects
- give operators and staff a clean workflow for acknowledgment, assignment, notes, and resolution

### What Was Completed

- a structured incident model with:
  - ticket id
  - session id
  - participant summary
  - reason category
  - urgency
  - suggested staff contact
  - current status
  - notes
  - timestamps
- automatic ticket creation when the executive chooses a human handoff path
- venue-aware handoff suggestions that can reference:
  - staff contacts
  - desk locations
  - operating notes
  - event-linked staff context when available
- operator APIs and console controls to:
  - view open and closed tickets
  - acknowledge a ticket
  - assign a ticket
  - attach notes
  - mark resolution outcome
- robot-side status-aware replies for:
  - pending handoff
  - accepted or assigned handoff
  - resolved handoff
  - unavailable operator path
- incident timelines in reports and episode exports

### What Changed In The Repo

- the brain gained a dedicated `IncidentWorkflow`
- memory persistence now stores tickets and timeline entries
- shared contracts gained incident request, response, status, and timeline models
- the operator console gained incident panels and controls
- demo reports and episode exports gained `incidents.json` and `incident_timeline.json`

### Why These Decisions Were Made

- escalation is not credible if it stops at a session flag
- pilot operations need visible state transitions and accountability
- local-first tickets are enough for the current stage and avoid premature external dependencies
- status-specific robot responses keep the handoff behavior honest and inspectable

### What A Beginner Should Understand

Before this phase, Blink-AI could decide that a human should help.
After this phase, it can also manage what happens next.

That means the system now has a real local record of the handoff:

- who the request is for
- why it was escalated
- who should probably respond
- whether someone acknowledged it
- whether it was assigned
- whether it was resolved or no operator was available

This is a major step from “demo escalation” toward “deployable pilot workflow.”

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`
- `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`

### What Stayed Deferred

- external ticketing-system integration
- paging, SMS, email, or other outbound staff notification channels
- deeper staff scheduling logic
- production multi-operator workflows across many venues

## Phase 17 - Venue Operations Packs And Site-Driven Behavior

### Goal

- move Blink-AI from venue knowledge into venue operations
- make pilot-site packs drive scheduling and policy, not just answers
- let different venues behave differently without code forks

### What Was Completed

- the pilot-site schema gained a structured `operations` block for:
  - opening hours
  - quiet hours
  - closing windows
  - proactive greeting policy
  - announcement policy
  - escalation policy overrides
  - accessibility notes
  - fallback instructions
- the venue loader now validates site operations settings and fails fast on broken references such as missing staff-contact keys
- the shift supervisor now uses site operations for:
  - opening prompts
  - closing prompts
  - event-start reminders
  - venue-specific proactive suggestions
  - quiet-hours suppression
  - site-specific degraded and safe-idle fallback wording
- the executive and incident workflow now use site policy for:
  - greeting wording
  - escalation keyword overrides
  - preferred staff contact mapping
  - operator-unavailable fallback wording
- the operator snapshot and world state now expose the loaded venue operations pack and the next scheduled prompt
- a second pilot-site pack was added so the repo has two real personalities:
  - community center
  - library branch

### What Changed In The Repo

- shared contracts gained venue-operations models
- `VenueKnowledge` now loads and validates site operations
- `ShiftSupervisor` now computes bounded scheduled prompts from site policy and event timing
- `InteractionExecutive` and `IncidentWorkflow` now honor site-specific greeting and escalation rules
- the operator console now receives venue-operations state in its snapshot data
- `pilot_site/README.md` now explains how to author an operations-driven pack

### Why These Decisions Were Made

- pilot rollout should become content and policy work, not per-site code edits
- long-horizon venue behavior must stay deterministic and inspectable
- site-specific operations are a real deployment concern, not a prompt tweak
- validation matters because bad policy data is as dangerous as bad code when it changes robot behavior

### What A Beginner Should Understand

Before this phase, a pilot-site pack mostly answered questions like:

- what rooms exist
- what events are on the calendar
- who works here

After this phase, the same pack also controls how Blink-AI behaves in that venue.

That means a community center and a library can now share one codebase while still feeling operationally different:

- the community center can greet more openly and announce upcoming programs
- the library can keep quieter hours, use more restrained prompts, and suppress outreach during study windows

### Validation At The Time

- `uv run pytest`

### What Stayed Deferred

- multi-day staff rostering or shift assignment logic
- external calendar or ticketing integrations
- richer operator UI for editing site policy live instead of loading it from files

## Phase 18 - Pilot Operations Measurement And Day-In-The-Life Evidence

### Goal

- measure Blink-AI as a shift-running venue system, not only as isolated demo scenes
- create investor- and pilot-grade evidence for whole-shift behavior
- keep the first measurement layer deterministic, local-first, and replayable

### What Was Completed

- shared contracts gained a pilot-shift report model with:
  - shift metrics
  - score summary
  - step-by-step simulator records
  - artifact-file map
- a new shift-metrics layer now computes:
  - visitors greeted
  - conversations started
  - conversations completed
  - escalations created
  - escalations resolved
  - average response latency
  - time spent degraded
  - safe-idle incidents
  - unanswered-question and fallback frequency
  - perception-limited-awareness rate
- a deterministic JSON-driven day-in-the-life simulator was added for pilot-shift replay
- the built-in community-center pilot day now exercises:
  - opening and after-hours behavior
  - overlapping visitors
  - queued secondary-visitor handling
  - accessibility escalation and operator resolution
  - event-start reminders
  - degraded transport recovery
  - recoverable safe-idle handling
- pilot-shift bundles now write under `runtime/shift_reports/` with:
  - `summary.json`
  - `report.json`
  - `shift_steps.json`
  - `simulation_definition.json`
  - `metrics.csv`
  - score summary
  - sessions, traces, perception, world-model transitions, shift transitions, incidents, incident timeline, command history, telemetry log, and manifest files
- the operator console snapshot now exposes:
  - live shift metrics
  - recent pilot-shift report summaries
- episode export now supports pilot-shift reports, so the new evidence path still feeds the existing data-flywheel bundle format

### What Changed In The Repo

- a new `shift_metrics.py` module was added for deterministic shift aggregation and scoring
- a new `shift_reports.py` module was added for local pilot-shift artifact storage
- a new `shift_simulator.py` module and built-in JSON fixture were added for deterministic day-in-the-life replay
- shared protocol models and API endpoints were extended for shift reports and shift-report episode export
- the operator console browser UI now renders live shift metrics and recent pilot-shift evidence

### Why These Decisions Were Made

- investors and pilot partners need evidence of whole-shift value, not only one-scene demos
- deterministic replay is more useful right now than a heavy analytics stack
- JSON and CSV artifacts are easy to inspect, archive, diff, and export later
- shift evidence only matters if it can still flow into the same review and data pipeline as the rest of the system

### What A Beginner Should Understand

Before this phase, Blink-AI could show:

- what happened in one scenario
- what happened in one live session

After this phase, it can also show what happened across a whole synthetic venue shift.

That means Blink-AI can now answer higher-level questions like:

- how many visitors were greeted
- how many conversations actually finished
- whether escalations were resolved
- how often the system fell back
- how long it spent degraded

This is the point where the project starts producing pilot-style operational evidence, not just demo-style proof.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.multimodal_checks`

### What Stayed Deferred

- real-hardware timing and crowd-behavior validation on the final robot
- long multi-day analytics across many saved shifts
- live dashboards or external BI tooling
- operator-authenticated scheduling of replay jobs from the browser

## Phase 19 - Checkpoint Review And Stabilization

### Goal

Treat the project as having reached a meaningful checkpoint and consolidate it before starting another major feature wave.

### What Was Completed

- a full engineering review was performed across the brain runtime, edge runtime, demo tooling, shared contracts, and project docs
- startup resilience was improved so a malformed local brain store no longer blocks the whole service from booting
- late identity binding now updates user-memory linkage correctly when a session starts anonymous and is identified later
- degraded HTTP safe-idle handling now preserves the real transport failure detail instead of hiding it behind the requested reason
- background shift-autonomy failures now log instead of failing silently
- demo-run, shift-report, and episode listings now skip malformed artifacts instead of breaking operator-facing reads
- a contributor-facing development guide was added
- a checkpoint engineering review document was added as persistent project memory

### What Changed In The Repo

- `brain/memory.py` now quarantines invalid store files and hardens user-memory linking
- `demo/coordinator.py` now reports real edge transport failures during degraded safe-idle handling
- `brain/shift_runner.py` now logs background tick failures
- demo, shift-report, and episode artifact stores were hardened against malformed files
- `Makefile` gained a `validate` target for the default checkpoint validation path
- `README.md` now links directly to the development guide and checkpoint review
- `docs/development_guide.md` and the preserved engineering review under `docs/evolution/2026-03-30_engineering_review.md` were added

### Why These Decisions Were Made

- after a fast feature-building phase, the next biggest risk was hidden fragility, not missing surface area
- investor demos only stay credible if recovery paths, failure visibility, and documentation are handled seriously
- future contributors need a stable mental model of the codebase before more complexity is added
- local-first JSON storage is fine for this phase, but it needed a safer failure mode

### What A Beginner Should Understand

This phase did not try to make Blink-AI look bigger.
It tried to make Blink-AI safer to keep building.

That means the important output was:

- fewer hidden failure modes
- clearer contributor guidance
- preserved engineering memory about the project’s current strengths and debts

This is the kind of phase that makes later feature work faster and less error-prone.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`
- `PYTHONPATH=src uv run python -m embodied_stack.demo.checks`

### What Stayed Deferred

- splitting oversized modules such as `shared/models.py` and `brain/orchestrator.py`
- introducing a more formal structured-logging strategy
- replacing local JSON persistence with a stronger multi-writer store
- real hardware integration beyond the current Jetson landing-zone boundaries

## Phase 20 - Desktop-First Embodiment Refactor

### Goal

Make the desktop runtime the real center of gravity without deleting the future tethered or Jetson path.

### What Was Completed

- a first-class `desktop/` package was added as the default runtime entrypoint
- a first-class `body/` package was added for semantic embodiment, normalized body state, head profiles, and future driver boundaries
- the main app path now runs through the desktop-local embodiment runtime by default instead of assuming the HTTP edge bridge
- runtime modes were expanded to include `desktop_bodyless`, `desktop_virtual_body`, `desktop_serial_body`, `tethered_future`, and `degraded_safe_idle`
- shared contracts were extended with semantic body commands such as `set_expression`, `set_gaze`, `perform_gesture`, `perform_animation`, and `safe_idle`
- config now exposes explicit desktop/runtime/body settings such as runtime mode, model profile, voice profile, camera source, body driver mode, serial port, servo baud, autoscan, and head profile path
- operator/runtime status now surfaces the selected runtime mode, body driver mode, head profile, and desktop-local embodiment state

### What Changed In The Repo

- `src/embodied_stack/desktop/` was added with `app.py`, `runtime.py`, `profiles.py`, and `cli.py`
- `src/embodied_stack/body/` was added with body-state models, profile loading, command compilation, and driver interfaces
- `src/embodied_stack/shared/contracts/` gained `body.py` plus expanded edge and operator contract fields
- `src/embodied_stack/config.py` now defaults to desktop-local runtime settings
- the brain app and orchestrator were updated to use the desktop-local embodiment gateway by default while preserving the optional tethered HTTP path
- targeted runtime and config tests were added for the new modes and compatibility paths

### Why These Decisions Were Made

- the real machine in front of the team today is the MacBook Pro, not a powered full robot body
- desktop-first development keeps perception, voice, memory, and operator tooling productive even when body hardware is absent
- semantic embodiment has to live above servo transport so the brain never learns raw hardware IDs
- preserving the future tethered path behind interfaces is cheaper than forcing every current workflow through it

### What A Beginner Should Understand

Blink-AI is no longer best understood as “a brain that mostly talks to a fake edge.”

It is better understood as:

- a desktop-local runtime that provides the active sensors and voice path
- a brain that owns cognition, memory, knowledge, traces, and policy
- a body layer that owns embodiment semantics
- an optional edge bridge for later transport or Jetson deployment

That is why the default first run is now `embodied_stack.desktop.app`, not the two-process tethered stack.

### Validation At The Time

- `uv run pytest`
- `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`

### What Stayed Deferred

- real powered-body serial bring-up
- richer virtual-body rendering beyond the current semantic state model
- live remote transport beyond the existing tethered compatibility path
- cleanup of remaining historical docs and comments that still mention Jetson-first development
