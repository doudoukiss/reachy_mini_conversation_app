from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from embodied_stack.shared.contracts.action import (
    ActionApprovalRecord,
    ActionApprovalState,
    ActionExecutionRecord,
    ActionInvocationOrigin,
    ActionPlaneStatus,
    ActionPolicyDecision,
    ActionProposalRecord,
    ActionRequestRecord,
    ActionRiskClass,
    ConnectorHealthRecord,
)
from embodied_stack.shared.contracts._common import ToolCapabilityState, ToolResultStatus

ACTION_PLANE_SCHEMA_VERSION = "stage_b.v1"


class PendingApprovalEnvelope(BaseModel):
    schema_version: str = ACTION_PLANE_SCHEMA_VERSION
    items: list[ActionApprovalRecord] = Field(default_factory=list)


class ExecutionLogEnvelope(BaseModel):
    schema_version: str = ACTION_PLANE_SCHEMA_VERSION
    items: list[ActionExecutionRecord] = Field(default_factory=list)


class ConnectorHealthEnvelope(BaseModel):
    schema_version: str = ACTION_PLANE_SCHEMA_VERSION
    items: list[ConnectorHealthRecord] = Field(default_factory=list)


class ActionPolicyOutcome(BaseModel):
    connector_id: str
    risk_class: ActionRiskClass
    policy_decision: ActionPolicyDecision
    approval_state: ActionApprovalState
    detail: str | None = None


class ActionPlaneSnapshot(BaseModel):
    status: ActionPlaneStatus
    connector_health: list[ConnectorHealthRecord] = Field(default_factory=list)
    pending_approvals: list[ActionApprovalRecord] = Field(default_factory=list)
    execution_log: list[ActionExecutionRecord] = Field(default_factory=list)


@dataclass(frozen=True)
class ActionInvocationResult:
    output_model: BaseModel | dict[str, object]
    proposal: ActionProposalRecord
    execution: ActionExecutionRecord
    approval: ActionApprovalRecord | None = None
    success_override: bool | None = None
    result_status_override: ToolResultStatus | None = None
    capability_state_override: ToolCapabilityState | None = None
    summary_override: str | None = None


@dataclass(frozen=True)
class ActionInvocationContext:
    session_id: str | None
    run_id: str | None
    context_mode: str | None
    body_mode: str | None
    invocation_origin: ActionInvocationOrigin
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None


@dataclass(frozen=True)
class ActionToolRoute:
    tool_name: str
    connector_id: str
    action_name: str


__all__ = [
    "ACTION_PLANE_SCHEMA_VERSION",
    "ActionInvocationContext",
    "ActionInvocationResult",
    "ActionPlaneSnapshot",
    "ActionPolicyOutcome",
    "ActionToolRoute",
    "ConnectorHealthEnvelope",
    "ExecutionLogEnvelope",
    "PendingApprovalEnvelope",
]
