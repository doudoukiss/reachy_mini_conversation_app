# Architecture

## Product layering

- primary product: a terminal-first, local-first, character-presence companion running on a nearby Mac
- primary surface: `uv run local-companion`
- character presence runtime: the next major product layer, built around a `fast loop / slow loop` split
- relationship runtime: bounded continuity inside the same companion core
- secondary surfaces: browser appliance, the optional `/presence` shell, `/console`, and the Action Center
- Action Plane: slow-loop capability substrate, not product identity
- optional embodiment: bodyless, virtual-body, and serial-head projection of the same companion core
- explicit vertical/demo mode: `venue_demo` for community concierge / guide demos and pilots

## High-level view

```text
+-------------------------------------------------------------------+
|                  PERSON / OPERATOR / VENUE VISITOR                |
+-------------------------------------------------------------------+
                  | speech, touch, presence, operator actions
                  v
+-------------------------------------------------------------------+
|             DESKTOP COMPANION RUNTIME + OPTIONAL EMBODIMENT      |
|-------------------------------------------------------------------|
| Webcam | Microphone | Speaker | Typed fallback | Operator console  |
| Local runtime modes | Virtual body | Serial landing zone          |
+-------------------------------------------------------------------+
                  | simple robot commands / event ingestion
                  v
+-------------------------------------------------------------------+
|                        BLINK-AI BRAIN                             |
|-------------------------------------------------------------------|
| Session API   | World state tracker | Dialogue / voice interfaces |
| Memory store  | Venue knowledge     | Operator console + traces   |
| Perception bus| Perception providers| Snapshot history + fixtures |
| Social exec   | Shift supervisor    | Demo orchestration + reports|
+-------------------------------------------------------------------+
                  |
                  v
+-------------------------------------------------------------------+
|                 BODY SEMANTICS + TRANSPORT                        |
|-------------------------------------------------------------------|
| Expression | Gaze | Gesture | Animation | Virtual preview         |
| Serial body landing zone | Future tethered / Jetson bridge        |
+-------------------------------------------------------------------+
```

## Current deployment profile

- Current active companion runtime host: local MacBook Pro
- Primary user-facing surface: `uv run local-companion`
- Browser appliance, the optional `/presence` shell, and `/console`: secondary operator/control surfaces
- Venue-demo guide behavior: explicit `venue_demo`, not the baseline identity
- Current local model path: optional Ollama on the development MacBook Pro
- Immediate embodiment path: desktop bodyless or desktop virtual body
- Serial-head bench path: optional embodiment lane for future hardware expression, not the product thesis
- Future body transport path: serial head or tethered Jetson bridge
- Intended later scale-up host: nearby Mac Studio for heavier workloads if needed

The embodiment transport boundary stays shared across:

- in-process desktop virtual preview
- serial body driver on the Mac
- future tethered Jetson bridge

That boundary remains semantic and deterministic: apply compiled semantic actions, report transport and servo health, acknowledge outcomes, and fall back to safe idle.

The application layer should behave the same across Mac environments, but the desktop runtime is now the first-class development and demo host instead of a temporary stand-in.
The companion runtime should remain valuable with no body attached; embodiment changes how the system is expressed, not what product Blink-AI is.

## Engineering principle

The important split is now:

- cognition and dialogue
- multimodal sensing
- semantic embodiment
- body transport

Use this product language consistently:

- `fast loop`: low-latency presence behavior
- `slow loop`: Action Plane work, workflows, approvals, and heavier task execution
- `relationship runtime`: bounded continuity rules layered inside the same companion core
- the optional avatar shell is a projection of the fast loop, not a separate planner or chatbot
- the robot head is the same projection layer in physical form, not a second behavior system

The terminal-first fast loop is now modeled explicitly as a presence state machine:

- `idle`
- `listening`
- `acknowledging`
- `thinking_fast`
- `speaking`
- `tool_working`
- `reengaging`
- `degraded`

The fast loop now also has an explicit bounded initiative engine:

- stages: `monitor -> candidate -> infer -> score -> decide -> cooldown`
- decisions: `ignore / suggest / ask / act`
- scoring dimensions: relevance, interruption cost, confidence, risk, recency, and relationship appropriateness
- grounding signals: terminal activity, current presence and voice-loop state, recent session digests and reminders, optional browser/runtime context, watcher state, and fresh semantic scene state when available
- terminal-first control: initiative must stay easy to silence from `local-companion`, and the runtime must expose honest initiative events instead of fake token streaming

