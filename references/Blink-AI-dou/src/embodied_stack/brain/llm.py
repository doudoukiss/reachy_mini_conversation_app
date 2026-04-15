from __future__ import annotations

import re
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Protocol

import httpx

from embodied_stack.brain.visual_query import looks_like_visual_query
from embodied_stack.shared.models import (
    CompanionContextMode,
    EmbodiedWorldModel,
    InstructionLayerRecord,
    PerceptionObservationType,
    PerceptionSnapshotRecord,
    ResponseMode,
    SessionRecord,
    SkillActivationRecord,
    ToolInvocationRecord,
    TypedToolCallRecord,
    UserMemoryRecord,
    WorldState,
    utc_now,
)


TOOL_NAME_TO_INTENT = {
    "faq_lookup": "faq",
    "events_lookup": "events",
    "wayfinding_lookup": "wayfinding",
    "operator_escalation": "operator_handoff",
    "user_memory_lookup": "user_memory",
    "profile_memory_lookup": "user_memory",
    "prior_session_lookup": "user_memory",
    "semantic_memory_lookup": "user_memory",
    "perception_fact_lookup": "perception_query",
    "venue_doc_lookup": "faq",
    "feedback_lookup": "feedback",
}

TOPIC_TO_INTENT = {
    "attention": "attention",
    "capabilities": "capabilities",
    "events": "events",
    "faq": "faq",
    "feedback": "feedback",
    "greeting": "greeting",
    "operator_handoff": "operator_handoff",
    "safe_idle": "safe_idle",
    "user_memory": "user_memory",
    "wayfinding": "wayfinding",
}

RESPONSE_MODE_GUIDANCE = {
    ResponseMode.GUIDE: "Be concise, direct, and helpful for the active companion mode.",
    ResponseMode.AMBASSADOR: "Be warm and welcoming, but stay concrete and avoid hype.",
    ResponseMode.DEBUG: "Prefix the reply with '[debug mode]' and briefly expose the grounded basis for the answer.",
}

EMBODIMENT_LIMITS = (
    "- Blink-AI is operating in venue_demo, the venue-guide mode of a local-first companion system.",
    "- Keep venue claims grounded in confirmed site facts, current operator-approved context, and retrieved venue knowledge.",
    "- Do not claim autonomous base movement, unsupported manipulation, hidden sensors, or unimplemented skills.",
    "- If the request exceeds known tools or confirmed state, say so plainly and offer directions, feedback capture, or a human handoff.",
    "- Keep replies short enough for robot speech and screen display.",
)


class DialogueEngineError(RuntimeError):
    pass


@dataclass
class DialogueContext:
    session: SessionRecord
    world_state: WorldState
    tool_invocations: list[ToolInvocationRecord]
    context_mode: CompanionContextMode = CompanionContextMode.PERSONAL_LOCAL
    user_memory: UserMemoryRecord | None = None
    latest_perception: PerceptionSnapshotRecord | None = None
    world_model: EmbodiedWorldModel | None = None
    venue_context: str | None = None
    active_skill: SkillActivationRecord | None = None
    instruction_layers: list[InstructionLayerRecord] = field(default_factory=list)
    typed_tool_calls: list[TypedToolCallRecord] = field(default_factory=list)


@dataclass
class DialogueResult:
    reply_text: str
    intent: str
    debug_notes: list[str]
    engine_name: str
    fallback_used: bool = False


class DialogueEngine(Protocol):
    def generate_reply(self, text: str, context: DialogueContext) -> DialogueResult:
        ...


