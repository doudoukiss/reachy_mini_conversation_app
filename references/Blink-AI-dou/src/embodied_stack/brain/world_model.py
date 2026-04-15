from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from embodied_stack.brain.attention_policy import build_attention_decision
from embodied_stack.brain.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.social_runtime import social_mode_for_event, social_mode_for_response
from embodied_stack.demo.community_scripts import COMMUNITY_LOCATIONS
from embodied_stack.shared.models import (
    AttentionTargetType,
    CommandBatch,
    CommandType,
    EmbodiedWorldModel,
    EngagementState,
    EnvironmentState,
    ExecutiveDecisionRecord,
    ExecutiveDecisionType,
    FactFreshness,
    InteractionExecutiveState,
    PerceptionConfidence,
    PerceptionEventType,
    PerceptionTier,
    RobotEvent,
    SceneClaimKind,
    SemanticQualityClass,
    SessionRecord,
    SocialRuntimeMode,
    VisualAnchorType,
    WorldModelAnchor,
    WorldModelObservation,
    WorldModelParticipant,
    utc_now,
)


@dataclass
class WorldModelRuntime:
    memory: MemoryStore
    freshness_policy: FreshnessPolicy = field(default_factory=lambda: DEFAULT_FRESHNESS_POLICY)
    participant_ttl_seconds: float = DEFAULT_FRESHNESS_POLICY.watcher_hint_window.ttl_seconds
    engagement_ttl_seconds: float = DEFAULT_FRESHNESS_POLICY.engagement_window.ttl_seconds
    anchor_ttl_seconds: float = DEFAULT_FRESHNESS_POLICY.semantic_window.ttl_seconds
    observation_ttl_seconds: float = DEFAULT_FRESHNESS_POLICY.semantic_window.ttl_seconds
    attention_ttl_seconds: float = DEFAULT_FRESHNESS_POLICY.attention_window.ttl_seconds
    responding_window_seconds: float = 8.0

    def get_state(self) -> EmbodiedWorldModel:
        current = self.memory.get_world_model()
        pruned = self._prune(current, now=utc_now())
        self.memory.replace_world_model(pruned)
        return pruned

    def apply_event(self, event: RobotEvent, *, session: SessionRecord) -> EmbodiedWorldModel:
        now = event.timestamp
        model = self._prune(self.memory.get_world_model(), now=now)
        model.last_updated = now
        context = self._perception_context(event)
        observed_at = context["observed_at"] or now
        claim_kind = context["claim_kind"]

        if event.event_type in {"person_detected", PerceptionEventType.PERSON_VISIBLE.value}:
            people_count = int(event.payload.get("people_count") or 1)
            confidence = confidence_from_payload(event.payload.get("confidence"), fallback=0.82)
            self._set_participants(
                model,
                count=people_count,
                confidence=confidence,
                now=observed_at,
                source_event_type=event.event_type,
                participant_ids=self._participant_ids_from_event(event, expected_count=people_count),
                source_tier=context["tier"],
                claim_kind=claim_kind,
            )
            self._set_engagement(
                model,
                state=EngagementState.NOTICING,
                confidence=confidence,
                now=observed_at,
            )
            self._set_attention(
                model,
                target_type=AttentionTargetType.PARTICIPANT,
                target_label="active_visitor",
                confidence=confidence,
                now=observed_at,
                rationale="person_visible_event",
                source_tier=context["tier"],
                claim_kind=claim_kind,
            )

        elif event.event_type == PerceptionEventType.PERSON_LEFT.value:
            people_count = int(event.payload.get("people_count") or 0)
            self._set_participants(
                model,
                count=people_count,
                confidence=confidence_from_payload(0.65),
                now=observed_at,
                source_event_type=event.event_type,
                participant_ids=self._participant_ids_from_event(event, expected_count=people_count),
                source_tier=context["tier"],
                claim_kind=claim_kind,
            )
            self._set_engagement(model, state=EngagementState.LOST, confidence=confidence_from_payload(0.68), now=observed_at)
            model.current_speaker_participant_id = None
            model.current_speaker_session_id = None
            model.attention_target = None

        elif event.event_type == PerceptionEventType.PEOPLE_COUNT_CHANGED.value:
            people_count = int(event.payload.get("people_count") or 0)
            confidence = confidence_from_payload(event.payload.get("confidence"), fallback=0.74)
            self._set_participants(
                model,
                count=people_count,
                confidence=confidence,
                now=observed_at,
                source_event_type=event.event_type,
                participant_ids=self._participant_ids_from_event(event, expected_count=people_count),
                source_tier=context["tier"],
                claim_kind=claim_kind,
            )
            self._set_engagement(
                model,
                state=EngagementState.NOTICING if people_count > 0 else EngagementState.LOST,
                confidence=confidence,
                now=observed_at,
            )
            if people_count == 0:
                model.attention_target = None

        elif event.event_type == PerceptionEventType.ENGAGEMENT_ESTIMATE_CHANGED.value:
            estimate = str(event.payload.get("engagement_estimate") or "").strip().lower()
            mapped = {
                "noticing": EngagementState.NOTICING,
                "engaged": EngagementState.ENGAGED,
                "disengaging": EngagementState.DISENGAGING,
                "lost": EngagementState.LOST,
            }.get(estimate, EngagementState.UNKNOWN)
            confidence = confidence_from_payload(event.payload.get("confidence"), fallback=0.7)
            self._set_engagement(model, state=mapped, confidence=confidence, now=observed_at)

        elif event.event_type == "speech_transcript":
            confidence = confidence_from_payload(event.payload.get("confidence"), fallback=0.88)
            participant_id = (
                str(event.payload.get("participant_id") or "").strip()
                or (model.active_participants_in_view[0].participant_id if model.active_participants_in_view else "likely_unseen_speaker")
            )
            model.current_speaker_participant_id = participant_id
            model.current_speaker_session_id = session.session_id
            model.likely_user_session_id = session.session_id
            model.last_user_speech_at = now
            model.turn_state = InteractionExecutiveState.LISTENING
            model.speaker_hypothesis_source = "recent_speech_in_active_session"
            model.speaker_hypothesis_expires_at = now + timedelta(seconds=self.freshness_policy.speaker_hypothesis_window.ttl_seconds)
            self._set_engagement(model, state=EngagementState.ENGAGED, confidence=confidence, now=now)
            self._set_attention(
                model,
                target_type=AttentionTargetType.PARTICIPANT,
                target_label=participant_id,
                confidence=confidence,
                now=now,
                rationale="speech_transcript_active_speaker",
                source_tier=PerceptionTier.WATCHER,
                speaker_source="recent_speech_in_active_session",
            )

        elif event.event_type in {"touch", "button"}:
            if model.current_speaker_participant_id is None:
                model.current_speaker_participant_id = "visitor_interaction"
            model.speaker_hypothesis_source = "direct_interaction"
            model.speaker_hypothesis_expires_at = now + timedelta(seconds=self.freshness_policy.speaker_hypothesis_window.ttl_seconds)
            self._set_engagement(model, state=EngagementState.ENGAGED, confidence=confidence_from_payload(0.85), now=now)
            self._set_attention(
                model,
                target_type=AttentionTargetType.PARTICIPANT,
                target_label="visitor_interaction",
                confidence=confidence_from_payload(0.8),
                now=now,
                rationale="direct_interaction_signal",
                source_tier=PerceptionTier.WATCHER,
                speaker_source="direct_interaction",
            )

        elif event.event_type == PerceptionEventType.VISIBLE_TEXT_DETECTED.value:
            text = str(event.payload.get("text") or "").strip()
            if text:
                model.recent_visible_text.insert(
                    0,
                    WorldModelObservation(
                        label=text,
                        confidence=confidence_from_payload(event.payload.get("confidence"), fallback=0.72),
                        claim_kind=claim_kind,
                        quality_class=self._quality_class(confidence_from_payload(event.payload.get("confidence"), fallback=0.72)),
                        observed_at=observed_at,
                        expires_at=observed_at + timedelta(seconds=self.observation_ttl_seconds),
                        source_event_type=event.event_type,
                        freshness=FactFreshness.FRESH,
                        provenance=self._provenance(event),
                        source_tier=context["tier"],
                    ),
                )

        elif event.event_type == PerceptionEventType.NAMED_OBJECT_DETECTED.value:
            object_name = str(event.payload.get("object_name") or "").strip()
            if object_name:
                model.recent_named_objects.insert(
                    0,
                    WorldModelObservation(
                        label=object_name,
                        confidence=confidence_from_payload(event.payload.get("confidence"), fallback=0.7),
                        claim_kind=claim_kind,
                        quality_class=self._quality_class(confidence_from_payload(event.payload.get("confidence"), fallback=0.7)),
                        observed_at=observed_at,
                        expires_at=observed_at + timedelta(seconds=self.observation_ttl_seconds),
                        source_event_type=event.event_type,
                        freshness=FactFreshness.FRESH,
                        provenance=self._provenance(event),
                        source_tier=context["tier"],
                    ),
                )
                if classify_anchor_type(object_name) is not None:
                    self._upsert_anchor(
                        model,
                        label=object_name,
                        anchor_type=classify_anchor_type(object_name) or VisualAnchorType.OBJECT,
                        confidence=confidence_from_payload(event.payload.get("confidence"), fallback=0.7),
                        now=observed_at,
                        source_event_type=event.event_type,
                        source_tier=context["tier"],
                        provenance=self._provenance(event),
                        claim_kind=claim_kind,
                    )

        elif event.event_type == PerceptionEventType.LOCATION_ANCHOR_DETECTED.value:
            anchor_name = str(event.payload.get("anchor_name") or "").strip()
            if anchor_name:
                self._upsert_anchor(
                    model,
                    label=anchor_name,
                    anchor_type=classify_anchor_type(anchor_name) or VisualAnchorType.SIGN,
                    confidence=confidence_from_payload(event.payload.get("confidence"), fallback=0.78),
                    now=observed_at,
                    source_event_type=event.event_type,
                    source_tier=context["tier"],
                    provenance=self._provenance(event),
                    claim_kind=claim_kind,
                )
                self._set_attention(
                    model,
                    target_type=attention_target_for_anchor(anchor_name),
                    target_label=anchor_name,
                    confidence=confidence_from_payload(event.payload.get("confidence"), fallback=0.74),
                    now=observed_at,
                    rationale="visible_anchor_guidance",
                    source_tier=context["tier"],
                    claim_kind=claim_kind,
                )

        elif event.event_type == PerceptionEventType.PARTICIPANT_ATTRIBUTE_DETECTED.value:
            attribute_text = str(event.payload.get("attribute_text") or "").strip()
            justification = str(event.payload.get("justification") or "").strip() or None
            if attribute_text and justification:
                model.recent_participant_attributes.insert(
                    0,
                    WorldModelObservation(
                        label=attribute_text,
                        confidence=confidence_from_payload(event.payload.get("confidence"), fallback=0.66),
                        claim_kind=claim_kind,
                        quality_class=self._quality_class(confidence_from_payload(event.payload.get("confidence"), fallback=0.66)),
                        justification=justification,
                        observed_at=observed_at,
                        expires_at=observed_at + timedelta(seconds=self.observation_ttl_seconds),
                        source_event_type=event.event_type,
                        freshness=FactFreshness.FRESH,
                        provenance=self._provenance(event),
                        source_tier=context["tier"],
                    ),
                )

        elif event.event_type == PerceptionEventType.SCENE_SUMMARY_UPDATED.value:
            model.last_perception_at = observed_at
            model.perception_limited_awareness = bool(event.payload.get("limited_awareness", False))
            if model.perception_limited_awareness and model.executive_state == InteractionExecutiveState.IDLE:
                model.executive_state = InteractionExecutiveState.DEGRADED

        elif event.event_type == "low_battery":
            model.executive_state = InteractionExecutiveState.SAFE_IDLE
            model.turn_state = InteractionExecutiveState.SAFE_IDLE

        elif event.event_type == "heartbeat" and not event.payload.get("network_ok", True):
            model.executive_state = InteractionExecutiveState.SAFE_IDLE
            model.turn_state = InteractionExecutiveState.SAFE_IDLE

        if event.event_type in {item.value for item in PerceptionEventType}:
            model.last_perception_at = observed_at
            model.perception_limited_awareness = context["limited_awareness"]

        self._apply_perception_context(model, event=event, now=observed_at, context=context)
        model.social_runtime_mode = social_mode_for_event(
            event_type=event.event_type,
            limited_awareness=context["limited_awareness"],
            scene_freshness=model.scene_freshness,
        )

        model.visual_anchors = model.visual_anchors[:8]
        model.recent_visible_text = model.recent_visible_text[:8]
        model.recent_named_objects = model.recent_named_objects[:8]
        model.recent_participant_attributes = model.recent_participant_attributes[:6]
        self.memory.replace_world_model(model)
        return model

    def apply_response(
        self,
        *,
        session: SessionRecord,
        response: CommandBatch,
        intent: str,
        decisions: list[ExecutiveDecisionRecord],
        at_time=None,
    ) -> EmbodiedWorldModel:
        now = at_time or utc_now()
        model = self._prune(self.memory.get_world_model(), now=now)
        model.last_updated = now

        if decisions:
            model.executive_state = decisions[-1].executive_state

        if any(decision.decision_type == ExecutiveDecisionType.STOP_FOR_INTERRUPTION for decision in decisions):
            model.last_interruption_at = now
            if response.reply_text and any(command.command_type == CommandType.SPEAK for command in response.commands):
                model.turn_state = InteractionExecutiveState.RESPONDING
                model.executive_state = InteractionExecutiveState.RESPONDING
                model.last_robot_speech_at = now
            else:
                model.turn_state = InteractionExecutiveState.INTERRUPTED
        elif any(decision.decision_type == ExecutiveDecisionType.FORCE_SAFE_IDLE for decision in decisions):
            model.turn_state = InteractionExecutiveState.SAFE_IDLE
            model.executive_state = InteractionExecutiveState.SAFE_IDLE
        elif response.reply_text and any(command.command_type == CommandType.SPEAK for command in response.commands):
            model.turn_state = InteractionExecutiveState.RESPONDING
            model.executive_state = InteractionExecutiveState.RESPONDING
            model.last_robot_speech_at = now
        elif any(decision.decision_type == ExecutiveDecisionType.KEEP_LISTENING for decision in decisions):
            model.turn_state = InteractionExecutiveState.LISTENING
            model.executive_state = InteractionExecutiveState.LISTENING
        elif any(decision.decision_type == ExecutiveDecisionType.DEFER_REPLY for decision in decisions):
            model.turn_state = InteractionExecutiveState.MONITORING
            model.executive_state = InteractionExecutiveState.MONITORING
        elif response.reply_text:
            model.turn_state = InteractionExecutiveState.MONITORING
        elif model.turn_state == InteractionExecutiveState.RESPONDING and model.last_robot_speech_at:
            if (now - model.last_robot_speech_at).total_seconds() > self.responding_window_seconds:
                model.turn_state = InteractionExecutiveState.MONITORING

        if intent == "wayfinding" and (last_location := session.session_memory.get("last_location")):
            location = COMMUNITY_LOCATIONS.get(last_location)
            if location is not None:
                self._set_attention(
                    model,
                    target_type=AttentionTargetType.ROOM_LABEL,
                    target_label=location.title,
                    confidence=confidence_from_payload(0.84),
                    now=now,
                    rationale="wayfinding_landmark_focus",
                    source_tier=PerceptionTier.SEMANTIC,
                )
        elif intent.startswith("operator_handoff"):
            self._set_attention(
                model,
                target_type=AttentionTargetType.OPERATOR,
                target_label="human_operator",
                confidence=confidence_from_payload(0.9),
                now=now,
                rationale="operator_handoff_focus",
                source_tier=PerceptionTier.SEMANTIC,
            )
        elif response.reply_text and not any(command.command_type == CommandType.STOP for command in response.commands):
            target_label = model.current_speaker_participant_id or "active_visitor"
            self._set_attention(
                model,
                target_type=AttentionTargetType.PARTICIPANT,
                target_label=target_label,
                confidence=confidence_from_payload(0.76),
                now=now,
                rationale="reply_directed_to_active_visitor",
                source_tier=PerceptionTier.WATCHER,
                speaker_source=model.speaker_hypothesis_source or "retained_active_speaker",
            )

        model.social_runtime_mode = social_mode_for_response(
            world_model=model,
            intent=intent,
            decisions=decisions,
            response_has_speech=bool(response.reply_text and any(command.command_type == CommandType.SPEAK for command in response.commands)),
        )
        self.memory.replace_world_model(model)
        return model

    def _prune(self, model: EmbodiedWorldModel, *, now) -> EmbodiedWorldModel:
        model.active_participants_in_view = [
            self._with_freshness(item, now=now)
            for item in model.active_participants_in_view
            if item.expires_at is None or item.expires_at >= now
        ]
        model.visual_anchors = [
            self._with_freshness(item, now=now)
            for item in model.visual_anchors
            if item.expires_at is None or item.expires_at >= now
        ]
        model.recent_visible_text = [
            self._with_freshness(item, now=now)
            for item in model.recent_visible_text
            if item.expires_at is None or item.expires_at >= now
        ]
        model.recent_named_objects = [
            self._with_freshness(item, now=now)
            for item in model.recent_named_objects
            if item.expires_at is None or item.expires_at >= now
        ]
        model.recent_participant_attributes = [
            self._with_freshness(item, now=now)
            for item in model.recent_participant_attributes
            if item.expires_at is None or item.expires_at >= now
        ]
        if model.attention_target and model.attention_target.expires_at and model.attention_target.expires_at < now:
            model.attention_target = None
        elif model.attention_target is not None:
            model.attention_target = self._with_freshness(model.attention_target, now=now)
        if model.engagement_expires_at and model.engagement_expires_at < now:
            model.engagement_state = EngagementState.UNKNOWN
            model.engagement_confidence = confidence_from_payload(0.2)
            model.engagement_observed_at = None
            model.engagement_expires_at = None
        if model.environment_expires_at and model.environment_expires_at < now:
            model.environment_state = EnvironmentState.UNKNOWN
            model.environment_confidence = confidence_from_payload(0.2)
            model.environment_observed_at = None
            model.environment_expires_at = None
        if model.turn_state == InteractionExecutiveState.RESPONDING and model.last_robot_speech_at:
            if (now - model.last_robot_speech_at).total_seconds() > self.responding_window_seconds:
                model.turn_state = InteractionExecutiveState.MONITORING
                if model.executive_state == InteractionExecutiveState.RESPONDING:
                    model.executive_state = InteractionExecutiveState.MONITORING
        if not model.active_participants_in_view and model.current_speaker_participant_id not in {None, "unseen_speaker"}:
            model.current_speaker_participant_id = None
        if model.speaker_hypothesis_expires_at and model.speaker_hypothesis_expires_at < now:
            model.speaker_hypothesis_source = None
            model.speaker_hypothesis_expires_at = None
            if model.current_speaker_participant_id not in {None, "unseen_speaker"}:
                model.current_speaker_participant_id = None
        model.scene_freshness = self._scene_freshness(model, now=now)
        return model

    def _set_participants(
        self,
        model: EmbodiedWorldModel,
        *,
        count: int,
        confidence: PerceptionConfidence,
        now,
        source_event_type: str,
        participant_ids: list[str] | None = None,
        source_tier: PerceptionTier = PerceptionTier.WATCHER,
        claim_kind: SceneClaimKind | None = None,
    ) -> None:
        participants = []
        resolved_ids = participant_ids or []
        resolved_claim_kind = self._claim_kind(source_tier, explicit=claim_kind)
        quality_class = self._quality_class(confidence)
        for index in range(max(count, 0)):
            participant_id = resolved_ids[index] if index < len(resolved_ids) else f"likely_participant_{index + 1}"
            participants.append(
                WorldModelParticipant(
                    participant_id=participant_id,
                    label=self._participant_label(participant_id, index=index),
                    confidence=confidence,
                    claim_kind=resolved_claim_kind,
                    quality_class=quality_class,
                    in_view=True,
                    observed_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(seconds=self.participant_ttl_seconds),
                    source_event_type=source_event_type,
                    freshness=FactFreshness.FRESH,
                    provenance=[f"event:{source_event_type}"],
                    source_tier=source_tier,
                )
            )
        model.active_participants_in_view = participants
        if not participants and model.current_speaker_participant_id != "unseen_speaker":
            model.current_speaker_participant_id = None

    def _set_engagement(self, model: EmbodiedWorldModel, *, state: EngagementState, confidence: PerceptionConfidence, now) -> None:
        model.engagement_state = state
        model.engagement_confidence = confidence
        model.engagement_observed_at = now
        model.engagement_expires_at = now + timedelta(seconds=self.engagement_ttl_seconds)

    def _set_attention(
        self,
        model: EmbodiedWorldModel,
        *,
        target_type: AttentionTargetType,
        target_label: str,
        confidence: PerceptionConfidence,
        now,
        rationale: str,
        source_tier: PerceptionTier,
        claim_kind: SceneClaimKind | None = None,
        speaker_source: str | None = None,
    ) -> None:
        decision = build_attention_decision(
            target_type=target_type,
            target_label=target_label,
            confidence=confidence,
            ttl_seconds=self.attention_ttl_seconds,
            rationale=rationale,
            provenance=[f"attention:{rationale}"],
            source_tier=source_tier,
            claim_kind=self._claim_kind(source_tier, explicit=claim_kind),
            likely_speaker_participant_id=(
                target_label if target_type == AttentionTargetType.PARTICIPANT else model.current_speaker_participant_id
            ),
            speaker_source=(
                speaker_source
                or (
                    "explicit_participant_id"
                    if target_type == AttentionTargetType.PARTICIPANT and target_label.startswith("likely_participant_") is False
                    else "watcher_attention_hint"
                )
            ),
        )
        model.attention_target = decision.target
        if decision.likely_speaker_participant_id:
            model.current_speaker_participant_id = decision.likely_speaker_participant_id
            model.speaker_hypothesis_source = decision.speaker_source or "retained_active_speaker"
            model.speaker_hypothesis_expires_at = now + timedelta(seconds=self.freshness_policy.speaker_hypothesis_window.ttl_seconds)

    @staticmethod
    def _participant_ids_from_event(event: RobotEvent, *, expected_count: int) -> list[str]:
        raw_ids = [
            item
            for item in event.payload.get("participant_ids", []) or []
            if isinstance(item, str) and item.strip()
        ]
        participant_id = str(event.payload.get("participant_id") or "").strip()
        if participant_id and participant_id not in raw_ids:
            raw_ids.insert(0, participant_id)
        return raw_ids[:expected_count] if expected_count > 0 else []

    @staticmethod
    def _participant_label(participant_id: str, *, index: int) -> str:
        if participant_id.startswith("likely_participant_"):
            suffix = participant_id.removeprefix("likely_participant_")
            if suffix.isdigit():
                return f"likely visitor {suffix}"
        return f"likely visitor {index + 1}"

    def _upsert_anchor(
        self,
        model: EmbodiedWorldModel,
        *,
        label: str,
        anchor_type: VisualAnchorType,
        confidence: PerceptionConfidence,
        now,
        source_event_type: str,
        source_tier: PerceptionTier,
        provenance: list[str],
        claim_kind: SceneClaimKind | None = None,
    ) -> None:
        remaining = [item for item in model.visual_anchors if item.label.lower() != label.lower()]
        remaining.insert(
            0,
            WorldModelAnchor(
                anchor_type=anchor_type,
                label=label,
                confidence=confidence,
                claim_kind=self._claim_kind(source_tier, explicit=claim_kind),
                quality_class=self._quality_class(confidence),
                observed_at=now,
                expires_at=now + timedelta(seconds=self.anchor_ttl_seconds),
                source_event_type=source_event_type,
                freshness=FactFreshness.FRESH,
                provenance=provenance,
                source_tier=source_tier,
            ),
        )
        model.visual_anchors = remaining

    def _apply_perception_context(self, model: EmbodiedWorldModel, *, event: RobotEvent, now, context: dict[str, object]) -> None:
        if event.event_type not in {item.value for item in PerceptionEventType}:
            return
        tier = context["tier"]
        claim_kind = context["claim_kind"]
        trigger_reason = context["trigger_reason"]
        environment_state = context["environment_state"]
        device_constraints = context["device_constraints"]
        uncertainty_markers = context["uncertainty_markers"]

        model.perception_limited_awareness = bool(context["limited_awareness"])
        model.uncertainty_markers = list(dict.fromkeys(uncertainty_markers))
        model.device_awareness_constraints = list(dict.fromkeys(device_constraints))
        if isinstance(environment_state, EnvironmentState):
            model.environment_state = environment_state
            model.environment_confidence = confidence_from_payload(event.payload.get("confidence"), fallback=0.62)
            model.environment_observed_at = now
            model.environment_expires_at = now + timedelta(seconds=self.observation_ttl_seconds)
        if tier == PerceptionTier.SEMANTIC:
            model.last_semantic_refresh_at = now
            model.last_semantic_refresh_reason = trigger_reason
        else:
            model.latest_observer_event_at = now
            if (
                str(event.payload.get("attention_state") or "").strip() == "toward_device"
                and model.current_speaker_participant_id is None
                and model.active_participants_in_view
            ):
                model.current_speaker_participant_id = model.active_participants_in_view[0].participant_id
                model.speaker_hypothesis_source = "watcher_attention_hint"
                model.speaker_hypothesis_expires_at = now + timedelta(seconds=self.freshness_policy.speaker_hypothesis_window.ttl_seconds)
        model.scene_freshness = self._freshness_for_timestamp(
            now,
            now,
            claim_kind=claim_kind,
        )
        if model.perception_limited_awareness:
            model.social_runtime_mode = SocialRuntimeMode.DEGRADED_AWARENESS

    @staticmethod
    def _perception_context(event: RobotEvent) -> dict[str, object]:
        raw_tier = str(event.payload.get("tier") or PerceptionTier.WATCHER.value)
        tier = PerceptionTier(raw_tier) if raw_tier in PerceptionTier._value2member_map_ else PerceptionTier.WATCHER
        raw_environment = str(event.payload.get("environment_state") or EnvironmentState.UNKNOWN.value)
        environment_state = (
            EnvironmentState(raw_environment)
            if raw_environment in EnvironmentState._value2member_map_
            else EnvironmentState.UNKNOWN
        )
        device_constraints = [
            str(item).strip()
            for item in event.payload.get("device_awareness_constraints", []) or []
            if str(item).strip()
        ]
        uncertainty_markers = [
            str(item).strip()
            for item in event.payload.get("uncertainty_markers", []) or []
            if str(item).strip()
        ]
        if tier == PerceptionTier.WATCHER and "watcher_only_scene_facts" not in uncertainty_markers:
            uncertainty_markers.append("watcher_only_scene_facts")
        if bool(event.payload.get("limited_awareness")) and "limited_awareness" not in uncertainty_markers:
            uncertainty_markers.append("limited_awareness")
        explicit_claim_kind = str(event.payload.get("claim_kind") or "").strip()
        claim_kind = (
            SceneClaimKind(explicit_claim_kind)
            if explicit_claim_kind in SceneClaimKind._value2member_map_
            else (SceneClaimKind.WATCHER_HINT if tier == PerceptionTier.WATCHER else SceneClaimKind.SEMANTIC_OBSERVATION)
        )
        captured_at_raw = str(event.payload.get("captured_at") or "").strip()
        observed_at = None
        if captured_at_raw:
            try:
                observed_at = datetime.fromisoformat(captured_at_raw)
            except ValueError:
                observed_at = None
        return {
            "tier": tier,
            "claim_kind": claim_kind,
            "observed_at": observed_at,
            "limited_awareness": bool(event.payload.get("limited_awareness", False)),
            "trigger_reason": str(event.payload.get("trigger_reason") or "").strip() or None,
            "environment_state": environment_state,
            "device_constraints": device_constraints,
            "uncertainty_markers": uncertainty_markers,
        }

    @staticmethod
    def _provenance(event: RobotEvent) -> list[str]:
        refs = [f"event:{event.event_type}"]
        source_kind = str(event.payload.get("source_kind") or "").strip()
        if source_kind:
            refs.append(f"source:{source_kind}")
        return refs

    def _scene_freshness(self, model: EmbodiedWorldModel, *, now) -> FactFreshness:
        reference_at = model.last_semantic_refresh_at or model.last_perception_at or model.latest_observer_event_at
        if reference_at is None:
            return FactFreshness.UNKNOWN
        claim_kind = (
            SceneClaimKind.SEMANTIC_OBSERVATION
            if model.last_semantic_refresh_at is not None and model.last_semantic_refresh_at == reference_at
            else SceneClaimKind.WATCHER_HINT
        )
        return self._freshness_for_timestamp(reference_at, now, claim_kind=claim_kind)

    def _freshness_for_timestamp(self, reference_at, now, *, claim_kind: SceneClaimKind) -> FactFreshness:
        return self.freshness_policy.assessment(
            observed_at=reference_at,
            now=now,
            claim_kind=claim_kind,
        ).freshness

    def _with_freshness(self, item, *, now):
        reference_at = getattr(item, "observed_at", None)
        expires_at = getattr(item, "expires_at", None)
        claim_kind = getattr(item, "claim_kind", SceneClaimKind.SEMANTIC_OBSERVATION)
        assessment = self.freshness_policy.assessment(
            observed_at=reference_at,
            now=now,
            expires_at=expires_at,
            claim_kind=claim_kind,
        )
        return item.model_copy(update={"freshness": assessment.freshness})

    @staticmethod
    def _claim_kind(source_tier: PerceptionTier, *, explicit: SceneClaimKind | None = None) -> SceneClaimKind:
        if explicit is not None:
            return explicit
        if source_tier == PerceptionTier.WATCHER:
            return SceneClaimKind.WATCHER_HINT
        return SceneClaimKind.SEMANTIC_OBSERVATION

    @staticmethod
    def _quality_class(confidence: PerceptionConfidence) -> SemanticQualityClass | None:
        if confidence.label in SemanticQualityClass._value2member_map_:
            return SemanticQualityClass(confidence.label)
        return None


