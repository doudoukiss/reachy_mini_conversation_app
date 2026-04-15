# Stage D — Workflow Runtime and Proactive Assistant

## Objective

Give Blink-AI a real bounded workflow system so it can complete multi-step work instead of isolated actions.

## Why this matters

World-class assistants do not only answer and execute one tool call.
They can:

- propose a plan
- stage work
- wait for approval
- continue later
- recover after interruption
- explain state at any point

## Deliverables

### 1. Workflow model
Create workflow definitions and workflow run records.

Core concepts:

- workflow id
- trigger
- preconditions
- steps
- approval boundaries
- retry policy
- timeout policy
- completion policy
- artifacts
- run summary

### 2. Workflow executor
A runtime that can:
- start a run
- pause
- resume
- retry a failed step
- branch on deterministic conditions
- emit artifacts and progress snapshots

### 3. Trigger model
Support bounded triggers such as:
- user request
- due reminder
- calendar event start window
- operator launch
- daily digest time
- venue-site schedule event

### 4. Initial workflow library

Suggested first workflows:

- save note and reminder from conversation
- morning personal briefing
- event lookup then open event page
- prepare investor/demo checklist
- follow up on unresolved incident ticket
- community concierge event guidance workflow

### 5. Proactive assistant discipline
Proactivity must be governed.

Rules:
- no high-risk autonomous action
- suggestions before side effects when uncertainty is non-trivial
- no surprise browser write actions
- quiet-hours aware
- context-mode aware (`personal_local` vs `venue_demo`)

### 6. Embodied feedback integration
When a workflow runs, Blink-AI may emit semantic body states such as:
- listening
- thinking
- acknowledging
- waiting_for_approval
- safe_idle

But workflow logic must not depend on body availability.

## Implementation order

1. workflow contracts
2. workflow state store
3. executor with pause/resume
4. one or two initial workflows
5. trigger integration
6. console/CLI workflow surfaces
7. proactive policy guardrails

## Validation

Add tests for:

- resumable runs after restart
- deduplicated step execution
- approval pause and later resume
- workflow timeouts
- quiet-hours suppression
- embodied feedback staying optional

## Success criteria

Stage D is done when Blink-AI can complete bounded multi-step assistance with explicit state, approval pauses, and resumable execution.