class DialoguePromptBuilder:
    """Builds grounded prompts for provider-backed and local model dialogue backends."""

    def build_chat_messages(self, text: str, context: DialogueContext) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._build_system_message(context)},
            {"role": "user", "content": self._build_user_message(text, context)},
        ]

    def build_text_prompt(self, text: str, context: DialogueContext) -> str:
        messages = self.build_chat_messages(text, context)
        return (
            f"System:\n{messages[0]['content']}\n\n"
            f"User:\n{messages[1]['content']}\n\n"
            "Assistant:"
        )

    def _build_system_message(self, context: DialogueContext) -> str:
        remembered_name = context.user_memory.display_name if context.user_memory else None
        operator_notes = self._format_operator_notes(context.session)
        tool_results = self._format_tool_results(context.tool_invocations)
        typed_tool_results = self._format_typed_tool_calls(context.typed_tool_calls)
        recent_turns = self._format_recent_turns(context.session)
        perception_state = self._format_perception(context.latest_perception)
        embodied_state = self._format_world_model(context.world_model)
        venue_context = context.venue_context or "- none"
        embodiment_limits = "\n".join(self._embodiment_limits(context))
        active_skill = self._format_active_skill(context.active_skill)
        instruction_layers = self._format_instruction_layers(context.instruction_layers)
        response_guidance = self._response_guidance(context)
        identity_line = self._identity_line(context)
        capability_scope = self._default_capability_scope(context)
        relationship_guidance = self._relationship_guidance(context)
        relationship_memory = self._format_relationship_memory(context.user_memory)

        return (
            f"{identity_line}\n"
            "Give honest, grounded, concise replies.\n"
            "Use only confirmed tool results, remembered session state, operator notes, and explicit product scope.\n"
            f"Relationship stance: {relationship_guidance}\n"
            f"Response mode: {context.session.response_mode.value}\n"
            f"Response guidance: {response_guidance}\n"
            f"Current session topic: {context.session.current_topic or 'none'}\n"
            f"Context mode: {context.context_mode.value}\n"
            f"Conversation summary: {context.session.conversation_summary or 'none'}\n"
            f"Remembered user identity: {remembered_name or 'unknown'}\n"
            f"Relationship continuity:\n{relationship_memory}\n"
            f"World mode: {context.world_state.mode.value}\n"
            f"Pending operator sessions: {len(context.world_state.pending_operator_session_ids)}\n\n"
            f"Active skill:\n{active_skill}\n\n"
            f"Instruction layers:\n{instruction_layers}\n\n"
            f"Recent operator notes:\n{operator_notes}\n\n"
            f"Grounded tool results:\n{tool_results}\n\n"
            f"Typed tool calls:\n{typed_tool_results}\n\n"
            f"Imported venue knowledge:\n{venue_context}\n\n"
            f"Latest perception state:\n{perception_state}\n\n"
            f"Embodied world model:\n{embodied_state}\n\n"
            f"Recent conversation turns:\n{recent_turns}\n\n"
            f"Default capability scope:\n{capability_scope}\n\n"
            f"Embodiment limits:\n{embodiment_limits}\n"
        )

    def _identity_line(self, context: DialogueContext) -> str:
        if context.context_mode == CompanionContextMode.PERSONAL_LOCAL:
            return "You are Blink-AI, a terminal-first, local-first personal companion running on a nearby Mac."
        return "You are Blink-AI operating in venue_demo, the Mac-side venue-guide mode for the current pilot site."

    def _embodiment_limits(self, context: DialogueContext) -> tuple[str, ...]:
        if context.context_mode == CompanionContextMode.PERSONAL_LOCAL:
            return (
                "- Blink-AI is currently operating as a local companion on a nearby Mac.",
                "- Keep the personal companion identity even when venue knowledge is loaded; use venue facts only when the user explicitly asks or grounded retrieval requires it.",
                "- Do not claim autonomous base movement, unsupported manipulation, hidden sensors, or unimplemented skills.",
                "- If the request exceeds known tools or confirmed state, say so plainly and offer the safest next step.",
                "- Keep replies short enough for live speech and screen display.",
            )
        return EMBODIMENT_LIMITS

    def _build_user_message(self, text: str, context: DialogueContext) -> str:
        request_label = "User request" if context.context_mode == CompanionContextMode.PERSONAL_LOCAL else "Visitor request"
        return (
            f"{request_label}: {text}\n"
            "Reply with one short spoken answer. If the context is insufficient, say what is known and offer the safest next step."
        )

    def _response_guidance(self, context: DialogueContext) -> str:
        if context.context_mode == CompanionContextMode.PERSONAL_LOCAL:
            if context.session.response_mode == ResponseMode.GUIDE:
                return "Be concise, direct, and helpful for a local companion conversation."
            if context.session.response_mode == ResponseMode.AMBASSADOR:
                return "Be warm and welcoming, but stay concrete and grounded to the user's actual context."
        return RESPONSE_MODE_GUIDANCE.get(
            context.session.response_mode,
            RESPONSE_MODE_GUIDANCE[ResponseMode.GUIDE],
        )

    def _default_capability_scope(self, context: DialogueContext) -> str:
        if context.context_mode == CompanionContextMode.PERSONAL_LOCAL:
            return (
                "- Default to local companion capabilities: notes, reminders, current workspace context, memory continuity, "
                "grounded camera answers, and safe operator-visible actions.\n"
                "- Do not default to venue-guide wording like visitors, rooms, directions, or events unless the user "
                "explicitly asks about a venue or retrieved venue knowledge is actually present."
            )
        return (
            "- Default to venue-demo capabilities grounded in confirmed venue facts, wayfinding, events, "
            "feedback capture, and operator handoff."
        )

    def _format_operator_notes(self, session: SessionRecord) -> str:
        notes = [f"- {note.text}" for note in session.operator_notes[-3:]]
        return "\n".join(notes) if notes else "- none"

    def _format_tool_results(self, tool_invocations: list[ToolInvocationRecord]) -> str:
        if not tool_invocations:
            return "- none"

        lines: list[str] = []
        for tool in tool_invocations:
            lines.append(f"- {tool.tool_name}: {tool.answer_text or 'no direct answer'}")
            if tool.metadata:
                lines.append(f"  metadata: {tool.metadata}")
            if tool.notes:
                lines.append(f"  notes: {', '.join(tool.notes)}")
        return "\n".join(lines)

    def _format_recent_turns(self, session: SessionRecord) -> str:
        turns = session.transcript[-3:]
        if not turns:
            return "- none"

        lines: list[str] = []
        for turn in turns:
            user_text = turn.user_text or "-"
            reply_text = turn.reply_text or "-"
            lines.append(f"- {turn.event_type}: user={user_text!r}; reply={reply_text!r}; intent={turn.intent or 'unknown'}")
        return "\n".join(lines)

    def _format_active_skill(self, skill: SkillActivationRecord | None) -> str:
        if skill is None:
            return "- none"
        success = ", ".join(skill.success_criteria) or "none"
        required_tools = ", ".join(skill.required_tools) or "none"
        return "\n".join(
            [
                f"- name={skill.skill_name}",
                f"- behavior_category={(skill.behavior_category.value if skill.behavior_category is not None else 'none')}",
                f"- reason={skill.reason}",
                f"- required_tools={required_tools}",
                f"- success_criteria={success}",
            ]
        )

    def _relationship_guidance(self, context: DialogueContext) -> str:
        if context.context_mode == CompanionContextMode.PERSONAL_LOCAL:
            return (
                "Provide useful continuity without fake intimacy. Use stored names or preferences sparingly, do not "
                "invent emotional closeness, and do not treat inferred feelings as durable memory."
            )
        return "Stay warm but mode-specific; do not imply personal closeness beyond the current venue interaction."

    def _format_relationship_memory(self, user_memory: UserMemoryRecord | None) -> str:
        if user_memory is None:
            return "- none"
        profile = user_memory.relationship_profile
        tone = ", ".join(profile.tone_preferences) or "none"
        boundaries = ", ".join(profile.interaction_boundaries) or "none"
        continuity = ", ".join(profile.continuity_preferences) or "none"
        return "\n".join(
            [
                f"- greeting_preference={profile.greeting_preference or 'none'}",
                f"- planning_style={profile.planning_style or 'none'}",
                f"- tone_preferences={tone}",
                f"- interaction_boundaries={boundaries}",
                f"- continuity_preferences={continuity}",
            ]
        )

    def _format_instruction_layers(self, layers: list[InstructionLayerRecord]) -> str:
        if not layers:
            return "- none"
        lines = []
        for layer in layers:
            lines.append(
                f"- {layer.name}: dynamic={layer.dynamic}; source={layer.source_ref}; summary={layer.summary or 'none'}"
            )
        return "\n".join(lines)

    def _format_typed_tool_calls(self, tool_calls: list[TypedToolCallRecord]) -> str:
        if not tool_calls:
            return "- none"
        lines = []
        for tool_call in tool_calls:
            lines.append(
                f"- {tool_call.tool_name}: success={tool_call.success}; summary={tool_call.summary or 'none'}; "
                f"schema_valid={tool_call.validation.schema_valid}; output_valid={tool_call.validation.output_valid}"
            )
        return "\n".join(lines)

    def _format_perception(self, snapshot: PerceptionSnapshotRecord | None) -> str:
        if snapshot is None:
            return "- none"

        lines = [
            f"- provider={snapshot.provider_mode.value}; status={snapshot.status.value}; limited_awareness={snapshot.limited_awareness}",
            f"- scene_summary={snapshot.scene_summary or 'none'}",
            f"- source={snapshot.source_frame.source_kind}; captured_at={snapshot.source_frame.captured_at or 'unknown'}",
        ]
        for observation in snapshot.observations[-5:]:
            value = observation.text_value
            if value is None and observation.number_value is not None:
                value = str(observation.number_value)
            if value is None and observation.bool_value is not None:
                value = str(observation.bool_value)
            lines.append(
                f"- observation={observation.observation_type.value}; value={value or '-'}; confidence={observation.confidence.score:.2f}"
            )
        return "\n".join(lines)

    def _format_world_model(self, world_model: EmbodiedWorldModel | None) -> str:
        if world_model is None:
            return "- none"

        participant_count = len(world_model.active_participants_in_view)
        attention = world_model.attention_target.target_label if world_model.attention_target else "none"
        anchors = ", ".join(item.label for item in world_model.visual_anchors[:3]) or "none"
        visible_text = ", ".join(item.label for item in world_model.recent_visible_text[:3]) or "none"
        objects = ", ".join(item.label for item in world_model.recent_named_objects[:3]) or "none"
        return "\n".join(
            [
                f"- participants_in_view={participant_count}",
                f"- engagement_state={world_model.engagement_state.value}",
                f"- attention_target={attention}",
                f"- current_speaker={world_model.current_speaker_participant_id or 'unknown'}",
                f"- turn_state={world_model.turn_state.value}",
                f"- visual_anchors={anchors}",
                f"- visible_text={visible_text}",
                f"- named_objects={objects}",
                f"- limited_awareness={world_model.perception_limited_awareness}",
            ]
        )


