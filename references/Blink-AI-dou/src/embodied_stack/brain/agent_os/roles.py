from __future__ import annotations

import re
from dataclasses import replace

from embodied_stack.brain.llm import DialogueContext, DialogueEngine
from embodied_stack.shared.models import (
    AgentValidationStatus,
    InstructionLayerRecord,
    SkillActivationRecord,
    SpecialistRoleDecisionRecord,
    TypedToolCallRecord,
    ValidationOutcomeRecord,
)

from .action_policy import EmbodiedActionPolicy
from .models import AgentTurnContext, ReplyCandidatePlan


_VISUAL_CERTAINTY_PATTERNS = (
    re.compile(r"\bi can see\b", re.IGNORECASE),
    re.compile(r"\bi see\b", re.IGNORECASE),
    re.compile(r"\bit looks like\b", re.IGNORECASE),
    re.compile(r"\bi'?m looking at\b", re.IGNORECASE),
)


class PerceptionAnalystRole:
    role_name = "perception_analyst"

    def analyze(self, context: AgentTurnContext) -> SpecialistRoleDecisionRecord:
        snapshot = context.latest_perception
        if snapshot is None:
            return SpecialistRoleDecisionRecord(
                role_name=self.role_name,
                summary="perception_unavailable",
                notes=["no_snapshot"],
            )
        return SpecialistRoleDecisionRecord(
            role_name=self.role_name,
            summary=f"{snapshot.provider_mode.value}:{snapshot.status.value}",
            notes=[
                f"limited_awareness={snapshot.limited_awareness}",
                f"scene_summary={snapshot.scene_summary or 'none'}",
            ],
            metadata={
                "provider_mode": snapshot.provider_mode.value,
                "status": snapshot.status.value,
                "limited_awareness": snapshot.limited_awareness,
            },
        )


class DialoguePlannerRole:
    role_name = "dialogue_planner"

    def __init__(self, *, dialogue_engine: DialogueEngine) -> None:
        self.dialogue_engine = dialogue_engine

    def plan(
        self,
        *,
        context: AgentTurnContext,
        tool_invocations: list[object],
        venue_context: str | None,
        active_skill: SkillActivationRecord,
        instruction_layers: list[InstructionLayerRecord],
        typed_tool_calls: list[TypedToolCallRecord],
    ) -> tuple[ReplyCandidatePlan, SpecialistRoleDecisionRecord]:
        dialogue_context = DialogueContext(
            session=context.session,
            world_state=context.world_state,
            tool_invocations=tool_invocations,
            context_mode=context.context_mode,
            user_memory=context.user_memory,
            latest_perception=context.latest_perception,
            world_model=context.world_model,
            venue_context=venue_context,
            active_skill=active_skill,
            instruction_layers=instruction_layers,
            typed_tool_calls=typed_tool_calls,
        )
        result = self.dialogue_engine.generate_reply(context.text, dialogue_context)
        candidate = ReplyCandidatePlan.from_dialogue_result(result)
        return (
            candidate,
            SpecialistRoleDecisionRecord(
                role_name=self.role_name,
                backend=result.engine_name,
                summary=f"intent={result.intent}",
                notes=[
                    f"fallback_used={result.fallback_used}",
                    f"typed_tools={len(typed_tool_calls)}",
                ],
            ),
        )


