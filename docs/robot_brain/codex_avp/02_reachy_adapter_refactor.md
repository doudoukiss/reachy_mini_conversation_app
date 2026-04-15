# Codex AVP prompt 02 — wrap the current Reachy path behind an adapter

Implement the Reachy compatibility adapter.

## Goal

Preserve current functionality while moving Reachy-specific logic behind the new body-adapter boundary.

## Create these files

- `src/reachy_mini_conversation_app/robot_brain/adapters/reachy_adapter.py`

## Modify these files

- `src/reachy_mini_conversation_app/main.py`
- `src/reachy_mini_conversation_app/moves.py`
- `src/reachy_mini_conversation_app/camera_worker.py`
- `src/reachy_mini_conversation_app/tools/core_tools.py`

Modify additional files only if necessary.

## Required implementation details

### 1. Reachy adapter responsibilities

The adapter should own the current Reachy-specific runtime dependencies:

- `ReachyMini`
- `MovementManager`
- `CameraWorker`
- `HeadWobbler`

It should translate semantic actions into the current implementation where possible.

### 2. Minimum action mapping

Support these semantic actions through the Reachy adapter:

- `go_neutral`
- `set_attention_mode`
- `orient_attention`
- `observe_scene`
- `stop_behavior`

You may implement `set_persistent_state` and `perform_motif` as rejected/not-supported for now if the Reachy path has no clean equivalent.
Return a typed `ActionResult` with clear status and warnings.

### 3. Main startup

Refactor `main.py` so robot construction and adapter construction are separate concerns.

Desired shape:

- config selects backend
- backend factory builds `MockRobotAdapter` or `ReachyAdapter`
- `ToolDependencies` receives `robot_runtime`

### 4. Preserve existing behavior

Do not delete the current movement manager or camera worker logic.
Use them internally from the Reachy adapter.

### 5. Avoid new direct Reachy dependencies in tools

No new tool should import `ReachyMini` directly.
All robot access should move toward `robot_runtime`.

## Tests to add

- adapter factory test
- Reachy adapter action translation tests using mocks/fakes
- startup test for `ROBOT_BACKEND=mock` and `ROBOT_BACKEND=reachy`

## Acceptance criteria

- current Reachy path still works conceptually
- app architecture now treats Reachy as one adapter, not the whole system
- `main.py` is less robot-specific than before