The current embodiment projection path is now explicit:

- `CharacterSemanticIntent` is the canonical semantic output of the character runtime
- `CharacterProjectionProfile` chooses downstream sinks: `no_body`, `avatar_only`, `robot_head_only`, or `avatar_and_robot_head`
- the avatar shell, virtual body preview, and serial head all consume that same intent
- live serial projection remains bounded by transport confirmation, saved calibration, coupling validation, and live-motion arm state
- if those gates are not satisfied, the runtime keeps the semantic preview and records a blocked reason instead of inventing successful hardware motion

Current initiative policy is intentionally conservative:

- `suggest` and `ask` are the default proactive surfaces
- `act` is limited to narrow low-risk cases such as bounded reminder follow-up workflow startup
- high-risk or irreversible digital actions remain blocked by Action Plane policy
- operator-sensitive writes still require approval outside explicit operator launches
- no broad autonomous desktop automation is on by default

The future Jetson path stays thin and deterministic, but it is no longer the mandatory center of the day-to-day development loop.

## Brain application layers

### 1. API and session layer
- creates sessions
- ingests embodiment or edge events and voice turns
- protects operator/demo surfaces with lightweight local operator auth
- exposes session inspection, response-mode control, world state, traces, scenario replay, demo runs, and operator-console APIs
- keeps top-level runtime sequencing in `BrainOrchestrator`, with extracted helper logic under `src/embodied_stack/brain/orchestration/`

### 2. Dialogue layer
- profile-driven backend router for text reasoning, vision, embeddings, STT, and TTS
- pluggable dialogue engine interface
- pluggable voice pipeline interface
- speech turns no longer route as a single hidden model call; they pass through an explicit agent runtime that loads instructions, selects a skill, runs hooks, invokes typed tools, and reviews the candidate plan before execution
- live voice runtime interfaces for speech input, STT, TTS, and cancel support
- the fast loop now tracks presence separately from raw speech-device state so the terminal and console can expose honest acknowledgements, slow-loop waiting, speaking, interruption, and reengagement
- native desktop-local microphone capture on the Mac through AVFoundation audio capture plus Apple Speech transcription
- native desktop-local speaker output on the Mac through the local `say` command, with explicit speaker-health visibility
- deterministic rule-based fallback engine
- optional Ollama-backed engine for local development
- optional Ollama vision and embedding backends for local multimodal and retrieval paths
- optional GRSai-backed chat-completions engine for provider-hosted replies
- OpenAI-compatible voice scaffold that falls back to the stub path when unavailable
- typed-input and browser speech-recognition paths retained as compatibility fallbacks instead of the primary live loop
- native desktop-local webcam snapshot capture on the Mac, with fixture replay and browser snapshot compatibility paths still available when needed
- structured perception provider layer for stub, manual annotations, native camera snapshots, browser snapshots, local fixture replay, and optional multimodal-LLM analysis

### 3. Agent runtime layer
- `AgentRuntime` is the explicit speech-turn operating loop inside the brain
- each bounded turn now creates a persisted `RunRecord` under `runtime/agent_os/runs/` and optional `CheckpointRecord` artifacts under `runtime/agent_os/checkpoints/`
- instruction layers are loaded from persistent files and generated memory surfaces:
  - `IDENTITY.md`
  - `SITE_POLICY.md`
  - `BODY_POLICY.md`
  - generated `user_memory`
- `SkillRegistry` now selects explicit first-party skills such as `general_companion_conversation`, `daily_planning`, `observe_and_comment`, `memory_followup`, `safe_degraded_response`, `incident_escalation`, and `self_diagnose_local_runtime`
- `community_concierge` remains available as an explicit venue/demo playbook rather than the default repo identity
- a separate `SubagentRegistry` selects the primary bounded subagent for the turn, such as `dialogue_planner`, `perception_analyst`, `memory_curator`, `safety_reviewer`, `embodiment_planner`, or `operator_handoff_planner`
- `HookRegistry` now covers canonical lifecycle phases such as `before_skill_selection`, `before_tool_call`, `after_tool_result`, `before_reply`, `before_speak`, `after_turn`, `on_failure`, and `on_session_close`, while older names like `before_reply_generation` and `on_provider_failure` remain compatibility aliases
- `AgentToolRegistry` now sits on a richer internal tool protocol where each tool carries version, family, schemas, permission class, latency class, effect class, failure modes, and checkpoint policy metadata
- the Stage 1 tool surface includes read and preview tools such as `device_health_snapshot`, `memory_status`, `system_health`, `search_memory`, `search_venue_knowledge`, `query_calendar`, `query_local_files`, and `body_preview`
- the same protocol also supports effectful or operator-sensitive tools such as `write_memory`, `promote_memory`, `request_operator_help`, `log_incident`, `create_reminder`, `create_note`, `read_local_file`, `draft_calendar_event`, and `require_confirmation`, with checkpointing before and after those calls
- Stage 6 now adds a separate `action_plane/` package for digital side-effect routing, connector descriptors, connector health, deterministic policy, explicit approval resolution, replay, idempotent execution logging, and code-defined workflow orchestration under `runtime/actions/`
- the current Stage A/B connector runtime is centered on `action_plane/connectors/` and formalizes these built-in connectors:
  - `memory_local`
  - `incident_local`
  - `browser_runtime`
  - `reminders_local`
  - `notes_local`
  - `local_files`
  - `calendar_local`
  - `mcp_adapter`