class SafetyPolicyReviewerRole:
    role_name = "safety_reviewer"

    def __init__(self, *, action_policy: EmbodiedActionPolicy) -> None:
        self.action_policy = action_policy

    def review(
        self,
        *,
        context: AgentTurnContext,
        active_skill: SkillActivationRecord,
        candidate: ReplyCandidatePlan,
    ) -> tuple[ReplyCandidatePlan, list[ValidationOutcomeRecord], SpecialistRoleDecisionRecord]:
        reviewed = replace(candidate)
        outcomes = list(self.action_policy.validate_commands(reviewed.commands))
        review_notes: list[str] = []

        if any(item.status == AgentValidationStatus.BLOCKED for item in outcomes):
            reviewed = self._downgrade_candidate(
                reviewed,
                reply_text=(
                    "I am keeping my body behavior in a safe semantic mode right now. "
                    "I can still help with directions, events, feedback, or a human handoff."
                ),
                intent="safe_degraded_response",
            )
            outcomes.append(
                ValidationOutcomeRecord(
                    validator_name="semantic_body_policy",
                    status=AgentValidationStatus.DOWNGRADED,
                    detail="unsafe_command_plan_replaced",
                    downgraded=True,
                )
            )
            review_notes.append("unsafe_command_plan_replaced")

        matched_claims = [
            claim
            for claim in active_skill.forbidden_claims
            if reviewed.reply_text and claim.lower() in reviewed.reply_text.lower()
        ]
        if matched_claims:
            reviewed = self._downgrade_candidate(
                reviewed,
                reply_text=(
                    "I should stay within confirmed capabilities. "
                    "I can give directions, answer venue questions, capture feedback, or connect you to staff."
                ),
                intent="safe_degraded_response",
            )
            outcomes.append(
                ValidationOutcomeRecord(
                    validator_name="skill_claim_policy",
                    status=AgentValidationStatus.DOWNGRADED,
                    detail="forbidden_claim_detected",
                    downgraded=True,
                    notes=matched_claims,
                )
            )
            review_notes.append("forbidden_claim_detected")

        if self._requires_visual_honesty_downgrade(context, reviewed):
            reviewed = self._downgrade_candidate(
                reviewed,
                reply_text=(
                    "My current visual awareness is limited, so I should not claim a confident scene read. "
                    "I can still help with directions, events, feedback, or a human handoff."
                ),
                intent="safe_degraded_response",
            )
            outcomes.append(
                ValidationOutcomeRecord(
                    validator_name="perception_honesty_policy",
                    status=AgentValidationStatus.DOWNGRADED,
                    detail="limited_awareness_visual_claim",
                    downgraded=True,
                )
            )
            review_notes.append("limited_awareness_visual_claim")

        if not review_notes:
            outcomes.append(
                ValidationOutcomeRecord(
                    validator_name="reply_review_policy",
                    status=AgentValidationStatus.APPROVED,
                    detail="candidate_plan_approved",
                )
            )

        return (
            reviewed,
            outcomes,
            SpecialistRoleDecisionRecord(
                role_name=self.role_name,
                summary="downgraded" if review_notes else "approved",
                notes=review_notes or ["candidate_plan_approved"],
            ),
        )

    def _requires_visual_honesty_downgrade(
        self,
        context: AgentTurnContext,
        candidate: ReplyCandidatePlan,
    ) -> bool:
        if not candidate.reply_text:
            return False
        snapshot = context.latest_perception
        limited_awareness = snapshot is None or snapshot.limited_awareness or snapshot.status.value != "ok"
        if not limited_awareness:
            return False
        return any(pattern.search(candidate.reply_text) for pattern in _VISUAL_CERTAINTY_PATTERNS)

    def _downgrade_candidate(
        self,
        candidate: ReplyCandidatePlan,
        *,
        reply_text: str,
        intent: str,
    ) -> ReplyCandidatePlan:
        downgraded = replace(candidate, reply_text=reply_text, intent=intent)
        downgraded.commands = self.action_policy.build_commands(intent, reply_text)
        return downgraded


class MemoryCuratorRole:
    role_name = "memory_curator"

    def curate(
        self,
        *,
        context: AgentTurnContext,
        memory_updates: dict[str, str],
    ) -> SpecialistRoleDecisionRecord:
        del context
        if not memory_updates:
            return SpecialistRoleDecisionRecord(
                role_name=self.role_name,
                summary="no_memory_updates",
            )
        return SpecialistRoleDecisionRecord(
            role_name=self.role_name,
            summary=f"memory_updates={','.join(sorted(memory_updates))}",
            notes=[f"{key}={value}" for key, value in sorted(memory_updates.items())],
        )


class ReflectionRole:
    role_name = "tool_result_summarizer"

    def reflect(
        self,
        *,
        candidate: ReplyCandidatePlan,
        validation_outcomes: list[ValidationOutcomeRecord],
        provider_failure_active: bool,
    ) -> SpecialistRoleDecisionRecord:
        degraded = provider_failure_active or any(
            outcome.status in {AgentValidationStatus.DOWNGRADED, AgentValidationStatus.BLOCKED}
            for outcome in validation_outcomes
        )
        return SpecialistRoleDecisionRecord(
            role_name=self.role_name,
            summary="status=degraded" if degraded else "status=clean",
            notes=[
                f"intent={candidate.intent}",
                f"validation_count={len(validation_outcomes)}",
            ],
        )


class EmbodimentPlannerRole:
    role_name = "embodiment_planner"

    def review(self, *, candidate: ReplyCandidatePlan) -> SpecialistRoleDecisionRecord:
        return SpecialistRoleDecisionRecord(
            role_name=self.role_name,
            summary=f"intent={candidate.intent}",
            notes=[f"command_count={len(candidate.commands)}"],
        )


class OperatorHandoffPlannerRole:
    role_name = "operator_handoff_planner"

    def plan(
        self,
        *,
        active_skill: SkillActivationRecord,
        typed_tool_calls: list[TypedToolCallRecord],
    ) -> SpecialistRoleDecisionRecord:
        return SpecialistRoleDecisionRecord(
            role_name=self.role_name,
            summary=active_skill.skill_name,
            notes=[f"typed_tools={len(typed_tool_calls)}"],
        )
