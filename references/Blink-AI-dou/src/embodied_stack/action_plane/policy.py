from __future__ import annotations

from embodied_stack.action_plane.models import ActionPolicyOutcome
from embodied_stack.shared.contracts.action import (
    ActionApprovalState,
    ActionInvocationOrigin,
    ActionPolicyDecision,
    ActionRiskClass,
    ConnectorDescriptorRecord,
    ConnectorHealthRecord,
)


class ActionPolicyEngine:
    def risk_class_for(
        self,
        *,
        tool_name: str,
        action_name: str | None = None,
        connector: ConnectorDescriptorRecord | None = None,
        input_model,
    ) -> ActionRiskClass:
        if tool_name == "write_memory":
            return (
                ActionRiskClass.OPERATOR_SENSITIVE_WRITE
                if getattr(input_model, "scope", None) == "profile"
                else ActionRiskClass.LOW_RISK_LOCAL_WRITE
            )
        if tool_name == "promote_memory" and getattr(input_model, "scope", None) == "profile":
            return ActionRiskClass.OPERATOR_SENSITIVE_WRITE
        if tool_name in {"request_operator_help", "log_incident"}:
            return ActionRiskClass.OPERATOR_SENSITIVE_WRITE
        resolved_action_name = action_name or tool_name
        if connector is not None and resolved_action_name in connector.action_risk:
            return connector.action_risk[resolved_action_name]
        if tool_name == "browser_task":
            return ActionRiskClass.READ_ONLY
        return ActionRiskClass.IRREVERSIBLE_OR_HIGH_RISK

    def evaluate(
        self,
        *,
        tool_name: str,
        action_name: str | None = None,
        connector_id: str,
        invocation_origin: ActionInvocationOrigin,
        connector: ConnectorDescriptorRecord | None = None,
        connector_health: ConnectorHealthRecord | None,
        input_model,
    ) -> ActionPolicyOutcome:
        risk_class = self.risk_class_for(
            tool_name=tool_name,
            action_name=action_name,
            connector=connector,
            input_model=input_model,
        )
        if connector_health is None:
            return ActionPolicyOutcome(
                connector_id=connector_id,
                risk_class=risk_class,
                policy_decision=ActionPolicyDecision.REJECT,
                approval_state=ActionApprovalState.NOT_REQUIRED,
                detail="connector_missing",
            )
        if not connector_health.supported:
            return ActionPolicyOutcome(
                connector_id=connector_id,
                risk_class=risk_class,
                policy_decision=ActionPolicyDecision.REJECT,
                approval_state=ActionApprovalState.NOT_REQUIRED,
                detail="connector_unsupported",
            )
        if not connector_health.configured:
            return ActionPolicyOutcome(
                connector_id=connector_id,
                risk_class=risk_class,
                policy_decision=ActionPolicyDecision.REJECT,
                approval_state=ActionApprovalState.NOT_REQUIRED,
                detail="connector_unconfigured",
            )
        if risk_class in {ActionRiskClass.EXTERNAL_SIDE_EFFECT, ActionRiskClass.IRREVERSIBLE_OR_HIGH_RISK}:
            return ActionPolicyOutcome(
                connector_id=connector_id,
                risk_class=risk_class,
                policy_decision=ActionPolicyDecision.REJECT,
                approval_state=ActionApprovalState.NOT_REQUIRED,
                detail="risk_class_rejected",
            )
        if risk_class == ActionRiskClass.LOW_RISK_LOCAL_WRITE:
            if invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME:
                return ActionPolicyOutcome(
                    connector_id=connector_id,
                    risk_class=risk_class,
                    policy_decision=ActionPolicyDecision.PREVIEW_ONLY,
                    approval_state=ActionApprovalState.NOT_REQUIRED,
                    detail="proactive_local_write_preview_only",
                )
            return ActionPolicyOutcome(
                connector_id=connector_id,
                risk_class=risk_class,
                policy_decision=ActionPolicyDecision.ALLOW,
                approval_state=ActionApprovalState.NOT_REQUIRED,
                detail="local_write_allowed",
            )
        if risk_class == ActionRiskClass.OPERATOR_SENSITIVE_WRITE:
            if invocation_origin == ActionInvocationOrigin.OPERATOR_CONSOLE:
                return ActionPolicyOutcome(
                    connector_id=connector_id,
                    risk_class=risk_class,
                    policy_decision=ActionPolicyDecision.ALLOW,
                    approval_state=ActionApprovalState.IMPLICIT_OPERATOR_APPROVAL,
                    detail="implicit_operator_approval",
                )
            return ActionPolicyOutcome(
                connector_id=connector_id,
                risk_class=risk_class,
                policy_decision=ActionPolicyDecision.REQUIRE_APPROVAL,
                approval_state=ActionApprovalState.PENDING,
                detail="operator_approval_required",
            )
        if risk_class == ActionRiskClass.READ_ONLY:
            return ActionPolicyOutcome(
                connector_id=connector_id,
                risk_class=risk_class,
                policy_decision=ActionPolicyDecision.ALLOW,
                approval_state=ActionApprovalState.NOT_REQUIRED,
                detail="read_only_allowed",
            )
        return ActionPolicyOutcome(
            connector_id=connector_id,
            risk_class=risk_class,
            policy_decision=ActionPolicyDecision.REJECT,
            approval_state=ActionApprovalState.NOT_REQUIRED,
            detail="policy_default_reject",
        )


__all__ = ["ActionPolicyEngine"]