class RuleBasedDialogueEngine:
    def generate_reply(self, text: str, context: DialogueContext) -> DialogueResult:
        lowered = text.lower().strip()

        if _looks_like_perception_query(lowered):
            grounded_perception = next(
                (
                    item
                    for item in context.tool_invocations
                    if item.tool_name == "perception_fact_lookup" and item.answer_text
                ),
                None,
            )
            if grounded_perception is not None:
                return DialogueResult(
                    reply_text=self._style_reply(
                        grounded_perception.answer_text,
                        context.session.response_mode,
                        intent="perception_query",
                    ),
                    intent="perception_query",
                    debug_notes=[f"tool_match:{grounded_perception.tool_name}", *grounded_perception.notes],
                    engine_name="rule_based",
                )
            reply_text = self._reply_from_perception(context, lowered)
            return DialogueResult(
                reply_text=self._style_reply(reply_text, context.session.response_mode, intent="perception_query"),
                intent="perception_query",
                debug_notes=["rule_match:perception_query"],
                engine_name="rule_based",
            )

        if context.tool_invocations:
            top_result = context.tool_invocations[0]
            reply_text = top_result.answer_text or self._fallback_reply(context)
            intent = _intent_for_tool_name(top_result.tool_name)
            return DialogueResult(
                reply_text=self._style_reply(reply_text, context.session.response_mode, intent=intent),
                intent=intent,
                debug_notes=[f"tool_match:{top_result.tool_name}", *top_result.notes],
                engine_name="rule_based",
            )

        if match := re.search(r"(?:my name is|i am|i'm)\s+([a-z][a-z\-']+)", lowered):
            name = match.group(1).strip(" .,!?:;").title()
            return DialogueResult(
                reply_text=self._style_reply(
                    self._introduction_reply(name=name, context=context),
                    context.session.response_mode,
                    intent="introduction",
                ),
                intent="introduction",
                debug_notes=["rule_match:introduction"],
                engine_name="rule_based",
            )

        if "what can you do" in lowered or "capabilities" in lowered:
            return DialogueResult(
                reply_text=self._style_reply(
                    self._capabilities_reply(context),
                    context.session.response_mode,
                    intent="capabilities",
                ),
                intent="capabilities",
                debug_notes=["rule_match:capabilities"],
                engine_name="rule_based",
            )

        if "do you remember me" in lowered and context.user_memory and context.user_memory.display_name:
            return DialogueResult(
                reply_text=self._style_reply(
                    f"Yes. I remember you as {context.user_memory.display_name}.",
                    context.session.response_mode,
                    intent="user_memory",
                ),
                intent="user_memory",
                debug_notes=["rule_match:user_memory"],
                engine_name="rule_based",
            )

        return DialogueResult(
            reply_text=self._style_reply(self._fallback_reply(context), context.session.response_mode, intent="fallback"),
            intent="fallback",
            debug_notes=["rule_match:fallback"],
            engine_name="rule_based",
        )

    def _fallback_reply(self, context: DialogueContext) -> str:
        current_topic = context.session.current_topic
        if current_topic == "events":
            return "I can help with this week's events, room directions, community hours, or a handoff to staff."
        if current_topic == "wayfinding":
            return "I can repeat directions, answer event questions, or connect you to a staff member."
        if current_topic == "feedback":
            return "I can collect structured feedback or connect you with the front desk."
        if context.context_mode == CompanionContextMode.PERSONAL_LOCAL:
            return (
                "I can help with local notes, reminders, today's context, recent workspace recap, or venue questions if you ask one directly."
            )
        if context.venue_context:
            return (
                f"I can help with venue questions, rooms, events, staff handoff, and other confirmed details for the current pilot site. "
                f"If I am unsure, I will say so clearly."
            )
        if context.context_mode == CompanionContextMode.VENUE_DEMO:
            return (
                "I am in venue-demo mode, so I keep responses deterministic. "
                "I can help with greetings, room guidance, event questions, feedback, and operator handoff."
            )
        return (
            "I am running as a local-first companion with limited context, so I keep responses deterministic. "
            "I can still help with grounded next steps and say clearly when I need more context."
        )

    def _is_personal_local(self, context: DialogueContext) -> bool:
        return context.context_mode == CompanionContextMode.PERSONAL_LOCAL

    def _introduction_reply(self, *, name: str, context: DialogueContext) -> str:
        if self._is_personal_local(context):
            return (
                f"Nice to meet you, {name}. I can help with notes, reminders, local workspace context, "
                "and grounded questions about what is happening right now."
            )
        return f"Nice to meet you, {name}. In venue-demo mode I can help with rooms, events, feedback, and staff handoff."

    def _capabilities_reply(self, context: DialogueContext) -> str:
        if self._is_personal_local(context):
            return (
                "I can help with local notes, reminders, today's context, recent workspace recap, "
                "and grounded camera or venue questions when you ask directly."
            )
        return (
            "In venue-demo mode I can greet visitors, answer common questions, guide people to rooms and events, "
            "remember active sessions, collect structured feedback, and escalate to a human operator when needed."
        )

    def _reply_from_perception(self, context: DialogueContext, lowered: str) -> str:
        snapshot = _fresh_perception_snapshot(context.latest_perception)
        people_count = _perception_number(snapshot, PerceptionObservationType.PEOPLE_COUNT) if snapshot else None
        visible_text = _perception_texts(snapshot, PerceptionObservationType.VISIBLE_TEXT) if snapshot else []
        anchors = _perception_texts(snapshot, PerceptionObservationType.LOCATION_ANCHOR) if snapshot else []
        objects = _perception_texts(snapshot, PerceptionObservationType.NAMED_OBJECT) if snapshot else []
        degraded_snapshot = snapshot is not None and (
            snapshot.limited_awareness or snapshot.status.value != "ok"
        )

        if context.world_model is not None and not degraded_snapshot:
            if not visible_text:
                visible_text = [item.label for item in context.world_model.recent_visible_text]
            if not anchors:
                anchors = [item.label for item in context.world_model.visual_anchors]
            if not objects:
                objects = [item.label for item in context.world_model.recent_named_objects]
            if people_count is None and context.world_model.active_participants_in_view:
                people_count = len(context.world_model.active_participants_in_view)

        if degraded_snapshot:
            if self._is_personal_local(context):
                return (
                    "My visual situational awareness is limited right now, so I do not have a confident fresh reading of that."
                )
            return (
                "My visual situational awareness is limited right now, so I do not have a confident fresh venue reading of that."
            )

        if snapshot is None:
            if context.world_model is not None:
                visible_text = [item.label for item in context.world_model.recent_visible_text]
                anchors = [item.label for item in context.world_model.visual_anchors]
                objects = [item.label for item in context.world_model.recent_named_objects]
                if context.world_model.active_participants_in_view:
                    people_count = len(context.world_model.active_participants_in_view)
            if visible_text or anchors or objects or people_count is not None:
                return self._reply_from_world_model(people_count, visible_text, anchors, objects, lowered)
            if self._is_personal_local(context):
                return (
                    "My visual situational awareness is limited right now. "
                    "I can still help with notes, reminders, workspace context, or other local tasks if you tell me what you need."
                )
            return (
                "My visual situational awareness is limited right now. "
                "I can still help with venue directions, event information, feedback, or a human handoff."
            )

        if "how many" in lowered or "anyone" in lowered or "people" in lowered:
            if people_count is None:
                return "I do not have a confident people count from the latest frame."
            noun = "person" if people_count == 1 else "people"
            return f"I currently have a visual estimate of {people_count} {noun} in view."

        if "text" in lowered or "sign" in lowered:
            if visible_text:
                return f"The latest visible text I can ground is: {', '.join(visible_text)}."
            return "I do not have a confident text reading from the latest frame."

        if "where" in lowered or "anchor" in lowered or "location" in lowered:
            if anchors:
                return f"I can currently ground these location anchors: {', '.join(anchors)}."
            return "I do not have a confident location anchor from the latest frame."

        if "object" in lowered or "see" in lowered:
            parts: list[str] = []
            if objects:
                parts.append(f"objects: {', '.join(objects)}")
            if anchors:
                parts.append(f"anchors: {', '.join(anchors)}")
            if snapshot.scene_summary:
                parts.append(f"scene: {snapshot.scene_summary}")
            if parts:
                return "From the latest frame, " + "; ".join(parts) + "."

        return snapshot.scene_summary or "I do not have a confident scene summary from the latest frame."

    def _reply_from_world_model(
        self,
        people_count: int | None,
        visible_text: list[str],
        anchors: list[str],
        objects: list[str],
        lowered: str,
    ) -> str:
        if "how many" in lowered or "anyone" in lowered or "people" in lowered:
            if people_count is None:
                return "I do not have a confident people count from the current scene state."
            noun = "person" if people_count == 1 else "people"
            return f"I currently have a visual estimate of {people_count} {noun} in view."

        if "text" in lowered or "sign" in lowered:
            if visible_text:
                return f"The latest visible text I can ground is: {', '.join(visible_text)}."
            if anchors:
                return f"The latest visible anchors I can ground are: {', '.join(anchors)}."
            return "I do not have a confident text reading from the current scene state."

        if "where" in lowered or "anchor" in lowered or "location" in lowered:
            if anchors:
                return f"I can currently ground these location anchors: {', '.join(anchors)}."
            return "I do not have a confident location anchor from the current scene state."

        if objects:
            return f"From the current scene state, I can ground these visible objects: {', '.join(objects)}."
        return "My current scene state is too limited to answer that confidently."

    def _style_reply(self, text: str, mode: ResponseMode, *, intent: str) -> str:
        if mode == ResponseMode.AMBASSADOR:
            return f"Happy to help. {text}"
        if mode == ResponseMode.DEBUG:
            return f"[debug mode] intent={intent}; topic={intent}; reply={text}"
        return text


