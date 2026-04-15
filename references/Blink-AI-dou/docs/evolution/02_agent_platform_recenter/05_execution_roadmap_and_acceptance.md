# 05 — Execution roadmap and acceptance

## Target milestone

## Milestone — Local Embodied Companion Runtime

Blink-AI should become a local desktop companion system that:
- listens through the Mac microphone
- sees through the Mac webcam
- speaks through the Mac speaker
- reasons locally or in the cloud through profiles
- tracks people, context, memory, and scene facts
- produces semantic body actions now
- drives the real expressive head later

## Phase 1 — Native desktop interaction loop

### Deliverables
- native mic capture service
- native webcam capture service
- turn manager with push-to-talk and typed fallback
- speech playback service
- latency instrumentation
- bodyless and virtual-body-first startup

### Acceptance
- one command launches Blink-AI locally
- no browser is required for a basic conversation
- the system can hear a question, respond, and speak back
- typed fallback still works
- the operator can see device health and current mode

## Phase 2 — Local model router

### Deliverables
- model profile registry
- backend interfaces for:
  - text reasoning
  - vision analysis
  - embeddings
  - STT
  - TTS
- profile switching between:
  - cloud_best
  - local_balanced
  - local_fast
  - offline_safe

### Acceptance
- profile can be changed without refactoring core logic
- provider state is visible
- local fallback is honest and usable
- low-memory and unavailable-backend paths degrade clearly

## Phase 3 — Agent OS

### Deliverables
- skill registry
- hook system
- subagent abstractions
- strict tool schemas
- action plan validation
- runtime status summary
- persistent instruction files

### Acceptance
- replies are generated through an explicit planning path
- tool calls are inspectable
- active skill is visible
- unsafe or unsupported action plans are downgraded
- long prompts are replaced by structured instructions and tools

## Phase 4 — Memory, retrieval, and grounded perception

### Deliverables
- episodic memory store
- semantic retrieval store
- profile memory
- compact turn summaries
- scene fact indexing
- perception freshness / confidence policy
- evidence-based reply grounding

### Acceptance
- Blink-AI can remember prior discussion topics
- Blink-AI can use visible context from camera input
- Blink-AI can say when it is unsure
- stale scene facts expire
- retrieval sources are visible

## Phase 5 — Productization and demo hardening

### Deliverables
- polished local desktop entrypoint
- companion-mode defaults
- device health dashboard
- conversation/story demos
- local eval suite
- artifact bundles for real local sessions
- explicit "no body", "virtual body", and "serial body later" modes

### Acceptance
- a non-technical user can launch the system
- a five-minute natural conversation works repeatedly
- camera-grounded dialogue works
- bodyless and virtual-body modes are stable
- local artifacts are exported after sessions
- the future servo path is still compatible

## Non-goals for this milestone

Do not spend the milestone on:
- robot navigation
- locomotion
- manipulation policy training
- ROS-first rearchitecture
- Isaac-first rearchitecture
- world-model research projects unrelated to the current desktop companion product

## Validation commands to add or keep

- `uv run pytest`
- focused desktop-local tests
- profile smoke tests
- one-command local conversation smoke test
- one-command camera-grounded conversation smoke test
- one-command offline-safe smoke test
- one-command story or demo evidence export

## Final success test

A person should be able to:
1. open Blink-AI on the MacBook
2. talk naturally
3. be seen through the webcam
4. receive grounded spoken replies
5. observe visible state changes and embodied attention behavior
6. continue interacting even though the physical servo controller is still offline