- the currently routed tool surface through that layer is:
  - `write_memory`
  - `promote_memory`
  - `request_operator_help`
  - `log_incident`
  - `browser_task`
  - `create_reminder`
  - `list_reminders`
  - `mark_reminder_done`
  - `create_note`
  - `append_note`
  - `search_notes`
  - `read_local_file`
  - `stage_local_file`
  - `export_local_bundle`
  - `query_calendar`
  - `draft_calendar_event`
- `browser_runtime` is now a bounded Stage 6C browser connector with `disabled`, `stub`, and `playwright` backends, per-session browser state under `runtime/actions/browser/`, comparable browser artifacts, and action-level policy that keeps click, type, and submit behind approval for non-operator invocations
- Stage 6D adds `action_plane/workflows/` as a reentrant step-machine runtime with:
  - code-defined workflow definitions in repo code rather than runtime-authored graphs
  - persisted run state under `runtime/actions/workflows/runs/`
  - trigger dedupe state under `runtime/actions/workflows/trigger_state.json`
  - summary and workflow artifacts under `runtime/actions/workflows/artifacts/`
  - automatic pause on pending approval and explicit resume or retry after approval resolution or rejection
- Stage 6E adds durable Action Plane flywheel exports with:
  - live `blink_action_bundle/v1` sidecar bundles under `runtime/actions/exports/action_bundles/`
  - deterministic action replays under `runtime/actions/exports/action_replays/`
  - bundle linkage back into `blink_episode/v2` through `derived_artifact_files`
  - additive research and benchmark linkage for action bundles, action replays, and action-quality metrics
- Stage 6F adds the operator product layer on top of those Stage 6 internals:
  - a unified `/console` Action Center driven by `GET /api/operator/action-plane/overview`
  - browser preview and bundle or workflow inspection through one shared inspector instead of disconnected Stage 6 subsections
  - `local-companion` `/actions ...` slash commands for approval, history, workflow, connector, and bundle handling inside the interactive loop
  - conservative restart reconciliation that marks uncertain action executions for operator review and pauses dependent workflows with `runtime_restart_review` instead of assuming success
- the current workflow library is:
  - `capture_note_and_reminder`
  - `morning_briefing`
  - `event_lookup_and_open_page`
  - `reminder_due_follow_up`
- workflow steps do not call connectors directly; they reuse the same Action Plane gateway and typed tool front door as normal connector actions
- proactive workflow startup still runs on the existing `ShiftAutonomyRunner` tick, but it is now gated by the explicit initiative engine rather than an unconditional trigger sweep
- Action Plane safety policy still dominates proactive work: proactive local writes stay preview-only, operator-sensitive writes require approval, and irreversible or external high-risk actions remain rejected
- `body_preview`, `body_command`, and `body_safe_idle` still stay on the existing embodiment path; the Action Plane still does not take over body execution
- bounded specialist roles keep responsibilities explicit:
  - perception analyst
  - dialogue planner
  - safety reviewer
  - memory curator
  - embodiment planner
  - operator handoff planner
  - reflection
- candidate reply and action plans are reviewed and can be downgraded before commands are emitted
- the semantic body boundary remains high-level; the planner never writes raw servo bytes or transport packets
- every Action Plane-routed tool call now enriches the existing tool-call record and tool checkpoints with action id, action name, connector id, risk class, approval state, execution status, request hash, idempotency key, and optional workflow run or step linkage

