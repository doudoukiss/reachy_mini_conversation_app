from __future__ import annotations

from dataclasses import dataclass, field

from embodied_stack.brain.llm import DialogueResult
from embodied_stack.shared.models import (
    CheckpointRecord,
    CompanionContextMode,
    EmbodiedWorldModel,
    HookExecutionRecord,
    InstructionLayerRecord,
    PerceptionSnapshotRecord,
    RobotCommand,
    RobotEvent,
    RunRecord,
    RuntimeBackendStatus,
    SessionRecord,
    SkillActivationRecord,
    SpecialistRoleDecisionRecord,
    TypedToolCallRecord,
    UserMemoryRecord,
    ValidationOutcomeRecord,
    WorldState,
)


@dataclass(frozen=True)
class LoadedInstruction:
    record: InstructionLayerRecord
    content: str


@dataclass
class AgentTurnContext:
    text: str
    event: RobotEvent
    session: SessionRecord
    context_mode: CompanionContextMode
    user_memory: UserMemoryRecord | None
    world_state: WorldState
    world_model: EmbodiedWorldModel
    latest_perception: PerceptionSnapshotRecord | None
    backend_status: list[RuntimeBackendStatus]
    replayed_from_run_id: str | None = None
    resumed_from_checkpoint_id: str | None = None


@dataclass
class ReplyCandidatePlan:
    reply_text: str | None
    intent: str
    engine_name: str
    fallback_used: bool = False
    debug_notes: list[str] = field(default_factory=list)
    commands: list[RobotCommand] = field(default_factory=list)

    @classmethod
    def from_dialogue_result(cls, result: DialogueResult) -> "ReplyCandidatePlan":
        return cls(
            reply_text=result.reply_text,
            intent=result.intent,
            engine_name=result.engine_name,
            fallback_used=result.fallback_used,
            debug_notes=list(result.debug_notes),
        )


@dataclass
class AgentTurnPlan:
    reply_text: str | None
    intent: str
    engine_name: str
    fallback_used: bool
    commands: list[RobotCommand]
    active_skill: SkillActivationRecord
    active_subagent: str | None = None
    run_record: RunRecord | None = None
    checkpoints: list[CheckpointRecord] = field(default_factory=list)
    instruction_layers: list[InstructionLayerRecord] = field(default_factory=list)
    typed_tool_calls: list[TypedToolCallRecord] = field(default_factory=list)
    hook_records: list[HookExecutionRecord] = field(default_factory=list)
    role_decisions: list[SpecialistRoleDecisionRecord] = field(default_factory=list)
    validation_outcomes: list[ValidationOutcomeRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AgentEventAudit:
    run_record: RunRecord | None = None
    checkpoints: list[CheckpointRecord] = field(default_factory=list)
    instruction_layers: list[InstructionLayerRecord] = field(default_factory=list)
    active_skill: SkillActivationRecord | None = None
    active_subagent: str | None = None
    typed_tool_calls: list[TypedToolCallRecord] = field(default_factory=list)
    hook_records: list[HookExecutionRecord] = field(default_factory=list)
    role_decisions: list[SpecialistRoleDecisionRecord] = field(default_factory=list)
    validation_outcomes: list[ValidationOutcomeRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
