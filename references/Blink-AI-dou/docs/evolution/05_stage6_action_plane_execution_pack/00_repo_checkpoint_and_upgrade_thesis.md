# Repo Checkpoint and Upgrade Thesis

## Current repository state

The current repo already includes:

- local appliance and local companion entrypoints
- explicit Agent OS runtime with skills, subagents, checkpoints, and typed tools
- perception, world model, social runtime, memory layers, teacher annotations, and episode export
- semantic embodiment with virtual body and serial-head landing zone
- research bridge and replay/eval infrastructure
- browser console and operator-facing runtime visibility

## What is missing

The largest remaining capability gap is **safe digital action**.

Today Blink-AI is much better at:

- seeing
- listening
- reasoning
- remembering
- replying
- expressing through semantic body actions

than it is at:

- opening the right page
- following a bounded browser workflow
- creating or updating a reminder or note through a governed action layer
- waiting for approval and resuming later
- executing a multi-step workflow with auditable state
- exposing connector health/capabilities the way a world-class assistant platform should

## Why this is the next huge upgrade

This is the right next step because it compounds almost every earlier stage:

- Agent OS gets real effectful tools instead of mostly informational tools
- local companion becomes a useful assistant rather than just an embodied conversational runtime
- workflow execution creates richer episode data than passive dialogue alone
- future robot embodiments can reuse the same action substrate
- the project becomes more differentiated from “chat plus servo demos”

## Stage 6 definition

**Stage 6 — Personal Action Plane, Workflow Runtime, and MCP-Compatible Skill Gateway**

Stage 6 should add:

1. a typed action protocol with approvals, idempotency, and audit history
2. a connector/runtime layer for local digital tools
3. a safe browser/computer-use runtime
4. a workflow runner for bounded multi-step assistance
5. action evidence bundles, replay, and evaluation
6. productized UI and CLI surfaces for approvals and action status

## Design stance

Blink-AI should not become a loose collection of side-effecting Python functions.

It should become a disciplined system with:

- a deterministic shell around model proposals
- stable tool contracts
- approval policies
- resumable runs
- bounded workflows
- replayable artifacts
- clear separation between reasoning and execution

## World-class benchmark for this stage

By the end of this stage Blink-AI should be able to:

- understand a request
- propose a bounded action plan
- preview what it wants to do
- request approval when needed
- execute through typed connectors
- resume after interruption or restart
- export the run as evidence
- explain exactly what happened
- continue to work without the physical robot body attached