### 4. Memory layer
- per-session transcript and memory facts
- optional user memory keyed by `user_id`
- explicit layered memory surfaces:
  - profile memory through `UserMemoryRecord`
    - explicit companion preferences such as greeting style, planning style, tone bounds, and interaction boundaries
  - episodic memory through compact per-session summaries
    - session digests plus open follow-ups for unresolved thread continuity
  - semantic memory through reusable grounded fact records
- response mode and conversation summary on each session
- richer durable user preferences and interests
- relationship continuity is bounded on purpose: durable profile memory stores only explicit user-stated preferences, while unresolved work should come from reminders, notes, and session digests instead of speculative personality modeling
- operator notes attached to sessions
- local retrieval now composes venue docs, user preferences, prior session summaries, semantic memory, and fresh perception facts
- local embedding-backed semantic retrieval fallback remains available across venue knowledge, operator notes, layered memory, and user memory
- local incident tickets plus auditable incident-timeline persistence
- lightweight JSON persistence in local storage

### 5. Knowledge and tools layer
- venue knowledge ingestion from pilot-site content packs
- venue operations ingestion from the same pilot-site packs so site-specific scheduling and policy stay data-driven
- FAQ retrieval from imported JSON/YAML or markdown-backed content
- event schedule retrieval from imported CSV/JSON/ICS sources
- room and wayfinding retrieval from imported room lists plus live scene context
- operator escalation and staff-contact lookup
- venue-aware handoff suggestions that can reference staff contacts, desk locations, operations notes, and event-linked staff context when available
- seeded Python demo data retained only as a fallback path when imported content is missing

### 6. Trace and observability layer
- public event response includes only reply text, commands, session status, and `trace_id`
- reasoning metadata is stored in trace records, not mixed into the robot-facing response
- world state summarizes current session focus, last commands, pending escalations, and open incident-ticket ids
- traces include latency and outcome fields
- traces now also expose run id, run phase, run status, active instruction layers, active skill, active subagent, typed tool calls, hook executions, checkpoint count, last checkpoint id, specialist-role decisions, validation outcomes, failure state, fallback reason, and replay/resume lineage for the selected turn
- traces and reports now also surface incident-ticket creation plus any incident timeline entries attached to that interaction
- demo runs persist step-by-step reports with end-to-end latency, trace latency, backend used, fallback events, telemetry, command acknowledgements, incident snapshots, and final world state
- pilot-shift reports now aggregate shift-level metrics such as greetings, conversation start/completion, escalation follow-through, degraded duration, fallback frequency, and limited-awareness rate
- pilot evidence stays local-first through JSON and CSV artifacts instead of introducing a database or external observability dependency

### 7. Perception layer
- `PerceptionService` owns structured scene ingestion, latest-snapshot tracking, and perception history
- perception providers run on the Mac brain, not on the Jetson edge
- Stage 2 now makes the cheap watcher path first-class instead of treating it as an ad hoc scene note:
  - `SceneObserverEngine` emits rolling watcher events with presence, rough people count, attention-toward-device estimate, scene-change score, environment estimate, refresh recommendation, and capability limits
  - watcher events are buffered by the always-on supervisor and exposed through the operator snapshot and evidence exports
- browser snapshots, local image uploads, manual annotations, and local fixture replay all normalize into the same structured observation contract
- rich semantic analysis is now explicitly trigger-driven rather than always-on:
  - new arrivals
  - meaningful watcher change
  - explicit visual questions
  - proactive-speech decisions
  - direct skill/tool requests
- every `PerceptionSnapshotRecord` now carries an explicit tier (`watcher` or `semantic`) plus a `trigger_reason`
- semantic provider output now passes through a normalization layer before any durable update:
  - engagement values normalize into a consistent label space
  - raw provider summaries remain in snapshot provenance
  - only normalized typed facts may flow into the world model or grounded dialogue
- the perception event bus publishes typed scene events such as `person_visible`, `people_count_changed`, and `scene_summary_updated`
- every perception result carries confidence, source-frame metadata, timestamps, and optional session linkage
- reply grounding uses only fresh scene facts; stale snapshots are rejected and the system falls back to limited-awareness language instead of replaying old visual claims
- when perception is unavailable or uncertain, Blink-AI records limited awareness instead of inventing scene facts