class OllamaDialogueEngine:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 4.0,
        cold_start_timeout_seconds: float | None = None,
        prompt_builder: DialoguePromptBuilder | None = None,
        keep_alive: str | None = None,
        success_reporter: Callable[[str, float, bool], None] | None = None,
        failure_reporter: Callable[[str, float | None, bool], None] | None = None,
        warm_checker: Callable[[], bool] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.cold_start_timeout_seconds = cold_start_timeout_seconds
        self.prompt_builder = prompt_builder or DialoguePromptBuilder()
        self.keep_alive = keep_alive
        self.success_reporter = success_reporter
        self.failure_reporter = failure_reporter
        self.warm_checker = warm_checker

    def generate_reply(self, text: str, context: DialogueContext) -> DialogueResult:
        messages = self.prompt_builder.build_chat_messages(text=text, context=context)
        retry_used = False
        try:
            response, latency_ms = self._perform_chat(messages=messages, timeout_seconds=self.timeout_seconds)
        except httpx.TimeoutException as exc:
            should_retry = self._should_retry_cold_start()
            if self.failure_reporter is not None:
                self.failure_reporter("ollama_timeout", self.timeout_seconds, should_retry)
            if not should_retry:
                raise DialogueEngineError("ollama_timeout") from exc
            retry_used = True
            try:
                response, latency_ms = self._perform_chat(
                    messages=messages,
                    timeout_seconds=float(self.cold_start_timeout_seconds),
                )
            except httpx.TimeoutException as retry_exc:
                if self.failure_reporter is not None:
                    self.failure_reporter(
                        "ollama_timeout_after_cold_start_retry",
                        float(self.cold_start_timeout_seconds),
                        True,
                    )
                raise DialogueEngineError("ollama_timeout_after_cold_start_retry") from retry_exc
            except httpx.HTTPError as retry_exc:
                if self.failure_reporter is not None:
                    self.failure_reporter(f"ollama_transport_error:{retry_exc}", float(self.cold_start_timeout_seconds), True)
                raise DialogueEngineError(f"ollama_transport_error:{retry_exc}") from retry_exc
        except httpx.HTTPError as exc:
            if self.failure_reporter is not None:
                self.failure_reporter(f"ollama_transport_error:{exc}", self.timeout_seconds, False)
            raise DialogueEngineError(f"ollama_transport_error:{exc}") from exc

        body = response.json()
        message = body.get("message") if isinstance(body, dict) else None
        generated = ""
        if isinstance(message, dict):
            generated = str(message.get("content") or "").strip()
        if not generated:
            generated = str(body.get("response") or "").strip() if isinstance(body, dict) else ""
        if not generated:
            raise DialogueEngineError("ollama_returned_empty_response")
        if self.success_reporter is not None:
            self.success_reporter(self.model, latency_ms, retry_used)

        return DialogueResult(
            reply_text=generated,
            intent=_infer_context_intent(context),
            debug_notes=["ollama_chat_retry" if retry_used else "ollama_chat"],
            engine_name=f"ollama:{self.model}",
        )

    def _perform_chat(self, *, messages: list[dict[str, str]], timeout_seconds: float) -> tuple[httpx.Response, float]:
        start = perf_counter()
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "think": False,
                    "keep_alive": self.keep_alive,
                    "messages": messages,
                    "options": {"temperature": 0.2},
                },
            )
            response.raise_for_status()
        return response, round((perf_counter() - start) * 1000.0, 2)

    def _should_retry_cold_start(self) -> bool:
        if self.cold_start_timeout_seconds is None or self.cold_start_timeout_seconds <= self.timeout_seconds:
            return False
        if self.warm_checker is None:
            return False
        return not self.warm_checker()

