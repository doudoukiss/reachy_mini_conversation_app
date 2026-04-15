# Capability and action contract proposal

This document defines the contract between the conversation app and a robot body adapter.

The goal is to support the same contract in three modes:

- `mock`
- `preview`
- `live`

---

## Python-side interface

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ExecutionMode = Literal["mock", "preview", "live"]
ActionStatus = Literal["accepted", "running", "completed", "failed", "cancelled", "rejected"]

@dataclass
class CapabilityCatalog:
    robot_name: str
    backend: str
    modes_supported: list[ExecutionMode]
    structural_units: list[str] = field(default_factory=list)
    expressive_units: list[str] = field(default_factory=list)
    persistent_states: list[str] = field(default_factory=list)
    motifs: list[str] = field(default_factory=list)
    attention_modes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

@dataclass
class RobotHealth:
    overall: Literal["ok", "degraded", "unsafe", "unknown"]
    message: str
    details: dict[str, Any] = field(default_factory=dict)

@dataclass
class RobotState:
    mode: ExecutionMode
    active_behavior: str | None = None
    persistent_state: str | None = None
    attention_mode: str | None = None
    last_observation_summary: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class RobotAction:
    action_type: str
    args: dict[str, Any] = field(default_factory=dict)
    mode: ExecutionMode = "mock"

@dataclass
class ActionResult:
    action_id: str
    action_type: str
    status: ActionStatus
    mode: ExecutionMode
    summary: str
    warnings: list[str] = field(default_factory=list)
    observation: dict[str, Any] | None = None
    state_snapshot: RobotState | None = None
    health_snapshot: RobotHealth | None = None
    details: dict[str, Any] = field(default_factory=dict)

class RobotBodyAdapter(Protocol):
    async def get_capabilities(self) -> CapabilityCatalog: ...
    async def get_health(self) -> RobotHealth: ...
    async def get_state(self) -> RobotState: ...
    async def execute(self, action: RobotAction) -> ActionResult: ...
    async def cancel(self, action_id: str) -> ActionResult: ...
    async def go_neutral(self, mode: ExecutionMode = "mock") -> ActionResult: ...
```

---

## Recommended action vocabulary

### `go_neutral`

No arguments.

### `orient_attention`

```json
{
  "target": "left|right|up|down|front|image_point|named_person",
  "x": 0.62,
  "y": 0.40,
  "reason": "attend to the speaking user"
}
```

### `set_attention_mode`

```json
{
  "mode": "manual|face_tracking|idle_scan|disabled"
}
```

### `set_persistent_state`

```json
{
  "state": "neutral|friendly|listen_attentively|thinking|focused_soft|concerned|confused|safe_idle"
}
```

### `perform_motif`

```json
{
  "motif": "guarded_close_right",
  "intensity": "low|medium|high",
  "reason": "react to a scary joke"
}
```

### `observe_scene`

```json
{
  "question": "What is in front of me?",
  "include_image": false
}
```

### `stop_behavior`

```json
{
  "behavior": "current|attention|expression|all"
}
```

### `query_health`

No arguments.

### `query_capabilities`

No arguments.

---

## Suggested HTTP contract for the embodied-stack adapter

These endpoints are not claims about the current body runtime.
They are the recommended boundary to add if you want a clean service interface.

### `GET /api/body/capabilities`

Returns `CapabilityCatalog`.

### `GET /api/body/health`

Returns `RobotHealth`.

### `GET /api/body/state`

Returns `RobotState`.

### `POST /api/body/actions/preview`

Request body: `RobotAction`
Response: `ActionResult`

### `POST /api/body/actions/execute`

Request body: `RobotAction`
Response: `ActionResult`

### `POST /api/body/actions/{action_id}/cancel`

Response: `ActionResult`

### `POST /api/body/go-neutral`

Body:

```json
{
  "mode": "preview"
}
```

---

## Mapping to your existing body stack

The existing docs suggest the real body stack already has the semantic structure needed to back this contract:

- grounded expression catalog
- persistent states
- motifs
- semantic body layer
- live safety and calibration gating
- health polling
- atomic family demonstrations and expressive motif runtime

So the adapter should translate the generic action vocabulary above into whichever internal cues, operator APIs, or Python entrypoints already exist in that stack, rather than bypassing it. fileciteturn0file0

---

## Mock adapter contract requirements

The mock adapter should implement the same methods and return the same structures.

### Minimum mock capabilities

```json
{
  "robot_name": "mock-head",
  "backend": "mock",
  "modes_supported": ["mock"],
  "structural_units": ["head_turn", "neck_pitch", "neck_tilt"],
  "expressive_units": ["eye_yaw", "eye_pitch", "lids", "brows"],
  "persistent_states": ["neutral", "friendly", "listen_attentively", "thinking", "safe_idle"],
  "motifs": ["guarded_close_left", "guarded_close_right"],
  "attention_modes": ["manual", "face_tracking", "idle_scan", "disabled"],
  "warnings": []
}
```

### Minimum mock health states

- `ok`
- `degraded`
- `unsafe`

### Minimum mock failure cases

- invalid motif
- unsupported persistent state
- action timeout
- degraded health blocks live/preview request
- cancellation of long-running action

---

## Tooling implications

Tools in the conversation app should depend on:

- `RobotBrainRuntime` or `RobotBodyAdapter`
- not on `ReachyMini`
- not on `MovementManager`
- not on raw motion-library types

This is the key move that lets you use the same tools in mock mode, Reachy compatibility mode, and Jushen mode.

---

## Prompting implications

Prompt/tool descriptions should be generated from `CapabilityCatalog`, not manually written lists.

That prevents a common failure mode:
the model tries to use a behavior that the currently connected robot cannot actually perform.