### 8. World model, participant router, social executive, and shift supervisor layer
- `ParticipantSessionRouter` sits ahead of the interaction executive and keeps a deterministic active-participant plus queue model using bounded `likely_participant_*` handles instead of fake identity claims
- the router applies simple turn-taking rules: one active speaker at a time, first-visible or first-speaker default ownership, bounded active-speaker retention, short wait prompts for secondary visitors, and accessibility/escalation priority
- the router also decides when a likely participant should resume an existing session, pause behind another visitor, stay handed off, or be marked complete after bounded inactivity
- `WorldModelRuntime` now tracks a fuller typed scene state:
  - participants in view
  - likely current speaker
  - engagement state
  - attention target plus rationale
  - recent anchors, visible text, and named objects
  - environment state
  - device-awareness constraints
  - uncertainty markers
  - explicit scene freshness
  - explicit `social_runtime_mode`
- ephemeral scene state carries confidence plus time-to-live semantics so stale visual observations expire instead of becoming durable facts
- watcher-derived facts can drive presence, greeting, and engagement policy, but only semantic-tier facts are treated as strong grounding for text, anchors, or objects
- `InteractionExecutive` applies deterministic embodied policy for auto-greeting, greeting suppression, clarification, interruption, disengagement-aware reply shaping, escalation, and safe idle
- companion-facing behavior categories are explicit in the runtime and skill layer: greeting/re-entry, unresolved-thread follow-up, day planning, observe-and-comment, and emotional tone bounds
- Stage 2 splits immediate situated behavior into explicit policy helpers:
  - `attention_policy.py` owns bounded attention-target construction and rationale
  - `social_runtime.py` maps current state into explicit modes such as `greeting`, `listening`, `speaking`, `follow_up_waiting`, `operator_handoff`, and `degraded_awareness`
- `ShiftSupervisor` sits above the per-interaction executive and keeps Blink-AI in explicit long-lived operating states such as `ready_idle`, `assisting`, `waiting_for_follow_up`, `degraded`, `quiet_hours`, and `closing`
- the supervisor uses bounded policy inputs only: perception presence, recent interaction state, venue hours, quiet-hours windows, closing windows, event schedule, transport/battery health, operator override, and inactivity timers
- proactive follow-up remains bounded, respectful, and inspectable: it should come from explicit reminders, open session-digest threads, or visible operator/supervisor policy rather than implied emotional attachment
- a periodic brain-side autonomy tick lets Blink-AI make short inspectable decisions between speech turns, such as entering attract mode, cooling down outreach, or holding safe idle
- the autonomy tick can also issue bounded site-pack-driven scheduled prompts such as opening prompts, closing prompts, event-start reminders, and venue-specific proactive suggestions
- executive decisions are visible in traces and operator snapshots through explicit decision records and reason codes
- site-pack escalation overrides remain inspectable because keyword rules, fallback messages, and contact mappings are loaded from content, not hidden in prompts
- when the executive chooses a human handoff path, `IncidentWorkflow` converts that decision into a local-first ticket with deterministic category, urgency, suggested staff contact, and status lifecycle instead of leaving the system at a bare session flag
- participant-routing state is visible in world state, the world model, session summaries, and the operator console through explicit active/queued mappings and last-seen or wait timestamps
- shift-state transitions are also visible in traces, reports, world state, and operator snapshots through explicit reason codes and timer snapshots
- LLM replies remain subordinate to this control policy; the model helps with wording, not hidden control logic

### 9. Demo coordination layer
- `DemoCoordinator` resets brain and edge state together
- seeded scenarios now flow through the edge bridge before reaching the brain
- report artifacts are stored locally for repeatable investor review
- each run writes a report bundle with summary, sessions, traces, telemetry log, command history, perception snapshots, world-model transitions, executive decisions, grounding sources, and manifest files
- report bundles now also preserve shift-supervisor transition history plus incident-ticket and incident-timeline artifacts so long-horizon operating behavior and handoff quality can be reviewed after the run
- a dedicated demo-check suite replays the main investor paths and writes a local evidence pack under `runtime/demo_checks/`
- a dedicated multimodal demo-check suite replays perception-grounded and socially-aware scenes with scorecards under `runtime/demo_checks/multimodal/`
- a dedicated always-on local check suite now replays supervisor-state, observer, fallback, interruption, and memory-continuity paths under `runtime/demo_checks/always_on_local/`
- a separate tethered smoke path launches the brain and edge as different processes and validates the real HTTP gateway
- a deterministic day-in-the-life simulator now replays file-driven pilot shifts with arrivals, overlap, escalations, schedule prompts, degraded periods, and recovery
- pilot-shift runs persist a separate evidence bundle under `runtime/shift_reports/` with step logs, metrics CSV, score summary, sessions, traces, transitions, and incident artifacts