class OpenAICompatibleChatEngine:
    """Shared adapter for providers that accept OpenAI-style chat completion requests."""

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout_seconds: float = 8.0,
        prompt_builder: DialoguePromptBuilder | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.prompt_builder = prompt_builder or DialoguePromptBuilder()
        self.transport = transport

    def generate_reply(self, text: str, context: DialogueContext) -> DialogueResult:
        if not self.api_key:
            raise DialogueEngineError(f"{self.provider_name}_api_key_missing")
        if not self.base_url.strip():
            raise DialogueEngineError(f"{self.provider_name}_base_url_missing")
        if not self.model.strip():
            raise DialogueEngineError(f"{self.provider_name}_model_missing")

        messages = self.prompt_builder.build_chat_messages(text=text, context=context)
        payload = {
            "model": self.model,
            "stream": False,
            "temperature": 0.2,
            "messages": messages,
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    self._chat_completions_url(),
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise DialogueEngineError(f"{self.provider_name}_timeout") from exc
        except httpx.HTTPError as exc:
            raise DialogueEngineError(f"{self.provider_name}_transport_error:{exc}") from exc
        except ValueError as exc:
            raise DialogueEngineError(f"{self.provider_name}_invalid_json") from exc

        generated = self._extract_response_text(body)
        if not generated:
            raise DialogueEngineError(f"{self.provider_name}_returned_empty_response")

        return DialogueResult(
            reply_text=generated,
            intent=_infer_context_intent(context),
            debug_notes=[f"{self.provider_name}_chat_completion"],
            engine_name=f"{self.provider_name}:{self.model}",
        )

    def _chat_completions_url(self) -> str:
        normalized = self.base_url.rstrip("/")
        if normalized.endswith("/v1"):
            normalized = normalized[:-3]
        return f"{normalized}/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _extract_response_text(self, body: dict[str, Any]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DialogueEngineError(f"{self.provider_name}_missing_choices")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise DialogueEngineError(f"{self.provider_name}_invalid_choice")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise DialogueEngineError(f"{self.provider_name}_missing_message")

        return self._coerce_content_to_text(message.get("content"))

    def _coerce_content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, dict):
            for key in ("text", "content"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            return "\n".join(parts).strip()

        return ""


class GRSAIDialogueEngine(OpenAICompatibleChatEngine):
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        text_base_url: str | None,
        model: str,
        timeout_seconds: float = 8.0,
        prompt_builder: DialoguePromptBuilder | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            provider_name="grsai",
            api_key=api_key,
            base_url=text_base_url or base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            prompt_builder=prompt_builder,
            transport=transport,
        )


