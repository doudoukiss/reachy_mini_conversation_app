# North Star

This is the authoritative product definition for Blink-AI.

Use this document when other files seem to disagree. For execution priorities, see [current_direction.md](/Users/sonics/project/Blink-AI/docs/current_direction.md). For architecture, see [architecture.md](/Users/sonics/project/Blink-AI/docs/architecture.md). For stage status, see [plan_w/README.md](/Users/sonics/project/Blink-AI/docs/evolution/plan_w/README.md).

## Product Definition

Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.

## What That Means

- The primary product is the AI presence living in the computer.
- The primary user-facing surface is `uv run local-companion`.
- The browser appliance, `/console`, and the Action Center are secondary operator and control surfaces around the same runtime.
- The robot head, virtual body, and future transport paths are optional embodiment, not the product definition.
- The Action Plane is the safe slow-loop capability substrate for digital side effects, not the product identity.
- `venue_demo` community concierge behavior remains supported, but it is an explicit mode layered on top of the same core runtime.

## Standard Terms

### local-first companion

The default Blink-AI product path: a companion that runs primarily on a nearby Mac, keeps memory and orchestration local when possible, and remains useful even with no body attached.

### character presence runtime

The product layer that makes Blink-AI feel like one continuous presence across terminal, voice, browser, avatar, and optional embodiment. It synchronizes language, memory, initiative, attention, and expression.

### fast loop / slow loop

- `fast loop`: low-latency presence behavior such as listening, thinking, speaking, short acknowledgements, visible state, and expression updates
- `slow loop`: slower task execution such as Action Plane work, workflows, browser tasks, approvals, memory consolidation, and heavier grounding

The fast loop should make Blink-AI feel alive. The slow loop should make it capable, safe, and inspectable.

### relationship runtime

The bounded continuity layer inside the companion. It governs greetings, re-entry, follow-up, planning style, tone bounds, and what relationship-relevant memory Blink-AI may store or surface.

### optional embodiment

Any virtual or physical body that renders the same companion runtime. Embodiment changes how Blink-AI is expressed, not what Blink-AI is.

## Honest Current State

- The terminal-first local companion path is real and already implemented.
- The browser appliance and operator surfaces are real and supported, but they are secondary.
- The Action Plane and optional embodiment substrate are real and implemented.
- The full character presence runtime is not finished yet. The fast loop, persona-manifest layer, and lightweight avatar shell are the next major upgrade, not a completed claim.

## Contributor Rule

When writing docs, prompts, skills, or product copy:

1. Start from the local-first companion.
2. Treat the character presence runtime as the next defining product layer.
3. Treat the Action Plane as substrate.
4. Treat embodiment as optional downstream expression.
5. Treat `venue_demo` as a mode, not the default identity.
