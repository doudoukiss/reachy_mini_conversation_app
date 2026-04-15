# Product Direction

This is the maintained product-layer summary for Blink-AI.

The authoritative product definition lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).

## Product Definition

Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.

The default identity is a private companion running on a nearby Mac, not a venue-first robot identity, browser-automation shell, hardware-first robotics stack, or generic assistant with no presence model.

## Product Stack

### local-first companion

The main product loop is the local-first companion on the Mac:

- terminal-first conversation
- local memory continuity
- grounded local context
- safe, inspectable actions
- graceful fallback when devices, models, or perception are degraded

The primary user-facing surface is `uv run local-companion`.

### character presence runtime

The next major product layer is the character presence runtime.

It should make Blink-AI feel like one continuous presence by splitting behavior into a `fast loop / slow loop` model:

- `fast loop`: low-latency listening, thinking, speaking, visible state, and expression
- `slow loop`: Action Plane tasks, workflows, approvals, memory consolidation, and heavier grounding
- bounded initiative belongs to the fast loop and should start with `ignore / suggest / ask / act`, suggestion-first and question-first, with only narrow auto-action by default
- a lightweight browser presence shell may mirror the same fast loop, but it remains optional and secondary to `uv run local-companion`

That does not replace the terminal as the primary interface. It makes the same local-first companion feel more alive and coherent.

### relationship runtime

The relationship runtime is the bounded continuity layer for the local-first companion. It handles greeting and re-entry, follow-up, planning style, tone bounds, familiarity, recurring topics, promises, and open threads without drifting into fake intimacy or indiscriminate storage.

### optional embodiment

Embodiment is an optional projection layer for the same companion core.

Today that means:

- bodyless operation is valid and supported
- virtual body is the default expressive path
- serial head is an optional hardware path
- future Jetson transport remains thin, deterministic, and safety-focused

The body expresses the companion. It does not define the product thesis.

### Action Plane

The Action Plane is Blink-AI's safe slow-loop substrate for digital side effects.

Its job is to make actions:

- typed
- inspectable
- approval-aware
- replayable
- operator-visible

It is capability infrastructure, not product identity.

### `venue_demo`

`venue_demo` is an explicit vertical mode built on top of the same companion core.

It exists to support:

- investor demos
- community concierge and guide pilots
- venue knowledge packs
- operator handoff and shift workflows

It should remain strong and believable, but it is a mode-specific deployment of Blink-AI rather than the hidden default identity of the repo.
