# Codex AVP prompt 04 — add the embodied-stack / Jushen adapter scaffold

Implement the adapter boundary for the real robot stack without requiring hardware.

## Goal

Add a typed adapter that can talk to the existing embodied-stack body runtime in mock or mocked-client conditions first.

## Create these files

- `src/reachy_mini_conversation_app/robot_brain/adapters/embodied_stack_adapter.py`

You may also create a small client helper module if that keeps the code clean.

## Modify these files

- `src/reachy_mini_conversation_app/config.py`
- `src/reachy_mini_conversation_app/main.py`
- `src/reachy_mini_conversation_app/robot_brain/adapters/__init__.py`

## Required implementation details

### 1. Config

Add settings such as:

- `EMBODIED_STACK_BASE_URL`
- `EMBODIED_STACK_TIMEOUT_S`
- `EMBODIED_STACK_ENABLE_LIVE`
- `EMBODIED_STACK_CAPABILITY_PATH`
- `EMBODIED_STACK_HEALTH_PATH`

### 2. Adapter surface

The adapter must implement the common adapter interface and support at least:

- `get_capabilities`
- `get_health`
- `get_state`
- `execute`
- `cancel`
- `go_neutral`

### 3. Preview-first behavior

By default, the adapter should operate in preview mode only.
It should refuse live execution unless an explicit live-enable flag is set.

### 4. Capability catalog source of truth

The adapter should be designed to fetch capability information from the existing body runtime rather than embedding static behavior knowledge in this repo.

### 5. Action mapping

Implement a clear mapping from generic action names to body-runtime calls or request payloads.
Do not assume low-level serial access in this repo.

### 6. Error handling

Return typed action results for:

- unsupported action
- body runtime unavailable
- timeout
- degraded or unsafe health
- live mode blocked by config

## Tests to add

Use mocked HTTP or mocked client responses to test:

- capability loading
- health loading
- preview action success
- live action blocked by config
- error handling

## Acceptance criteria

- no hardware is required
- no serial code is added to this repo
- the adapter is ready to be pointed at the real body runtime later
