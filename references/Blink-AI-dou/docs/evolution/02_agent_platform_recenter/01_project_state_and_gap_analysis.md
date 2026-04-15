# 01 — Project state and gap analysis

## What is already strong

The current repository is already much more mature than a prototype.

It already has:

- a desktop-first runtime direction
- a semantic body layer
- a virtual body path
- a serial body landing zone
- Feetech protocol encode/decode and calibration tooling
- session memory and operator tooling
- multimodal perception abstractions
- world model and interaction policy layers
- pilot-site knowledge packs
- replay, reports, episode export, and regression tests

This means the next step is **not** a restart.
It is a **re-centering** of the product around the desktop-local embodiment loop.

## Current technical strengths

### 1. Body abstraction is already correct
The `body/` package is the right long-term shape:
- semantic expressions
- gaze targets
- gestures
- animation compiler
- profile-driven mapping from semantics to raw servo targets
- serial transport boundary

This should be preserved.

### 2. Desktop runtime exists, but it is not yet the undisputed center of gravity
The repo already has:
- `desktop/`
- desktop runtime modes
- typed shell
- browser-assisted live paths
- virtual body preview

But the user goal now requires a **first-class native local interaction loop**, not just browser-driven or typed fallback paths.

### 3. The current "intelligence" stack is useful but still too orchestration-light
The repo has:
- dialogue backend abstraction
- perception abstraction
- world model
- social executive
- shift supervisor
- venue knowledge
- incident workflow

But it still behaves more like:
- one orchestrator
- one model call
- deterministic policy helpers

It does **not yet** behave like a true local multimodal agent runtime with:
- specialized subagents
- tool discipline
- skill packs
- lifecycle hooks
- structured long-lived memory layers
- local model arbitration

### 4. The repo is still too browser-shaped for the immediate product need
The current project can do useful local work, but the user goal now is:
- open Blink-AI locally
- speak through the Mac microphone
- hear replies through the Mac speaker
- let the Mac camera observe the world
- run bodyless or virtual-body by default

So the product should stop assuming that the browser console is the main "live embodiment" path.

## Main gaps relative to the immediate goal

### Gap A — No first-class native mic→STT→reason→TTS loop
Needed:
- continuous or push-to-talk microphone capture
- VAD or explicit turn control
- native local STT backends
- reply synthesis through speaker
- interruption/cancel support
- latency instrumentation

### Gap B — No first-class native webcam perception loop
Needed:
- native webcam capture
- frame sampler
- frame queue
- perception workers
- scene fact extraction
- confidence-aware publishing into the world model

### Gap C — No local model router for Apple Silicon
Needed:
- model profiles
- local vs cloud arbitration
- separate backends for:
  - text reasoning
  - vision understanding
  - embeddings
  - STT
  - TTS
- load/unload policy for 24 GB unified memory

### Gap D — No Claude-Code-style agent operating system
Needed:
- skills
- hooks
- subagents
- strict tool schemas
- persistent project/identity instructions
- runtime-learned memory
- status and audit surfaces

### Gap E — Memory is still too simple for a long-lived conversational companion
Needed:
- episodic memory
- semantic memory
- profile memory
- venue/knowledge retrieval
- compact summaries
- user preference memory
- retrieval scoring and source visibility

## Product judgement

Because the current robot is visually an expressive social bust/head rather than a manipulation platform, the near-term product should optimize for:

- attentive conversation
- grounded perception
- expressive gaze and facial semantics
- memory and social continuity
- visible honesty about uncertainty
- desktop-native usability

It should **not** optimize next for:
- navigation
- locomotion
- arm manipulation
- learning robot motor policies from scratch
- Isaac-heavy workflows as the default development path

## Resulting recommendation

The next huge upgrade is:

## **Blink-AI Local Intelligence Runtime**

That means:
- desktop-first
- body-optional
- multimodal
- agentic
- local/cloud hybrid
- designed for the M4 Pro machine first
- still able to drive the servo body later through the existing semantic body layer
