# Stage 7 — Character Presence Runtime

## Status

Planned next major upgrade.

Stage 0 through Stage 6 gave Blink-AI a strong local-first companion, Agent OS, world model, memory substrate, Action Plane, optional embodiment path, and research/eval discipline.

The largest remaining product gap is now **presence**:

- a visible identity
- low-latency aliveness between task turns
- synchronization between language, memory, initiative, and expression
- an avatar shell and eventual robot body that clearly project the same mind

## Why this is next

The current repo can already:

- converse in a terminal-first loop
- remember and retrieve useful context
- run safe digital actions under approval
- render semantic embodiment into virtual or serial body actions
- export and evaluate episodes

What it cannot yet do in a world-class way is feel like a **persistent character presence**.

## Target outcome

Blink-AI should become a terminal-first, local-first, character-presence companion OS with:

- an explicit persona manifest
- a presence state machine
- a `fast loop / slow loop` split
- a bounded initiative engine
- an optional lightweight avatar shell
- synchronized expression output across terminal, avatar, virtual body, and serial head

## Recommended architecture

### Loops

1. Fast loop
2. Slow loop (existing Action Plane and planners)
3. Memory loop
4. Proactivity loop

### Three buses

1. Interaction Event Bus
2. Presence State Bus
3. Action and Approval Bus

## Remaining hardening rule

Do not start with universal desktop automation.
The first strong scenario should stay narrow and current-repo-aligned:

- terminal-first daily use
- coding / writing / research workflows
- browser and document assistance
- optional voice
- lightweight avatar shell

## What Stage 7 must preserve

- terminal-first `local-companion` remains valid and primary
- browser appliance and Action Center remain secondary control surfaces
- Action Plane remains the slow-loop capability substrate
- relationship runtime remains bounded and inspectable
- embodiment remains optional and semantic
- memory remains bounded, editable, and inspectable
- initiative remains conservative and rate-limited
