from __future__ import annotations

import logging
from pathlib import Path

from embodied_stack.action_plane import ActionPlaneGateway
from embodied_stack.action_plane.models import ActionInvocationContext
from embodied_stack.action_plane.workflows import WorkflowRuntime
from embodied_stack.demo.action_replay import ActionReplayHarness
from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.agent_os.checkpoints import ActiveRunState, RunTracker
from embodied_stack.brain.agent_os.registry import AgentOSRegistry
from embodied_stack.brain.agent_os.subagents import SubagentRegistry
from embodied_stack.brain.agent_os.trace_store import AgentOSTraceStore
from embodied_stack.brain.agent_os.tools import AgentToolRegistry, ToolRuntimeContext
from embodied_stack.brain.agent_os.roles import (
    DialoguePlannerRole,
    EmbodimentPlannerRole,
    MemoryCuratorRole,
    OperatorHandoffPlannerRole,
    PerceptionAnalystRole,
    ReflectionRole,
    SafetyPolicyReviewerRole,
)
from embodied_stack.brain.llm import DialogueEngine
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.config import Settings
from embodied_stack.observability import log_event
from embodied_stack.shared.models import (
    ActionApprovalListResponse,
    ActionApprovalResolutionRecord,
    ActionBundleDetailRecord,
    ActionBundleListResponse,
    ActionInvocationOrigin,
    ActionReplayRequestRecord,
    ActionReplayRecord,
    ActionPlaneStatus,
    AgentHookName,
    BrowserRuntimeStatusRecord,
    CheckpointListResponse,
    CheckpointRecord,
    CheckpointKind,
    CommandType,
    CompanionContextMode,
    EmbodiedWorldModel,
    FallbackClassification,
    InteractionExecutiveState,
    ConnectorCatalogResponse,
    SessionRecord,
    WorkflowCatalogResponse,
    WorkflowRunActionRequestRecord,
    WorkflowRunActionResponseRecord,
    WorkflowRunListResponse,
    WorkflowStartRequestRecord,
    RunPhase,
    RunRecord,
    ActionExecutionListResponse,
    RunExportArtifact,
    SkillActivationRecord,
    SpecialistRoleDecisionRecord,
    ToolInvocationRecord,
    TypedToolCallRecord,
    WorldState,
)

from .action_policy import EmbodiedActionPolicy
from .hooks import HookRegistry, HookRuntimeState
from .instructions import InstructionBundleLoader
from .models import AgentEventAudit, AgentTurnContext, AgentTurnPlan
from .skills import SkillRegistry

logger = logging.getLogger(__name__)


class AgentRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        backend_router: BackendRouter,
        knowledge_tools: KnowledgeToolbox,
        dialogue_engine: DialogueEngine,
        action_policy: EmbodiedActionPolicy,
        memory_store: MemoryStore | None = None,
        instruction_loader: InstructionBundleLoader | None = None,
        skill_registry: SkillRegistry | None = None,
        subagent_registry: SubagentRegistry | None = None,
        hook_registry: HookRegistry | None = None,
        tool_registry: AgentToolRegistry | None = None,
        trace_store: AgentOSTraceStore | None = None,
        run_tracker: RunTracker | None = None,
        action_gateway: ActionPlaneGateway | None = None,
    ) -> None:
        self.settings = settings
        self.backend_router = backend_router
        self.knowledge_tools = knowledge_tools
        self.dialogue_engine = dialogue_engine
        self.action_policy = action_policy
        self.memory_store = memory_store
        self.instruction_loader = instruction_loader or InstructionBundleLoader(settings=settings)
        self.skill_registry = skill_registry or SkillRegistry()
        self.subagent_registry = subagent_registry or SubagentRegistry()
        self.hook_registry = hook_registry or HookRegistry()
        self.tool_registry = tool_registry or AgentToolRegistry()
        default_trace_root = Path(settings.brain_store_path).resolve().parent / "agent_os"
        default_action_root = Path(settings.brain_store_path).resolve().parent / "actions"
        self.trace_store = trace_store or AgentOSTraceStore(str(default_trace_root))
        self.run_tracker = run_tracker or RunTracker(self.trace_store)
        self.action_gateway = action_gateway or ActionPlaneGateway(root_dir=default_action_root, settings=settings)
        self.workflow_runtime = WorkflowRuntime(
            root_dir=default_action_root,
            settings=settings,
            tool_registry=self.tool_registry,
            action_gateway=self.action_gateway,
            body_feedback_callback=self._emit_workflow_body_feedback,
        )
        self.action_gateway.reconcile_restart_review()
        self.workflow_runtime.reconcile_restart_review()
        self.registry = AgentOSRegistry(
            skills=self.skill_registry,
            hooks=self.hook_registry,
            tools=self.tool_registry,
            subagents=self.subagent_registry,
        )
        self.perception_analyst = PerceptionAnalystRole()
        self.dialogue_planner = DialoguePlannerRole(dialogue_engine=dialogue_engine)
        self.safety_reviewer = SafetyPolicyReviewerRole(action_policy=action_policy)
        self.memory_curator = MemoryCuratorRole()
        self.embodiment_planner = EmbodimentPlannerRole()
        self.operator_handoff_planner = OperatorHandoffPlannerRole()
        self.reflection = ReflectionRole()

    def registered_skills(self) -> list[str]:
        return self.skill_registry.list_skill_names()

    def registered_subagents(self) -> list[str]:
        return self.subagent_registry.list_subagent_names()

    def registered_hooks(self) -> list[str]:
        return self.hook_registry.list_hook_names()

    def registered_tools(self) -> list[str]:
        return self.tool_registry.list_tool_names()

    def specialist_roles(self) -> list[str]:
        return self.subagent_registry.list_role_names()

    def action_plane_status(self) -> ActionPlaneStatus:
        status = self.action_gateway.status()
        workflow_summary = self.workflow_runtime.summary_status()
        return status.model_copy(
            update={
                **workflow_summary,
                "review_required_count": status.review_required_count + int(workflow_summary.get("review_required_count", 0)),
            }
        )

    def action_plane_connectors(self) -> ConnectorCatalogResponse:
        return self.action_gateway.list_connectors()

    def action_plane_browser_status(self, *, session_id: str | None = None) -> BrowserRuntimeStatusRecord:
        return self.action_gateway.browser_status(session_id=session_id)

    def action_plane_approvals(self) -> ActionApprovalListResponse:
        return self.action_gateway.list_pending_approvals()

    def action_plane_history(self, *, limit: int = 50) -> ActionExecutionListResponse:
        return self.action_gateway.list_execution_history(limit=limit)

    def action_plane_bundles(self, *, session_id: str | None = None, limit: int = 50) -> ActionBundleListResponse:
        return self.action_gateway.list_action_bundles(limit=limit, session_id=session_id)

    def action_plane_bundle(self, bundle_id: str) -> ActionBundleDetailRecord | None:
        return self.action_gateway.get_action_bundle(bundle_id)

    def action_plane_replays(self, *, session_id: str | None = None, limit: int = 25) -> list[ActionReplayRecord]:
        return self.action_gateway.list_action_replays(session_id=session_id, limit=limit)

    def action_plane_workflows(self) -> WorkflowCatalogResponse:
        return self.workflow_runtime.list_definitions()

    def action_plane_workflow_runs(self, *, session_id: str | None = None, limit: int = 50) -> WorkflowRunListResponse:
        return self.workflow_runtime.list_runs(session_id=session_id, limit=limit)

    def action_plane_workflow_run(self, workflow_run_id: str):
        return self.workflow_runtime.get_run(workflow_run_id)

    def start_action_plane_workflow(
        self,
        *,
        request: WorkflowStartRequestRecord,
        tool_context: ToolRuntimeContext,
    ) -> WorkflowRunActionResponseRecord:
        return self.workflow_runtime.start_workflow(request=request, tool_context=tool_context)

    def resume_action_plane_workflow(
        self,
        *,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
        tool_context: ToolRuntimeContext,
    ) -> WorkflowRunActionResponseRecord:
        return self.workflow_runtime.resume_workflow(
            workflow_run_id=workflow_run_id,
            request=request,
            tool_context=tool_context,
        )

    def retry_action_plane_workflow(
        self,
        *,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
        tool_context: ToolRuntimeContext,
    ) -> WorkflowRunActionResponseRecord:
        return self.workflow_runtime.retry_workflow_step(
            workflow_run_id=workflow_run_id,
            request=request,
            tool_context=tool_context,
        )

    def pause_action_plane_workflow(
        self,
        *,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
    ) -> WorkflowRunActionResponseRecord:
        return self.workflow_runtime.pause_workflow(
            workflow_run_id=workflow_run_id,
            request=request,
        )

    def evaluate_action_plane_workflow_triggers(
        self,
        *,
        tool_context: ToolRuntimeContext,
        shift_snapshot,
        now=None,
    ) -> list[WorkflowRunActionResponseRecord]:
        return self.workflow_runtime.evaluate_due_triggers(
            tool_context=tool_context,
            shift_snapshot=shift_snapshot,
            now=now,
        )

    def resolve_action_plane_approval(
        self,
        *,
        action_id: str,
        approve: bool,
        operator_note: str | None,
        tool_context: ToolRuntimeContext,
    ) -> ActionApprovalResolutionRecord:
        if approve:
            resolution = self.action_gateway.approve_action(
                action_id=action_id,
                operator_note=operator_note,
                handler_context=tool_context,
            )
            self.workflow_runtime.handle_action_resolution(resolution=resolution, tool_context=tool_context)
            return resolution
        resolution = self.action_gateway.reject_action(
            action_id=action_id,
            operator_note=operator_note,
            handler_context=tool_context,
        )
        self.workflow_runtime.handle_action_resolution(resolution=resolution, tool_context=tool_context)
        return resolution

    def replay_action_plane_action(
        self,
        *,
        replay: ActionReplayRequestRecord,
        tool_context: ToolRuntimeContext,
    ) -> ActionInvocationResult:
        previous = self.action_gateway.get_execution(replay.action_id)
        if previous is None:
            raise KeyError(f"action not found for replay: {replay.action_id}")
        spec = self.tool_registry.resolve_spec(previous.tool_name)
        input_model = spec.input_model.model_validate(previous.input_payload)
        return self.action_gateway.replay_action(
            replay=replay,
            tool_name=previous.tool_name,
            requested_tool_name=previous.tool_name,
            input_model=input_model,
            handler_context=tool_context,
            invocation=ActionInvocationContext(
                session_id=tool_context.session.session_id,
                run_id=tool_context.run_id,
                workflow_run_id=tool_context.workflow_run_id,
                workflow_step_id=tool_context.workflow_step_id,
                context_mode=tool_context.context_mode.value,
                body_mode=tool_context.body_driver_mode,
                invocation_origin=tool_context.action_invocation_origin,
            ),
        )

    def replay_action_plane_bundle(self, *, replay: ActionReplayRequestRecord) -> ActionReplayRecord:
        harness = ActionReplayHarness.from_settings(settings=self.settings)
        return harness.replay_bundle(replay)

    def list_runs(self, *, session_id: str | None = None, limit: int = 50):
        return self.trace_store.list_runs(session_id=session_id, limit=limit)

    def get_run(self, run_id: str) -> RunRecord | None:
        return self.trace_store.get_run(run_id)

    def list_checkpoints(self, *, run_id: str | None = None, limit: int = 100) -> CheckpointListResponse:
        return self.trace_store.list_checkpoints(run_id=run_id, limit=limit)

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord | None:
        return self.trace_store.get_checkpoint(checkpoint_id)

    def get_run_for_trace(self, trace_id: str) -> RunRecord | None:
        return self.trace_store.find_run_by_trace_id(trace_id)

    def pause_run(self, run_id: str, *, reason: str) -> RunRecord | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        active = ActiveRunState(run=run, checkpoints=self.list_checkpoints(run_id=run_id, limit=500).items[::-1])
        return self.run_tracker.pause(active, reason=reason, recovery_notes=[reason])

    def resume_run(self, run_id: str, *, note: str | None = None) -> RunRecord | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        active = ActiveRunState(run=run, checkpoints=self.list_checkpoints(run_id=run_id, limit=500).items[::-1])
        return self.run_tracker.resume(active, checkpoint_id=run.paused_from_checkpoint_id, note=note)

    def abort_run(self, run_id: str, *, reason: str) -> RunRecord | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        active = ActiveRunState(run=run, checkpoints=self.list_checkpoints(run_id=run_id, limit=500).items[::-1])
        return self.run_tracker.abort(active, reason=reason)

    def attach_trace(self, run_id: str | None, trace_id: str) -> RunRecord | None:
        if run_id is None:
            return None
        run = self.trace_store.get_run(run_id)
        if run is None:
            return None
        active = ActiveRunState(run=run, checkpoints=self.list_checkpoints(run_id=run_id, limit=200).items[::-1])
        return self.run_tracker.attach_trace(active, trace_id)

    def plan_speech_turn(
        self,
        *,
        context: AgentTurnContext,
        tool_invocations: list[ToolInvocationRecord],
        memory_updates: dict[str, str],
    ) -> AgentTurnPlan:
        provider_failure_active = self._provider_failure_active(context)
        active_run = self.run_tracker.start_run(
            session_id=context.session.session_id,
            event=context.event,
            provider_failure_active=provider_failure_active,
            replayed_from_run_id=context.replayed_from_run_id,
            resumed_from_checkpoint_id=context.resumed_from_checkpoint_id,
            notes=["speech_turn"],
        )
        log_event(
            logger,
            logging.INFO,
            "agent_turn_started",
            run_id=active_run.run.run_id,
            session_id=context.session.session_id,
            event_id=context.event.event_id,
            provider_failure_active=provider_failure_active,
        )
        try:
            self.run_tracker.advance(active_run, phase=RunPhase.INSTRUCTION_LOAD)
            instruction_layers = [
                item.record
                for item in self.instruction_loader.load(
                    session=context.session,
                    user_memory=context.user_memory,
                )
            ]
            self.run_tracker.advance(
                active_run,
                phase=RunPhase.SKILL_SELECTION,
                note=f"instruction_layers={len(instruction_layers)}",
            )
            hook_records = self.hook_registry.run(
                AgentHookName.BEFORE_SKILL_SELECTION,
                context=context,
                state=HookRuntimeState(
                    provider_failure_active=provider_failure_active,
                    run_id=active_run.run.run_id,
                ),
            )
            active_skill = self.skill_registry.resolve(
                text=context.text,
                session=context.session,
                context_mode=context.context_mode,
                latest_perception=context.latest_perception,
                provider_failure_active=provider_failure_active,
            )
            self.run_tracker.advance(
                active_run,
                phase=RunPhase.SKILL_SELECTION,
                active_skill=active_skill.skill_name,
                active_playbook=active_skill.playbook_name,
                active_playbook_variant=active_skill.route_variant,
            )
            hook_records.extend(
                self.hook_registry.run(
                    AgentHookName.AFTER_TRANSCRIPT,
                    context=context,
                    state=HookRuntimeState(
                        active_skill_name=active_skill.skill_name,
                        provider_failure_active=provider_failure_active,
                        run_id=active_run.run.run_id,
                    ),
                )
            )

            selected_subagent = self.subagent_registry.resolve(active_skill)
            self.run_tracker.advance(
                active_run,
                phase=RunPhase.SUBAGENT_SELECTION,
                active_skill=active_skill.skill_name,
                active_playbook=active_skill.playbook_name,
                active_playbook_variant=active_skill.route_variant,
                active_subagent=selected_subagent.name,
            )
            role_decisions = [
                self.perception_analyst.analyze(context),
                self._subagent_selection_record(selected_subagent.name),
            ]
            if context.latest_perception is not None:
                hook_records.extend(
                    self.hook_registry.run(
                        AgentHookName.AFTER_PERCEPTION,
                        context=context,
                        state=HookRuntimeState(
                            active_skill_name=active_skill.skill_name,
                            active_subagent_name=selected_subagent.name,
                            provider_failure_active=provider_failure_active,
                            run_id=active_run.run.run_id,
                        ),
                    )
                )

            typed_tool_calls, tool_hook_records = self._invoke_required_tools(
                active_run=active_run,
                active_skill=active_skill,
                active_subagent_name=selected_subagent.name,
                context=context,
                tool_invocations=tool_invocations,
            )
            hook_records.extend(tool_hook_records)
            hook_records.extend(
                self.hook_registry.run(
                    AgentHookName.BEFORE_REPLY,
                    context=context,
                    state=HookRuntimeState(
                        active_skill_name=active_skill.skill_name,
                        active_subagent_name=selected_subagent.name,
                        tool_count=len(typed_tool_calls),
                        provider_failure_active=provider_failure_active,
                        run_id=active_run.run.run_id,
                    ),
                )
            )

            self.run_tracker.advance(
                active_run,
                phase=RunPhase.REPLY_PLANNING,
                active_skill=active_skill.skill_name,
                active_playbook=active_skill.playbook_name,
                active_playbook_variant=active_skill.route_variant,
                active_subagent=selected_subagent.name,
            )
            candidate, planner_decision = self.dialogue_planner.plan(
                context=context,
                tool_invocations=tool_invocations,
                venue_context=self.knowledge_tools.contextual_venue_overview(
                    text=context.text,
                    session=context.session,
                ),
                active_skill=active_skill,
                instruction_layers=instruction_layers,
                typed_tool_calls=typed_tool_calls,
            )
            role_decisions.append(planner_decision)

            action_call, action_hooks = self._invoke_single_tool(
                active_run=active_run,
                tool_name="body_preview",
                payload={"intent": candidate.intent, "reply_text": candidate.reply_text},
                context=context,
                tool_invocations=tool_invocations,
                active_skill=active_skill,
                active_subagent_name="embodiment_planner",
            )
            typed_tool_calls.append(action_call)
            hook_records.extend(action_hooks)
            candidate.commands = self.action_policy.build_commands(candidate.intent, candidate.reply_text)
            role_decisions.append(self.embodiment_planner.review(candidate=candidate))

            self.run_tracker.advance(
                active_run,
                phase=RunPhase.VALIDATION,
                intent=candidate.intent,
                reply_text=candidate.reply_text,
            )
            candidate, validation_outcomes, reviewer_decision = self.safety_reviewer.review(
                context=context,
                active_skill=active_skill,
                candidate=candidate,
            )
            role_decisions.append(reviewer_decision)
            if active_skill.skill_name == "incident_escalation":
                role_decisions.append(
                    self.operator_handoff_planner.plan(
                        active_skill=active_skill,
                        typed_tool_calls=typed_tool_calls,
                    )
                )

            hook_records.extend(
                self.hook_registry.run(
                    AgentHookName.BEFORE_SPEAK,
                    context=context,
                    state=HookRuntimeState(
                        active_skill_name=active_skill.skill_name,
                        active_subagent_name=selected_subagent.name,
                        tool_count=len(typed_tool_calls),
                        validation_count=len(validation_outcomes),
                        provider_failure_active=provider_failure_active,
                        reply_candidate=candidate,
                        run_id=active_run.run.run_id,
                    ),
                )
            )

            safe_idle_active = self._safe_idle_active(context, candidate)
            if provider_failure_active:
                hook_records.extend(
                    self.hook_registry.run(
                        AgentHookName.ON_FAILURE,
                        context=context,
                        state=HookRuntimeState(
                            active_skill_name=active_skill.skill_name,
                            active_subagent_name=selected_subagent.name,
                            provider_failure_active=True,
                            reply_candidate=candidate,
                            run_id=active_run.run.run_id,
                        ),
                    )
                )
            if safe_idle_active:
                hook_records.extend(
                    self.hook_registry.run(
                        AgentHookName.ON_SAFE_IDLE,
                        context=context,
                        state=HookRuntimeState(
                            active_skill_name=active_skill.skill_name,
                            active_subagent_name=selected_subagent.name,
                            safe_idle_active=True,
                            provider_failure_active=provider_failure_active,
                            reply_candidate=candidate,
                            run_id=active_run.run.run_id,
                        ),
                    )
                )

            role_decisions.append(self.memory_curator.curate(context=context, memory_updates=memory_updates))
            role_decisions.append(
                self.reflection.reflect(
                    candidate=candidate,
                    validation_outcomes=validation_outcomes,
                    provider_failure_active=provider_failure_active,
                )
            )

            self.run_tracker.advance(
                active_run,
                phase=RunPhase.COMMAND_EMISSION,
                intent=candidate.intent,
                reply_text=candidate.reply_text,
                fallback_reason=self._fallback_reason(candidate, provider_failure_active, validation_outcomes),
                fallback_classification=self._fallback_classification(
                    candidate=candidate,
                    provider_failure_active=provider_failure_active,
                    validation_outcomes=validation_outcomes,
                    typed_tool_calls=typed_tool_calls,
                ),
                unavailable_capabilities=self._unavailable_capabilities(typed_tool_calls),
                intentionally_skipped_capabilities=self._intentionally_skipped_capabilities(
                    active_skill=active_skill,
                    typed_tool_calls=typed_tool_calls,
                ),
            )
            completed_run = self.run_tracker.complete(
                active_run,
                intent=candidate.intent,
                reply_text=candidate.reply_text,
                command_types=[command.command_type for command in candidate.commands],
                fallback_reason=self._fallback_reason(candidate, provider_failure_active, validation_outcomes),
                fallback_classification=self._fallback_classification(
                    candidate=candidate,
                    provider_failure_active=provider_failure_active,
                    validation_outcomes=validation_outcomes,
                    typed_tool_calls=typed_tool_calls,
                ),
            )

            plan = AgentTurnPlan(
                reply_text=candidate.reply_text,
                intent=candidate.intent,
                engine_name=candidate.engine_name,
                fallback_used=candidate.fallback_used,
                commands=list(candidate.commands),
                active_skill=active_skill,
                active_subagent=selected_subagent.name,
                run_record=completed_run,
                checkpoints=list(active_run.checkpoints),
                instruction_layers=instruction_layers,
                typed_tool_calls=typed_tool_calls,
                hook_records=hook_records,
                role_decisions=role_decisions,
                validation_outcomes=validation_outcomes,
                notes=list(candidate.debug_notes),
            )
            plan.hook_records.extend(
                self.hook_registry.run(
                    AgentHookName.AFTER_TURN,
                    context=context,
                    state=HookRuntimeState(
                        active_skill_name=active_skill.skill_name,
                        active_subagent_name=selected_subagent.name,
                        tool_count=len(typed_tool_calls),
                        validation_count=len(validation_outcomes),
                        provider_failure_active=provider_failure_active,
                        safe_idle_active=safe_idle_active,
                        reply_candidate=candidate,
                        final_plan=plan,
                        run_id=active_run.run.run_id,
                        checkpoint_id=active_run.last_checkpoint_id,
                    ),
                )
            )
            log_event(
                logger,
                logging.INFO,
                "agent_turn_completed",
                run_id=completed_run.run_id,
                session_id=context.session.session_id,
                checkpoint_id=active_run.last_checkpoint_id,
                intent=plan.intent,
                active_skill=active_skill.skill_name,
                active_subagent=selected_subagent.name,
                tool_count=len(typed_tool_calls),
            )
            return plan
        except Exception as exc:
            self.run_tracker.fail(active_run, failure_state=exc.__class__.__name__, note=str(exc))
            log_event(
                logger,
                logging.ERROR,
                "agent_turn_failed",
                run_id=active_run.run.run_id,
                session_id=context.session.session_id,
                checkpoint_id=active_run.last_checkpoint_id,
                failure_state=exc.__class__.__name__,
            )
            raise

    def audit_event(
        self,
        *,
        context: AgentTurnContext,
        safe_idle_active: bool = False,
        preferred_skill_name: str | None = None,
    ) -> AgentEventAudit:
        provider_failure_active = self._provider_failure_active(context)
        active_run = self.run_tracker.start_run(
            session_id=context.session.session_id,
            event=context.event,
            provider_failure_active=provider_failure_active,
            replayed_from_run_id=context.replayed_from_run_id,
            resumed_from_checkpoint_id=context.resumed_from_checkpoint_id,
            notes=["event_audit"],
        )
        instruction_layers = [
            item.record
            for item in self.instruction_loader.load(
                session=context.session,
                user_memory=context.user_memory,
            )
        ]
        self.run_tracker.advance(active_run, phase=RunPhase.SKILL_SELECTION)
        active_skill = self._resolve_audit_skill(
            context=context,
            safe_idle_active=safe_idle_active,
            provider_failure_active=provider_failure_active,
            preferred_skill_name=preferred_skill_name,
        )
        selected_subagent = self.subagent_registry.resolve(active_skill)
        self.run_tracker.advance(
            active_run,
            phase=RunPhase.SUBAGENT_SELECTION,
            active_skill=active_skill.skill_name,
            active_playbook=active_skill.playbook_name,
            active_playbook_variant=active_skill.route_variant,
            active_subagent=selected_subagent.name,
        )
        hook_records = self.hook_registry.run(
            AgentHookName.AFTER_TRANSCRIPT,
            context=context,
            state=HookRuntimeState(
                active_skill_name=active_skill.skill_name,
                active_subagent_name=selected_subagent.name,
                provider_failure_active=provider_failure_active,
                safe_idle_active=safe_idle_active,
                run_id=active_run.run.run_id,
            ),
        )
        role_decisions = [
            self.perception_analyst.analyze(context),
            self._subagent_selection_record(selected_subagent.name),
        ]
        if context.latest_perception is not None:
            hook_records.extend(
                self.hook_registry.run(
                    AgentHookName.AFTER_PERCEPTION,
                    context=context,
                    state=HookRuntimeState(
                        active_skill_name=active_skill.skill_name,
                        active_subagent_name=selected_subagent.name,
                        provider_failure_active=provider_failure_active,
                        run_id=active_run.run.run_id,
                    ),
                )
            )
        if provider_failure_active:
            hook_records.extend(
                self.hook_registry.run(
                    AgentHookName.ON_FAILURE,
                    context=context,
                    state=HookRuntimeState(
                        active_skill_name=active_skill.skill_name,
                        active_subagent_name=selected_subagent.name,
                        provider_failure_active=True,
                        run_id=active_run.run.run_id,
                    ),
                )
            )
        if safe_idle_active:
            hook_records.extend(
                self.hook_registry.run(
                    AgentHookName.ON_SAFE_IDLE,
                    context=context,
                    state=HookRuntimeState(
                        active_skill_name=active_skill.skill_name,
                        active_subagent_name=selected_subagent.name,
                        safe_idle_active=True,
                        provider_failure_active=provider_failure_active,
                        run_id=active_run.run.run_id,
                    ),
                )
            )
        completed_run = self.run_tracker.complete(
            active_run,
            intent=active_skill.skill_name,
            reply_text=None,
            command_types=[],
            fallback_reason="event_audit_only",
        )
        audit = AgentEventAudit(
            run_record=completed_run,
            checkpoints=list(active_run.checkpoints),
            instruction_layers=instruction_layers,
            active_skill=active_skill,
            active_subagent=selected_subagent.name,
            hook_records=hook_records,
            role_decisions=role_decisions,
            notes=["event_audit_only"],
        )
        audit.hook_records.extend(
            self.hook_registry.run(
                AgentHookName.AFTER_TURN,
                context=context,
                state=HookRuntimeState(
                    active_skill_name=active_skill.skill_name,
                    active_subagent_name=selected_subagent.name,
                    provider_failure_active=provider_failure_active,
                    safe_idle_active=safe_idle_active,
                    run_id=active_run.run.run_id,
                ),
            )
        )
        return audit

    def _invoke_required_tools(
        self,
        *,
        active_run: ActiveRunState,
        active_skill: SkillActivationRecord,
        active_subagent_name: str,
        context: AgentTurnContext,
        tool_invocations: list[ToolInvocationRecord],
    ) -> tuple[list[TypedToolCallRecord], list]:
        records: list[TypedToolCallRecord] = []
        hook_records: list = []
        for tool_name in dict.fromkeys(active_skill.required_tools):
            if tool_name == "body_preview":
                continue
            payload = self._payload_for_tool(
                tool_name=tool_name,
                context=context,
                active_skill=active_skill,
            )
            record, tool_hooks = self._invoke_single_tool(
                active_run=active_run,
                tool_name=tool_name,
                payload=payload,
                context=context,
                tool_invocations=tool_invocations,
                active_skill=active_skill,
                active_subagent_name=active_subagent_name,
            )
            records.append(record)
            hook_records.extend(tool_hooks)
        return records, hook_records

    def _invoke_single_tool(
        self,
        *,
        active_run: ActiveRunState,
        tool_name: str,
        payload: dict[str, object],
        context: AgentTurnContext,
        tool_invocations: list[ToolInvocationRecord],
        active_skill: SkillActivationRecord,
        active_subagent_name: str,
    ) -> tuple[TypedToolCallRecord, list]:
        tool_context = self._build_tool_context(
            context=context,
            tool_invocations=tool_invocations,
            run_id=active_run.run.run_id,
        )
        allowed_tools = self._allowed_tools(active_skill=active_skill, active_subagent_name=active_subagent_name)
        spec = self.tool_registry.resolve_spec(tool_name)
        self.run_tracker.advance(
            active_run,
            phase=RunPhase.TOOL_EXECUTION,
            active_skill=active_skill.skill_name,
            active_subagent=active_subagent_name,
            tool_name=spec.name,
        )
        hook_state = HookRuntimeState(
            active_skill_name=active_skill.skill_name,
            active_subagent_name=active_subagent_name,
            tool_count=len(active_run.run.tool_names) + 1,
            run_id=active_run.run.run_id,
            checkpoint_id=active_run.last_checkpoint_id,
        )
        before_hooks = self.hook_registry.run(
            AgentHookName.BEFORE_TOOL_CALL,
            context=context,
            state=hook_state,
        )
        memory_hooks = []
        if spec.name in {"write_memory", "promote_memory"}:
            memory_hooks = self.hook_registry.run(
                AgentHookName.BEFORE_MEMORY_WRITE,
                context=context,
                state=HookRuntimeState(
                    active_skill_name=active_skill.skill_name,
                    active_subagent_name=active_subagent_name,
                    tool_count=len(active_run.run.tool_names) + 1,
                    memory_write_requested=True,
                    run_id=active_run.run.run_id,
                    checkpoint_id=active_run.last_checkpoint_id,
                ),
            )
        before_checkpoint = None
        if spec.requires_checkpoint:
            before_checkpoint = self.run_tracker.create_checkpoint(
                active_run,
                phase=RunPhase.TOOL_EXECUTION,
                kind=CheckpointKind.TOOL_BEFORE,
                label=f"before_{spec.name}",
                reason="effectful_tool_call",
                tool_name=spec.name,
                resumable=spec.confirmation_required,
                payload={
                    **payload,
                    "_action_plane": {
                        "routed": bool(tool_context.action_gateway and tool_context.action_gateway.is_routed_tool(spec.name)),
                        "origin": tool_context.action_invocation_origin.value,
                    },
                },
                resumable_payload=payload if spec.confirmation_required else None,
                recovery_notes=[item.detail or item.hook_name.value for item in memory_hooks],
                notes=[item.detail or item.hook_name.value for item in [*before_hooks, *memory_hooks]],
            )
        record, output = self.tool_registry.invoke(
            tool_name,
            payload,
            context=tool_context,
            allowed_tools=allowed_tools,
            active_skill_name=active_skill.skill_name,
            active_subagent_name=active_subagent_name,
        )
        after_checkpoint = None
        if spec.requires_checkpoint:
            after_checkpoint = self.run_tracker.create_checkpoint(
                active_run,
                phase=RunPhase.TOOL_EXECUTION,
                kind=CheckpointKind.TOOL_AFTER,
                label=f"after_{spec.name}",
                reason="effectful_tool_result",
                tool_name=spec.name,
                resumable=spec.confirmation_required,
                payload=payload,
                result_payload={
                    **record.output_payload,
                    "_action_plane": {
                        "action_id": record.action_id,
                        "connector_id": record.connector_id,
                        "risk_class": record.risk_class.value if record.risk_class is not None else None,
                        "approval_state": record.approval_state.value if record.approval_state is not None else None,
                        "action_status": record.action_status.value if record.action_status is not None else None,
                        "request_hash": record.request_hash,
                        "idempotency_key": record.idempotency_key,
                    },
                },
                resumable_payload=record.output_payload if spec.confirmation_required else None,
                recovery_notes=[record.summary or spec.name],
                notes=[record.summary or spec.name],
            )
        record = record.model_copy(
            update={
                "before_checkpoint_id": before_checkpoint.checkpoint_id if before_checkpoint is not None else None,
                "after_checkpoint_id": after_checkpoint.checkpoint_id if after_checkpoint is not None else None,
            }
        )
        log_event(
            logger,
            logging.INFO if record.success else logging.WARNING,
            "agent_tool_completed",
            run_id=active_run.run.run_id,
            session_id=context.session.session_id,
            tool_name=record.tool_name,
            checkpoint_id=record.after_checkpoint_id or record.before_checkpoint_id or active_run.last_checkpoint_id,
            success=record.success,
            duration_ms=record.duration_ms,
        )
        after_hooks = self.hook_registry.run(
            AgentHookName.AFTER_TOOL_RESULT,
            context=context,
            state=HookRuntimeState(
                active_skill_name=active_skill.skill_name,
                active_subagent_name=active_subagent_name,
                tool_count=len(active_run.run.tool_names),
                run_id=active_run.run.run_id,
                checkpoint_id=after_checkpoint.checkpoint_id if after_checkpoint is not None else None,
            ),
        )
        del output
        return record, [*before_hooks, *memory_hooks, *after_hooks]

    def _build_tool_context(
        self,
        *,
        context: AgentTurnContext,
        tool_invocations: list[ToolInvocationRecord],
        run_id: str | None = None,
    ) -> ToolRuntimeContext:
        return self.build_tool_runtime_context(
            session=context.session,
            context_mode=context.context_mode,
            user_memory=context.user_memory,
            world_state=context.world_state,
            world_model=context.world_model,
            latest_perception=context.latest_perception,
            backend_status=context.backend_status,
            tool_invocations=tool_invocations,
            run_id=run_id,
            action_invocation_origin=self._action_invocation_origin(context),
        )

    def build_tool_runtime_context(
        self,
        *,
        session,
        context_mode,
        user_memory,
        world_state,
        world_model,
        latest_perception,
        backend_status,
        tool_invocations: list[ToolInvocationRecord],
        run_id: str | None = None,
        action_invocation_origin: ActionInvocationOrigin = ActionInvocationOrigin.USER_TURN,
    ) -> ToolRuntimeContext:
        return ToolRuntimeContext(
            session=session,
            context_mode=context_mode,
            user_memory=user_memory,
            world_state=world_state,
            world_model=world_model,
            latest_perception=latest_perception,
            backend_status=backend_status,
            backend_profile=self.backend_router.resolved_backend_profile(),
            body_driver_mode=self.settings.resolved_body_driver.value,
            body_transport_mode=(
                self.settings.blink_serial_transport
                if self.settings.resolved_body_driver.value == "serial"
                else ("virtual_preview" if self.settings.resolved_body_driver.value == "virtual" else "preview_only")
            ),
            body_preview_status=(
                "live"
                if self.settings.resolved_body_driver.value == "serial" and self.settings.blink_serial_transport == "live_serial"
                else (
                    self.settings.blink_serial_transport
                    if self.settings.resolved_body_driver.value == "serial"
                    else ("virtual_preview" if self.settings.resolved_body_driver.value == "virtual" else "preview_only")
                )
            ),
            tool_invocations=tool_invocations,
            action_policy=self.action_policy,
            run_id=run_id,
            action_invocation_origin=action_invocation_origin,
            action_gateway=self.action_gateway,
            workflow_runtime=self.workflow_runtime,
            knowledge_tools=self.knowledge_tools,
            memory_store=self.memory_store,
        )

    def _emit_workflow_body_feedback(self, state: str, run) -> None:
        intent_by_state = {
            "thinking": "operator_handoff_pending",
            "acknowledging": "greeting",
            "waiting_for_approval": "operator_handoff_pending",
        }
        log_event(
            logger,
            logging.INFO,
            "workflow_body_feedback",
            workflow_run_id=run.workflow_run_id,
            workflow_id=run.workflow_id,
            body_feedback_state=state,
        )
        if state not in {"thinking", "acknowledging", "waiting_for_approval", "safe_idle"}:
            return
        session = None
        if self.memory_store is not None and run.session_id:
            session = self.memory_store.get_session(run.session_id)
        if session is None:
            session = SessionRecord(session_id=run.session_id or f"workflow-{run.workflow_run_id}")
        world_model = self.memory_store.get_world_model() if self.memory_store is not None else EmbodiedWorldModel()
        payload = {"intent": intent_by_state.get(state, "safe_idle"), "reply_text": None}
        tool_name = "body_safe_idle" if state == "safe_idle" else "body_preview"
        if tool_name == "body_preview":
            payload["reply_text"] = run.summary or run.detail
        try:
            context_mode = (
                CompanionContextMode(run.context_mode)
                if run.context_mode is not None
                else self.settings.blink_context_mode
            )
            context = self.build_tool_runtime_context(
                session=session,
                context_mode=context_mode,
                user_memory=(
                    self.memory_store.get_user_memory(session.user_id)
                    if self.memory_store is not None and session.user_id
                    else None
                ),
                world_state=WorldState(last_session_id=session.session_id),
                world_model=world_model,
                latest_perception=None,
                backend_status=self.backend_router.runtime_statuses(),
                tool_invocations=[],
                run_id=f"workflow-feedback:{run.workflow_run_id}",
                action_invocation_origin=run.started_by,
            )
            record, _output = self.tool_registry.invoke(tool_name, payload, context=context)
            log_event(
                logger,
                logging.INFO,
                "workflow_body_feedback_emitted",
                workflow_run_id=run.workflow_run_id,
                workflow_id=run.workflow_id,
                body_feedback_state=state,
                tool_name=tool_name,
                success=record.success,
            )
        except Exception:
            log_event(
                logger,
                logging.WARNING,
                "workflow_body_feedback_tool_failed",
                workflow_run_id=run.workflow_run_id,
                workflow_id=run.workflow_id,
                body_feedback_state=state,
                tool_name=tool_name,
            )

    def _action_invocation_origin(self, context: AgentTurnContext) -> ActionInvocationOrigin:
        proactive_sources = {
            "always_on_runtime",
            "proactive_runtime",
            "scene_observer",
            "shift_supervisor",
            "shift_autonomy",
            "shift_tick",
        }
        if (context.event.source or "") in proactive_sources:
            return ActionInvocationOrigin.PROACTIVE_RUNTIME
        return ActionInvocationOrigin.USER_TURN

    def _allowed_tools(self, *, active_skill: SkillActivationRecord, active_subagent_name: str) -> set[str]:
        subagent = self.subagent_registry.get(active_subagent_name)
        skill_allow = set(active_skill.allowed_tools or active_skill.required_tools)
        if active_subagent_name == "embodiment_planner":
            skill_allow.update({"body_preview"})
        subagent_allow = set(subagent.allowed_tools)
        if skill_allow and subagent_allow:
            return skill_allow & subagent_allow
        return skill_allow or subagent_allow

    def _payload_for_tool(
        self,
        *,
        tool_name: str,
        context: AgentTurnContext,
        active_skill: SkillActivationRecord,
    ) -> dict[str, object]:
        if tool_name in {"search_venue_knowledge", "query_calendar", "search_memory", "query_local_files", "personal_reminders"}:
            return {"query": context.text}
        if tool_name in {
            "device_health_snapshot",
            "memory_status",
            "system_health",
            "today_context",
            "recent_session_digest",
            "capture_scene",
            "world_model_runtime",
        }:
            return {"session_id": context.session.session_id}
        if tool_name == "require_confirmation":
            return {"prompt": f"Confirm {active_skill.skill_name} tool path."}
        if tool_name in {"request_operator_help", "log_incident"}:
            return {
                "participant_summary": context.session.last_user_text or context.text or "operator_handoff_requested",
                "note": f"skill={active_skill.skill_name}",
            }
        if tool_name == "write_memory":
            return {"key": "last_topic", "value": context.text, "scope": "session"}
        if tool_name == "promote_memory":
            return {"summary": context.text or active_skill.skill_name, "memory_kind": active_skill.skill_name}
        if tool_name == "transcribe_audio":
            return {"transcript_text": context.text, "source": context.event.source or "pass_through"}
        if tool_name == "body_safe_idle":
            return {"intent": "safe_idle", "reply_text": None}
        if tool_name in {"body_preview", "body_command"}:
            return {"intent": active_skill.skill_name, "reply_text": None}
        if tool_name in {"speak_text", "interrupt_speech", "set_listening_state"}:
            return {"text": context.text, "state": "listening"}
        raise KeyError(tool_name)

    def _provider_failure_active(self, context: AgentTurnContext) -> bool:
        relevant_kinds = {"text_reasoning"}
        if context.latest_perception is not None:
            relevant_kinds.add("vision_analysis")
        return any(
            item.kind.value in relevant_kinds
            and item.status.value in {"fallback_active", "unavailable"}
            for item in context.backend_status
        )

    def _safe_idle_active(self, context: AgentTurnContext, candidate) -> bool:
        return (
            context.session.current_topic == "safe_idle"
            or context.world_model.executive_state == InteractionExecutiveState.SAFE_IDLE
            or candidate.intent == "safe_idle"
        )

    def _resolve_audit_skill(
        self,
        *,
        context: AgentTurnContext,
        safe_idle_active: bool,
        provider_failure_active: bool,
        preferred_skill_name: str | None,
    ) -> SkillActivationRecord:
        if preferred_skill_name:
            return self.skill_registry.activate_named(preferred_skill_name, reason=f"audit:{preferred_skill_name}")
        if safe_idle_active or provider_failure_active:
            return self.skill_registry.activate_named("safe_degraded_response", reason="audit:degraded")
        if context.latest_perception is not None:
            return self.skill_registry.activate_named("observe_and_comment", reason="audit:perception")
        return self.skill_registry.activate_named("general_conversation", reason="audit:system")

    def _subagent_selection_record(self, subagent_name: str) -> SpecialistRoleDecisionRecord:
        return SpecialistRoleDecisionRecord(
            role_name=subagent_name,
            summary="selected_primary_subagent",
            notes=["primary_surface_selection"],
        )

    def _fallback_reason(self, candidate, provider_failure_active: bool, validation_outcomes) -> str | None:
        if provider_failure_active:
            return "provider_failure_active"
        if candidate.fallback_used:
            return "dialogue_engine_fallback"
        downgraded = [item.detail for item in validation_outcomes if item.downgraded and item.detail]
        if downgraded:
            return downgraded[0]
        return None

    def _fallback_classification(
        self,
        *,
        candidate,
        provider_failure_active: bool,
        validation_outcomes,
        typed_tool_calls: list[TypedToolCallRecord],
    ) -> FallbackClassification | None:
        if provider_failure_active:
            return FallbackClassification.PROVIDER_FAILURE
        if self._unavailable_capabilities(typed_tool_calls):
            return FallbackClassification.CAPABILITY_UNAVAILABLE
        if any(item.downgraded for item in validation_outcomes):
            return FallbackClassification.VALIDATION_DOWNGRADE
        if candidate.fallback_used:
            return FallbackClassification.POLICY_DOWNGRADE
        return None

    def _unavailable_capabilities(self, typed_tool_calls: list[TypedToolCallRecord]) -> list[str]:
        unavailable_states = {"unavailable", "unsupported", "unconfigured", "blocked"}
        capabilities: list[str] = []
        for item in typed_tool_calls:
            if item.capability_state.value not in unavailable_states:
                continue
            if item.capability_name not in capabilities:
                capabilities.append(item.capability_name)
        return capabilities

    def _intentionally_skipped_capabilities(
        self,
        *,
        active_skill: SkillActivationRecord,
        typed_tool_calls: list[TypedToolCallRecord],
    ) -> list[str]:
        called = {item.capability_name for item in typed_tool_calls}
        allowed = {
            self.tool_registry.resolve_spec(tool_name).capability_name
            for tool_name in active_skill.allowed_tools
            if tool_name in self.tool_registry.list_tool_names()
        }
        skipped: list[str] = []
        for capability in sorted(allowed - called):
            if capability != "browser_task":
                continue
            skipped.append(capability)
        return skipped
