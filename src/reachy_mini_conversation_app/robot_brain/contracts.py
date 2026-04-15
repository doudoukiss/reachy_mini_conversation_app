"""Typed contracts for robot-brain adapters and runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypeAlias


ExecutionMode: TypeAlias = Literal["mock", "preview", "live"]
ActionStatus: TypeAlias = Literal["accepted", "running", "completed", "failed", "cancelled", "rejected"]


@dataclass(slots=True)
class CapabilityCatalog:
    """Live capability surface exposed by a robot body adapter."""

    robot_name: str
    backend: str
    modes_supported: list[ExecutionMode]
    structural_units: list[str] = field(default_factory=list)
    expressive_units: list[str] = field(default_factory=list)
    persistent_states: list[str] = field(default_factory=list)
    motifs: list[str] = field(default_factory=list)
    attention_modes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the catalog to a plain dictionary."""
        return asdict(self)


@dataclass(slots=True)
class RobotHealth:
    """Health snapshot for the connected robot backend."""

    overall: Literal["ok", "degraded", "unsafe", "unknown"]
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the health snapshot to a plain dictionary."""
        return asdict(self)


@dataclass(slots=True)
class RobotState:
    """Semantic state snapshot for the connected robot."""

    mode: ExecutionMode
    active_behavior: str | None = None
    persistent_state: str | None = None
    attention_mode: str | None = None
    last_observation_summary: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the robot state to a plain dictionary."""
        return asdict(self)


@dataclass(slots=True)
class RobotAction:
    """Typed semantic action request sent to a robot adapter."""

    action_type: str
    args: dict[str, Any] = field(default_factory=dict)
    mode: ExecutionMode = "mock"
    action_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the action to a plain dictionary."""
        return asdict(self)


@dataclass(slots=True)
class ActionResult:
    """Typed semantic action result returned by a robot adapter."""

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
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the action result to a plain dictionary."""
        return asdict(self)