### 10. Data flywheel layer
- `MemoryPolicyService` sits in front of durable memory writes and records append-only `MemoryActionRecord` and `MemoryReviewRecord` artifacts for profile, episodic, and semantic memory
- teacher feedback now persists as first-class local records linked to traces, memory items, and exported episodes so correction and review stay inspectable
- `BlinkEpisodeExporter` turns a demo run or a live session into a versioned episode artifact under `runtime/episodes/`
- exported episodes are append-only local bundles, not mutable database rows
- the maintained export schema is now `blink_episode/v2`, with backward read support for older `blink_episode/v1` bundles during transition
- the episode schema keeps transcript, tool calls, perception, world-model transitions, executive decisions, commands, acknowledgements, telemetry, layered memory artifacts, grounding sources, scene facts, run lineage, and annotation-ready labels in one place
- episode exports now also carry incident tickets and incident timelines so operator-handoff quality can be evaluated end to end
- episode bundles now preserve `episodic_memory`, `semantic_memory`, `profile_memory`, `memory_actions`, `memory_reviews`, and `teacher_annotations` artifacts so future retrieval and eval jobs can use the same compact grounding assets the live runtime uses
- live local companion bundles may also preserve `runtime_snapshot.json`, `presence_runtime.json`, `voice_loop.json`, `scene_observer.json`, `trigger_history.json`, and `ollama_runtime.json` so always-on behavior and fallback evidence stay inspectable after a session
- the exporter can now package a pilot-shift report bundle into the same episode format, so day-in-the-life evidence can flow into the existing review and dataset path
- frame or clip provenance is preserved through asset references when perception inputs provided a fixture path, file name, or explicit audio-path hook
- a Stage 5 research bridge now derives `blink_research_bundle/v1` artifacts from `blink_episode/v2` without replacing the episode contract, and writes planner inputs, planner outputs, tool traces, memory actions, labels, and split metadata as separate JSON assets
- the episode manifest and summary now keep `derived_artifact_files` so replay and research exports remain linked back to the canonical local episode bundle
- episode exports may now also write `linked_action_bundles.json` so the canonical episode artifact can reference the live Action Plane work that happened during that session or workflow run
- an episode replay harness under `runtime/replays/` can now replay exported episodes against registered in-process planners such as `agent_os_current` and `deterministic_baseline` without mutating the source artifact
- an Action Plane replay harness under `runtime/actions/exports/action_replays/` now replays `blink_action_bundle/v1` bundles against deterministic stub or dry-run backends without touching live browser or effectful connector paths
- a local benchmark runner under `runtime/demo_checks/benchmarks/` now scores exported episodes on grounded conversation, memory quality, honest uncertainty, safe fallback, and escalation quality without turning pytest into the only eval surface
- the same benchmark runner now also scores research-bridge families such as export validity, planner swap compatibility, replay determinism, annotation completeness, dataset split hygiene, action approval correctness, action idempotency, workflow resume correctness, browser artifact completeness, connector safety policy, proactive action restraint, and action trace completeness
- the current format is intentionally Blink-native and explicit so it can later be mapped into LeRobot-style or other training pipelines without prematurely committing the runtime to a single ML dataset standard

