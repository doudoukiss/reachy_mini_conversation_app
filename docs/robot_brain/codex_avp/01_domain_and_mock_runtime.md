# Codex AVP prompt 01 — introduce robot-brain contracts and mock runtime

Implement the first migration step.

## Goal

Create a robot-agnostic domain layer and a mock-first runtime without breaking the existing app.

## Create these files

- `src/reachy_mini_conversation_app/robot_brain/__init__.py`
- `src/reachy_mini_conversation_app/robot_brain/contracts.py`
- `src/reachy_mini_conversation_app/robot_brain/runtime.py`
- `src/reachy_mini_conversation_app/robot_brain/state_store.py`
- `src/reachy_mini_conversation_app/robot_brain/capability_catalog.py`
- `src/reachy_mini_conversation_app/robot_brain/adapters/__init__.py`
- `src/reachy_mini_conversation_app/robot_brain/adapters/base.py`
- `src/reachy_mini_conversation_app/robot_brain/adapters/mock_adapter.py`

## Modify these files

- `src/reachy_mini_conversation_app/config.py`
- `src/reachy_mini_conversation_app/main.py`
- `src/reachy_mini_conversation_app/tools/core_tools.py`

## Required implementation details

### 1. Contracts

Implement typed contracts for:

- capability catalog
- robot health
- robot state
- robot action
- action result
- execution mode

Use dataclasses or Pydantic, but keep the types easy to serialize and test.

### 2. Adapter base interface

Define a protocol or abstract base class for a robot body adapter with methods:

- `get_capabilities`
- `get_health`
- `get_state`
- `execute`
- `cancel`
- `go_neutral`

### 3. Mock adapter

Implement a deterministic `MockRobotAdapter` that:

- exposes a small but realistic capability catalog
- supports `go_neutral`
- supports `set_persistent_state`
- supports `perform_motif`
- supports `set_attention_mode`
- supports `observe_scene`
- supports `stop_behavior`
- records actions to an in-memory journal
- can simulate a long-running action and cancellation

### 4. Runtime object

Implement `RobotBrainRuntime` that wraps one adapter and offers:

- `get_capabilities`
- `get_health`
- `get_state`
- `execute_action`
- `cancel_action`
- `go_neutral`

The runtime should also own a small state store or journal helper.

### 5. Config and startup

Add config for:

- `ROBOT_BACKEND` with at least `mock` and `reachy`
- `ROBOT_EXECUTION_MODE`
- `ROBOT_DISABLE_EXTERNAL_TOOLS`

Update startup so the app can build a robot runtime object even before the Reachy adapter exists.
If the backend is `mock`, the app must not require a Reachy connection.

### 6. Tool dependencies

Refactor `ToolDependencies` so it can carry a `robot_runtime` object.
Do not remove the old fields yet; keep migration-compatible fields if needed.

## Tests to add

Create tests for:

- contract creation/serialization
- mock adapter capabilities
- mock action execution
- mock cancellation
- runtime wrapper behavior

## Acceptance criteria

- app startup can select `ROBOT_BACKEND=mock`
- no physical robot is needed for the new tests
- existing tests still pass or any necessary adjustments are minimal and explained
- `ToolDependencies` can support future semantic tools through `robot_runtime`
