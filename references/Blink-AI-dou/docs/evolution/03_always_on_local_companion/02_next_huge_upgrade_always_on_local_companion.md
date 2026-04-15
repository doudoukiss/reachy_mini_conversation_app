# 02 — Next Huge Upgrade: Always-On Local Companion

## Milestone summary

Blink-AI should become a **local multimodal companion runtime** that runs on the M4 Pro MacBook even with no powered robot body.

The robot head remains important, but in this phase it is treated as:

- optional
- virtualizable
- semantic-only from the brain’s point of view

The Mac becomes the real embodied runtime.

## Product target for this phase

A user should be able to launch Blink-AI locally and get this experience:

1. Blink-AI is idle and observing quietly.
2. It notices a person entering view or a conversational cue.
3. It decides whether to greet, wait, or stay silent.
4. It hears speech naturally.
5. It retrieves relevant memory and grounded scene facts.
6. It answers concisely through the speaker.
7. It can be interrupted.
8. It can follow up when appropriate.
9. It exports evidence and traces of what happened.
10. The same semantic body commands work with virtual mode now and serial body mode later.

## Core design principle

Do **not** treat the local model like a single giant black box.

Instead, structure the runtime as:

- a continuous local supervisor
- a scene observer
- a conversation turn manager
- a trigger engine
- a memory loop
- a tool-using dialogue planner
- a semantic body output layer

## The main change in architecture

Current center of gravity:

- request/response turn handling
- capture a snapshot when needed
- generate a reply
- optionally emit semantic body commands

New center of gravity:

- always-running local loop
- background perception and state updates
- explicit trigger evaluation
- explicit turn state transitions
- proactive but bounded interaction
- stronger memory promotion and retrieval

## Recommended sub-milestones

### Sub-milestone A — Canonical local model profile

Make the installed models first-class:

- `qwen3.5:9b` for text reasoning and image-grounded dialogue
- `embeddinggemma:300m` for semantic retrieval

This should become the default documented local companion profile for the M4 Pro machine.

### Sub-milestone B — Continuous voice loop

Move beyond bounded single-turn capture.
Introduce a persistent local voice runtime with:

- push-to-talk and/or wake control
- voice activity detection or turn-state gating
- interruption / barge-in handling
- honest fallback to typed input

### Sub-milestone C — Two-tier perception loop

Use a cheap continuous watcher for scene changes and a heavier multimodal model only when needed.

### Sub-milestone D — Proactive trigger engine

Build a policy layer that decides when Blink-AI should:

- greet
- comment
- ask follow-up questions
- remind
- stay quiet
- defer to the user

### Sub-milestone E — Daily-use local companion

Make the system useful in daily life, not only for demo scenes.

## What not to do

- do not hardwire raw servo byte logic into the brain
- do not make continuous multimodal inference run at full LLM cost on every frame
- do not force cloud dependencies into the core local path
- do not remove typed fallback and deterministic degraded behavior
- do not collapse skills, hooks, tools, memory, and perception into one monolithic prompt

## The concrete target state

At the end of this milestone, Blink-AI should be able to serve as:

- a local companion
- a local talking visual assistant
- a future robot brain whose embodiment output already targets the semantic body interface