### 11. Operator console layer
- the brain serves a practical browser-based operator console at `/console`
- appliance mode trusts the local browser on localhost, while non-appliance service modes still protect the console and operator-only APIs with a local-first operator token
- the console now includes teacher-mode review flows for episodes, traces, and memory corrections plus browser controls for benchmark runs against exported episodes
- the console now also includes an Action Flywheel panel for recent action bundles, approval completeness, deterministic action replay, linked teacher review, and action-focused benchmark summaries
- the console aggregates sessions, transcript, world state, telemetry, command history, and trace summaries
- operator controls drive the same orchestrator and edge bridge used by the scripted demo paths
- investor scenes provide step-by-step presence, wayfinding, memory, escalation, and safe-fallback sequences
- runtime status now exposes whether the edge path is `in_process` or real `http`, plus degraded transport state when the tether is unhealthy
- runtime status now also exposes the backend profile, selected text or vision or embedding or STT or TTS backends, and per-backend availability or fallback state
- runtime status now also exposes always-on supervisor state, current voice-loop state, scene-observer state, trigger-engine state, last scene-refresh reason, and proactive cooldown or suppression state
- runtime status now also exposes `presence_runtime` so fast-loop state remains visible even when the slow loop is still reasoning or working
- runtime status now also exposes the current `social_runtime_mode`, watcher-buffer count, and the latest semantic refresh reason
- runtime status now also exposes Ollama reachability, requested and active model, warm or cold state, keep-alive policy, and last-success latency for local model backends
- live voice state now exposes listening, transcribing, thinking, speaking, idle, interrupted, failed, and transcript-preview status for the selected session
- the operator snapshot now also exposes explicit microphone, speaker, and camera device-health records for the active desktop-local path
- the operator snapshot now also exposes registered skills, hooks, typed tools, specialist roles, and the latest turn's active skill, tool calls, validation outcomes, hook records, and role decisions
- the operator snapshot now also exposes registered subagents plus the latest run id, run phase, run status, active subagent, checkpoint count, last checkpoint id, failure state, and fallback reason
- operator-only recovery APIs now expose run inspection, checkpoint inspection, replay, and resume flows on top of the existing snapshot and trace surfaces
- operator-only APIs now also expose planner listing, episode replay launching, replay lookup, research-bundle export, and replay-aware benchmark runs
- the console now also exposes current perception mode, camera/image submission, manual annotations, fixture replay, latest structured perception output, and recent perception history
- the console now also exposes the rolling watcher-event buffer, richer perception freshness, tier and trigger metadata, and uncertainty or device-constraint markers for the latest scene state
- the console now also exposes the embodied world model, engagement state, current attention target, current social-runtime mode, environment estimate, and recent executive decisions with reason codes
- the console now also exposes the active participant, queued participants, session-to-participant mapping, and routing reason for multi-visitor handling
- the console now also exposes the current shift-supervisor state, timers, recent transition reasons, and a bounded manual autonomy tick path
- the console now also exposes live shift metrics plus recent pilot-shift report summaries so operators can see shift-level value, not just individual turns
- the console now also exposes the loaded venue operations pack, including proactive greeting settings, quiet-hours windows, and the next scheduled prompt
- the console now also exposes open and closed incident tickets, suggested staff contacts, assignee state, operator notes, and incident timelines with direct acknowledge/assign/resolve controls
- the console replay inspector now exposes frame or clip source, extracted scene facts, engagement timeline, final chosen action, and scene scorecards for multimodal demos
- the console now also exposes exported episode summaries and lets the operator export the current session or latest demo run without leaving the browser

### 12. Always-on local companion runtime
- the Mac-local companion path is now organized around a single supervisor rather than a bounded-turn loop with side threads
- the supervisor owns background scene observation, voice-loop transitions, trigger evaluation, shift/autonomy integration, proactive cooldowns, and evidence collection
- push-to-talk is the primary live-control path in this phase: the observer runs continuously, `/listen` arms one utterance, typed input remains available, and `/interrupt` cancels current speech immediately
- `local-companion` is now personal-first by default on the Mac through `personal_local` context, while story, scene replay, and demo surfaces force `venue_demo`
- scene understanding is explicitly tiered:
  - cheap watcher first, using frame-difference as the required baseline and optional MediaPipe attention hints when installed
  - semantic refresh only when needed for meaningful change, visual questions, stale facts, or grounded proactive speech
- local M4 Pro operation is now a first-class backend preset through `m4_pro_companion`, which prefers Ollama text or vision or embeddings plus Apple Speech STT and macOS `say`
- the local acceptance harness is now `uv run local-companion-doctor`, which probes the actual MBP stack and writes a machine-specific runtime report
- the always-on runtime stays body-optional: `bodyless`, `virtual_body`, and future `serial_body` remain orthogonal embodiment choices, not hidden inside the model preset

## Edge adapter model

The Jetson runtime is no longer treated as one opaque driver object. It is organized into explicit adapter boundaries:

- actuator adapters: speaker trigger, display, LED, head pose
- input adapters: touch, button, presence, transcript relay
- monitor adapters: network, battery, heartbeat

Each adapter boundary has:

- capability declaration in `CapabilityProfile.adapters`
- runtime health in `TelemetrySnapshot.adapter_health`
- a profile-controlled state such as `active`, `simulated`, `unavailable`, `degraded`, or `disabled`

This keeps the edge deterministic while making it obvious which pieces are wired, simulated, or still missing on a future Jetson build.

## Public output contract

The brain returns a structured response for each event:

- `reply_text` for user-facing speech/display
- `commands` for the edge runtime
- `trace_id` for operator inspection
- `status` for session state