def confidence_from_payload(value, *, fallback: float = 0.5) -> PerceptionConfidence:
    try:
        score = float(value) if value is not None else float(fallback)
    except (TypeError, ValueError):
        score = float(fallback)
    bounded = max(0.0, min(1.0, score))
    if bounded >= 0.8:
        label = "high"
    elif bounded >= 0.55:
        label = "medium"
    else:
        label = "low"
    return PerceptionConfidence(score=bounded, label=label)


def classify_anchor_type(label: str) -> VisualAnchorType | None:
    lowered = label.lower()
    if "desk" in lowered:
        return VisualAnchorType.DESK
    if "screen" in lowered or "display" in lowered or "monitor" in lowered:
        return VisualAnchorType.SCREEN
    if "poster" in lowered or "banner" in lowered:
        return VisualAnchorType.POSTER
    if "room" in lowered:
        return VisualAnchorType.ROOM_LABEL
    if "sign" in lowered or "arrow" in lowered or "check-in" in lowered:
        return VisualAnchorType.SIGN
    if lowered:
        return VisualAnchorType.OBJECT
    return None


def attention_target_for_anchor(label: str) -> AttentionTargetType:
    anchor_type = classify_anchor_type(label)
    mapping = {
        VisualAnchorType.DESK: AttentionTargetType.DESK,
        VisualAnchorType.SCREEN: AttentionTargetType.SCREEN,
        VisualAnchorType.POSTER: AttentionTargetType.POSTER,
        VisualAnchorType.ROOM_LABEL: AttentionTargetType.ROOM_LABEL,
        VisualAnchorType.SIGN: AttentionTargetType.SIGN,
        VisualAnchorType.OBJECT: AttentionTargetType.OBJECT,
    }
    return mapping.get(anchor_type or VisualAnchorType.OBJECT, AttentionTargetType.OBJECT)