class FallbackDialogueEngine:
    def __init__(self, primary: DialogueEngine | None, fallback: DialogueEngine) -> None:
        self.primary = primary
        self.fallback = fallback

    def generate_reply(self, text: str, context: DialogueContext) -> DialogueResult:
        notes: list[str] = []
        if self.primary is not None:
            try:
                return self.primary.generate_reply(text, context)
            except DialogueEngineError as exc:
                notes.append(f"primary_failed:{exc}")

        fallback_result = self.fallback.generate_reply(text, context)
        fallback_result.fallback_used = True if self.primary is not None else fallback_result.fallback_used
        fallback_result.debug_notes = [*notes, *fallback_result.debug_notes]
        return fallback_result


@dataclass
class DialogueEngineFactory:
    backend: str
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float = 4.0
    grsai_api_key: str | None = None
    grsai_base_url: str = "https://grsai.dakka.com.cn"
    grsai_text_base_url: str | None = None
    grsai_model: str = "gpt-4o-mini"
    grsai_timeout_seconds: float = 8.0
    _fallback_engine: RuleBasedDialogueEngine = field(default_factory=RuleBasedDialogueEngine)
    _prompt_builder: DialoguePromptBuilder = field(default_factory=DialoguePromptBuilder)

    def build(self) -> DialogueEngine:
        normalized = self.backend.lower().strip()
        if normalized in {"grsai", "provider", "openai_compatible"}:
            return FallbackDialogueEngine(
                primary=GRSAIDialogueEngine(
                    api_key=self.grsai_api_key,
                    base_url=self.grsai_base_url,
                    text_base_url=self.grsai_text_base_url,
                    model=self.grsai_model,
                    timeout_seconds=self.grsai_timeout_seconds,
                    prompt_builder=self._prompt_builder,
                ),
                fallback=self._fallback_engine,
            )
        if normalized in {"ollama", "auto"}:
            return FallbackDialogueEngine(
                primary=OllamaDialogueEngine(
                    base_url=self.ollama_base_url,
                    model=self.ollama_model,
                    timeout_seconds=self.ollama_timeout_seconds,
                    prompt_builder=self._prompt_builder,
                ),
                fallback=self._fallback_engine,
            )
        return self._fallback_engine