Reasoning metadata, tool hits, and memory updates are stored in trace records and fetched separately through logs/traces endpoints.

## Modes

- `desktop_bodyless` - local Mac runtime with no body attached
- `desktop_virtual_body` - local Mac runtime with semantic actions rendered into virtual body state
- `desktop_serial_body` - local Mac runtime with serial-body landing zone enabled
- `tethered_future` - future external body transport such as Jetson or another controller
- `degraded_safe_idle` - low battery, disconnect, or explicit safe stop
- legacy compatibility modes remain available in the edge package for the fake robot and Jetson-shaped profiles

## Key contracts

### From edge to brain
- `person_detected`
- `speech_transcript`
- `touch`
- `button`
- `heartbeat`
- `telemetry`
- `low_battery`
- simulated sensor events routed through the edge bridge
- perception-scene events emitted by the Mac-side perception bus:
- `person_visible`
- `person_left`
- `people_count_changed`
- `engagement_estimate_changed`
  - `visible_text_detected`
  - `named_object_detected`
  - `location_anchor_detected`
  - `scene_summary_updated`

### From brain to embodiment runtime
- `speak`
- `display_text`
- `set_led`
- `set_head_pose`
- `set_expression`
- `set_gaze`
- `perform_gesture`
- `perform_animation`
- `safe_idle`
- `stop`

No high-level planning or community logic should move into the Jetson runtime.
The brain should never need raw servo IDs; semantic body commands are compiled behind the body package.

## Embodied interaction policy

The world model and social executive live entirely on the Mac brain.

The brain can now:

- greet automatically on approach
- suppress repeated greetings within a cooldown window
- issue short attract-mode prompts during bounded idle periods
- stay silent during quiet hours, cooldowns, or repeat-presence windows
- stop current speech when a user interrupts
- ask deterministic clarifying questions for unresolved references
- shorten replies when engagement is dropping
- escalate accessibility-sensitive requests to a human
- convert an escalation decision into a real local incident ticket with status-specific robot replies for pending, acknowledged, resolved, or unavailable handoff states
- force operator handoff or safe idle on explicit supervisor policy
- admit limited situational awareness when perception is missing or degraded

These remain inspectable policy decisions rather than hidden prompt-only behavior.

## Safety model

The edge is responsible for:

- rejecting unsupported commands
- treating `command_id` as an idempotency key so safe HTTP retries do not replay actions
- entering safe idle on explicit stop, low battery, disconnect, or heartbeat timeout
- reporting command acknowledgement clearly
- exposing telemetry history and heartbeat state for operator inspection
- surfacing readiness honestly when a hardware profile is present but actuator or sensor adapters are still unwired

The body compiler and desktop runtime are responsible for:

- clamping normalized semantic pose values before they become hardware targets
- applying head-specific coupling rules for the current expressive 11-servo bust/head
- exposing compiled body frames and virtual preview state for operator inspection
- keeping raw servo IDs and mirrored joint mechanics out of the brain

The brain is responsible for:

- emitting only simple, supported commands
- classifying HTTP transport failures separately from command rejections
- keeping fallback behavior honest and deterministic
- escalating to operators instead of inventing unsupported embodiment
- protecting operator/demo control surfaces without adding cloud auth dependencies

## Simulation strategy

### Tier 1 - desktop-local runtime
Fastest loop, zero body hardware required, and the main validation target right now.
The desktop runtime keeps camera, microphone, speaker, typed fallback, semantic body state, and safe-idle behavior in one local process. The native desktop-local loop is now the first-class live path rather than a browser-dependent assist mode.

### Tier 2 - repo-local fake edge or tethered compatibility path
Same brain service shape, but validated through the edge bridge or a separate HTTP process boundary when you specifically need it.

Perception remains Mac-side in this tier. Camera and fixture inputs are still processed into structured scene events before the brain decides whether to speak or command the edge.

The new `jetson_simulated_io` profile is the pre-hardware bridge between Tier 1 and final hardware: it keeps the Jetson-shaped adapter boundaries while still using simulated adapters so the same brain protocol can be validated before hardware arrives.

### Tier 3 - production landing zone
Move the brain from the development MBP to the Mac Studio without changing the core contracts.

On the edge side, `jetson_landing_zone` is the honest hardware landing zone. Its actuator and sensor boundaries are declared up front, but unwired adapters stay visibly unavailable until a real Jetson implementation fills them in.
