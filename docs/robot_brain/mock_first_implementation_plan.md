# Mock-first implementation plan

## Goal

Reach a point where the repository can act as a robot brain in **mock mode** before any real robot is connected, and then add the real embodied-stack adapter with minimal risk.

---

## Phase 0 — Freeze baseline and create migration guardrails

### Deliverables

- create a feature branch
- capture the current tool set and current profiles
- run the existing tests and save the baseline result
- add this documentation bundle to the repo

### Exit criteria

- current Reachy behavior still runs unchanged
- tests are green or known failures are documented

---

## Phase 1 — Introduce robot-brain contracts and runtime skeleton

### Deliverables

Create:

- `src/reachy_mini_conversation_app/robot_brain/contracts.py`
- `src/reachy_mini_conversation_app/robot_brain/runtime.py`
- `src/reachy_mini_conversation_app/robot_brain/capability_catalog.py`
- `src/reachy_mini_conversation_app/robot_brain/state_store.py`
- `src/reachy_mini_conversation_app/robot_brain/adapters/base.py`

Add config flags such as:

- `ROBOT_BACKEND=reachy|mock|embodied_stack`
- `ROBOT_EXECUTION_MODE=mock|preview|live`
- `ROBOT_ENABLE_LIVE=0/1`
- `ROBOT_DISABLE_EXTERNAL_TOOLS=1/0`

### Exit criteria

- app can construct a robot-brain runtime object on startup
- no functional behavior change yet
- code compiles and tests pass

---

## Phase 2 — Add the mock adapter

### Deliverables

Create:

- `src/reachy_mini_conversation_app/robot_brain/adapters/mock_adapter.py`

Features:

- deterministic state machine
- capability catalog
- health surface
- action journal
- simulated long-running actions
- cancellation support
- mock observations for camera/vision requests

### Exit criteria

- app runs with `ROBOT_BACKEND=mock`
- semantic actions execute without hardware
- scenario tests can assert on journaled action results

---

## Phase 3 — Wrap the current Reachy path behind an adapter

### Deliverables

Create:

- `src/reachy_mini_conversation_app/robot_brain/adapters/reachy_adapter.py`

Move Reachy-specific logic behind the adapter boundary:

- `moves.py`
- `camera_worker.py`
- `audio/head_wobbler.py`
- Reachy motion helpers

### Exit criteria

- current Reachy app path still works
- `main.py` no longer needs to know robot-specific details beyond adapter selection
- `tools/core_tools.py` stops exposing `ReachyMini` directly as the primary abstraction

---

## Phase 4 — Replace default tools with semantic tools

### Deliverables

Add semantic tools:

- `observe_scene`
- `report_robot_status`
- `orient_attention`
- `set_attention_mode`
- `set_expression_state`
- `perform_motif`
- `stop_behavior`
- `go_neutral`

Refactor current tools:

- `move_head` becomes a compatibility wrapper
- `play_emotion` becomes legacy/debug-only
- `dance` becomes Reachy-only legacy/debug-only

Create a new default production profile, for example:

- `profiles/robot_brain_default/instructions.txt`
- `profiles/robot_brain_default/tools.txt`

### Exit criteria

- default robot-brain profile uses semantic tools only
- mock mode is the default development path
- tool descriptions are capability-aware

---

## Phase 5 — Add capability-aware prompting and status grounding

### Deliverables

- inject capability summary into session instructions
- inject robot state/health summary into tool-result handling
- add a concise action-result narration layer
- surface mode (`mock`, `preview`, `live`) to the user and to the model

### Exit criteria

- model no longer relies on stale hard-coded robot affordances
- responses after actions are grounded in typed results
- mock and Reachy modes share the same semantic vocabulary

---

## Phase 6 — Add the embodied-stack/Jushen adapter in preview mode

### Deliverables

Create:

- `src/reachy_mini_conversation_app/robot_brain/adapters/embodied_stack_adapter.py`

Initial scope:

- fetch capability catalog
- fetch health/status
- preview-only execution of semantic actions
- no live execution yet

### Exit criteria

- app can run against the embodied stack without owning hardware directly
- preview results are visible in the conversation and logs
- no hardware dependence for CI

---

## Phase 7 — Live integration hardening

### Deliverables

- explicit live enable flag
- preflight checks
- neutral recovery path
- action timeout policy
- degraded-health lockout
- operator-safe stop behavior
- action/result metrics and structured logs

### Exit criteria

- live mode is intentionally gated
- preview mode remains default
- failures fall back to safe state and are narratable

---

## Test strategy

## Unit tests

Add tests for:

- contract serialization
- mock adapter behavior
- action routing
- capability-aware prompt assembly
- semantic tool wrappers
- adapter selection by config

## Scenario tests

Add end-to-end no-hardware tests such as:

1. user asks robot to look attentive
2. model/tool calls `set_expression_state`
3. mock adapter records state transition
4. assistant reply grounds on the result

Other scenarios:

- start face tracking
- perform motif
- stop current behavior
- degraded health blocks action
- cancel long-running behavior
- observe scene in mock mode

## Adapter contract tests

A shared test suite should run against:

- `MockRobotAdapter`
- `ReachyAdapter` (where feasible)
- `EmbodiedStackAdapter` with mocked HTTP/client responses

---

## Definition of done for the hardware-free milestone

You are ready for integration testing on the real robot when all of the following are true:

- the app runs end-to-end with `ROBOT_BACKEND=mock`
- the default profile uses semantic tools only
- the model sees capability-aware instructions
- semantic tools no longer depend directly on `ReachyMini`
- mock scenario tests cover action success, rejection, cancellation, and degraded health
- the embodied-stack adapter runs in preview mode with mocked responses
- live execution remains disabled by default

Only after that should the real robot be attached.

---

## Practical migration rule

During migration, every new semantic action must exist in this order:

1. contract
2. mock implementation
3. test
4. prompt/tool exposure
5. real-adapter implementation
6. live enablement

That order prevents the hardware from becoming the integration test harness.