def _intent_for_tool_name(tool_name: str) -> str:
    return TOOL_NAME_TO_INTENT.get(tool_name, "fallback")


def _infer_context_intent(context: DialogueContext) -> str:
    if context.tool_invocations:
        return _intent_for_tool_name(context.tool_invocations[0].tool_name)
    if context.session.current_topic:
        return TOPIC_TO_INTENT.get(context.session.current_topic, "llm_response")
    return "llm_response"


def _looks_like_perception_query(text: str) -> bool:
    return looks_like_visual_query(text)


def _perception_number(snapshot: PerceptionSnapshotRecord, observation_type: PerceptionObservationType) -> int | None:
    for item in snapshot.observations:
        if item.observation_type == observation_type and item.number_value is not None:
            return int(item.number_value)
    return None


def _perception_texts(snapshot: PerceptionSnapshotRecord, observation_type: PerceptionObservationType) -> list[str]:
    return [
        item.text_value
        for item in snapshot.observations
        if item.observation_type == observation_type and item.text_value
    ]


def _fresh_perception_snapshot(snapshot: PerceptionSnapshotRecord | None) -> PerceptionSnapshotRecord | None:
    if snapshot is None:
        return None
    captured_at = snapshot.source_frame.captured_at or snapshot.created_at
    if (utc_now() - captured_at).total_seconds() > 75.0:
        return None
    return snapshot
