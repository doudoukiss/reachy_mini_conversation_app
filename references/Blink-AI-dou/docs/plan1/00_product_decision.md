# Product Decision

This file is preserved planning lineage. The authoritative product definition now lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).

## Final product definition

Blink-AI should ultimately be:

## **A terminal-first, local-first, character-presence companion OS with optional embodiment**

Short version:
- **primary identity**: local-first companion with character presence
- **primary surface**: terminal-first local companion runtime
- **secondary surfaces**: browser console, voice loop, background proactive runtime
- **optional embodiment**: expressive robot head / desk companion shell
- **optional vertical**: community concierge / guide mode for demos or commercial pilots

## What Blink-AI is not

It is not primarily:
- a concierge robot product
- a browser-automation product
- a servo-control framework
- an investor-demo shell
- a generic agent platform with no personality or embodiment

## Why this is the right decision

The current repository already proves several things:
- the companion path exists and is maintained
- `personal_local` is already a real context mode
- the robot body is optional
- the browser console is already a secondary surface
- the action plane already exists

What is still fragmented is the **story**.
Some docs and prompts still describe Blink-AI as a community concierge robot, while the maintained runtime already behaves much more like a personal local companion.

The next upgrade is therefore not just code.
It is **product recentering**.

## Canonical product sentence

Use this sentence everywhere after the refactor:

> Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.

## Product layers

### Layer 1 — Companion Core
This is the real product.
- dialogue
- memory
- perception
- world model
- relationship continuity
- planning and safe actions
- terminal/voice interaction

### Layer 2 — Operator / Developer Surfaces
These are control and inspection tools.
- console
- traces
- replay
- evals
- action center
- body calibration tools

### Layer 3 — Embodiment
This is a deployable shell for the Companion Core.
- virtual body
- serial head
- future desk robot form

### Layer 4 — Vertical Packs
These are use-case overlays.
- personal companion
- demo/investor mode
- concierge / guide mode
- future elder-care / classroom / studio modes

## Immediate implication

The default runtime, docs, prompts, and skill library should all point to **local-first companion first**.
Concierge becomes an explicit mode, not the hidden identity.
