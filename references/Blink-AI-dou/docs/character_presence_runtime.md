# Character Presence Runtime

This document describes the **next major product layer** for Blink-AI after the current Stage 0 through Stage 6 baseline.

The authoritative product definition lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).

Blink-AI is no longer missing a local-first companion, Agent OS, memory substrate, Action Plane, or optional embodiment path. The biggest remaining product gap is **presence**:

- a stable visible identity
- a believable sense of being alive between task turns
- stronger continuity between language, memory, initiative, and expression
- a product surface that feels like a companion, not only a toolkit

## Product Decision

Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.

That means:

- the primary product remains the local-first companion on the Mac
- the primary user surface remains terminal-first `uv run local-companion`
- an optional lightweight avatar or character shell may mirror the same runtime state
- browser appliance, `/console`, Action Center, and voice loops remain secondary surfaces around the same core
- virtual body and serial head remain optional embodiment for the same mind

The character is not a detached mascot. It is a rendering of the same companion runtime.

## Why This Is The Next Major Upgrade

The current repo already has:

- local-first companion runtime
- explicit Agent OS
- world model and social runtime
- layered memory and episode flywheel
- Action Plane and approval substrate
- semantic optional embodiment and serial-head path
- replay, benchmark, and export discipline

What it still does not have is a first-class character presence runtime. The current repo can reason, remember, and act more than it can **feel present**.

## Runtime Shape

The character presence runtime should be implemented as a **fast loop / slow loop** architecture with two supporting loops and three buses.

### Fast loop

The fast loop preserves responsiveness and aliveness.

It drives:

- short acknowledgements
- visible listening, thinking, and speaking state
- backchannels and quick replies
- attention and expression updates

It must stay fast even while slower work is running.

### Slow loop

The slow loop reuses the existing Action Plane, tool routing, planner, browser runtime, workflows, and approvals.

It performs slower work such as:

- world-model refresh
- search and retrieval
- workflow execution
- browser tasks
- approval-aware side effects

### Supporting loops

- `memory loop`
  - decides what to write, summarize, consolidate, or forget after the turn or task
  - keeps profile, episodic, semantic, workflow, and relationship memory distinct
- `proactivity loop`
  - watches context, task state, and cooldowns
  - decides whether to stay silent, suggest, ask, or take a bounded low-risk action
  - must remain rate-limited and explicitly governed

### Buses

- `Interaction Event Bus`
  - text turns, voice turns, screen observations, terminal state, app-focus changes, reminders, workflow updates, and operator overrides
- `Presence State Bus`
  - listening, thinking, speaking, idle, degraded, emotional tone, expression intent, and attention target
- `Action and Approval Bus`
  - typed task requests, approval state, progress narration, completion state, rollback, and task summaries

## Relationship Runtime

The existing [relationship runtime](/Users/sonics/project/Blink-AI/docs/relationship_runtime.md) remains important but is not sufficient on its own.

The relationship runtime governs bounded continuity:

- greeting and re-entry
- unresolved-thread follow-up
- planning style
- tone bounds
- relationship-relevant memory rules

The character presence runtime adds the broader presence layer around it:

- `persona manifest`
  - name, speech style, humor policy, boundaries, initiative policy, values, tone bands, and expression mapping
- `presence state machine`
  - idle, listening, acknowledging, thinking_fast, speaking, tool_working, reengaging, degraded
- `expression intent model`
  - maps dialogue, uncertainty, task progress, and attention into character-facing expression signals
- `initiative policy model`
  - controls whether Blink-AI stays silent, suggests, asks, or takes a bounded low-risk action
- `rendering adapters`
  - terminal, avatar shell, virtual body, and serial head all consume the same character signals

## Scope Discipline

The next stage should **not** attempt to become a universal GUI agent immediately.

The first strong scenario should stay aligned with the current repo shape:

- terminal-first daily companionship
- coding, writing, research, and creator workflows
- browser and document assistance
- explicit optional voice
- lightweight desktop grounding

This means:

- terminal + browser + selected app adapters first
- generic OS-wide desktop control later
- strong suggest and ask behavior first
- broad unattended action later and only with much stronger governance

## Non-Goals

Do not make these the critical path:

- full Live2D or VRM production pipeline on day one
- full-duplex voice perfection before the fast loop is stable
- universal desktop automation across arbitrary macOS apps
- emotional manipulation or fake attachment
- robot-first UI or hardware-first product framing

## Honest Status

Today, the slow-loop substrate is real. The local-first companion, Action Plane, relationship runtime, and optional embodiment path already exist.

A first lightweight browser character shell now mirrors the shared fast-loop state and semantic embodiment mapping, so Blink-AI has an inspectable optional presence surface alongside the terminal.

What remains incomplete is the fuller Stage 7 layer: the explicit persona-manifest layer, richer synchronized expression policy, and broader desktop-grounded character runtime are still in progress rather than complete.

## World-Class Bar

A world-class Stage 7 result means:

- Blink-AI feels like one continuous character across terminal, voice, browser, avatar, and optional robot embodiment
- latency is low enough that the character feels alive
- memory is useful, editable, and bounded
- initiative is helpful, sparse, and predictable
- task execution remains visible, safe, and approval-aware
- terminal-only use remains valid
- the avatar and robot are projections of the same mind, not separate products
