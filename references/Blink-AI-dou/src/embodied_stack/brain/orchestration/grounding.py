from __future__ import annotations

import logging

from embodied_stack.brain.freshness import DEFAULT_FRESHNESS_POLICY
from embodied_stack.shared.models import (
    EmbodiedWorldModel,
    ExecutiveDecisionRecord,
    FactFreshness,
    GroundingSourceRecord,
    GroundingSourceType,
    PerceptionSnapshotRecord,
    PerceptionTier,
    SceneClaimKind,
    SessionRecord,
    ShiftSupervisorSnapshot,
    ShiftTransitionRecord,
    ToolInvocationRecord,
    UserMemoryRecord,
)

logger = logging.getLogger(__name__)


class GroundingSourceBuilder:
    def collect(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        tool_invocations: list[ToolInvocationRecord],
        latest_perception: PerceptionSnapshotRecord | None,
        world_model: EmbodiedWorldModel | None,
    ) -> list[GroundingSourceRecord]:
        try:
            sources: list[GroundingSourceRecord] = []

            for tool in tool_invocations:
                metadata = dict(tool.metadata)
                sources.append(
                    GroundingSourceRecord(
                        source_type=GroundingSourceType.TOOL,
                        label=tool.tool_name,
                        source_ref=str(metadata.get("knowledge_source") or "tool"),
                        detail=tool.answer_text,
                        metadata=metadata,
                    )
                )
                source_type = self._grounding_type_for_knowledge_source(str(metadata.get("knowledge_source") or ""))
                if source_type is not None:
                    refs = metadata.get("source_refs", []) or [metadata.get("memory_id"), metadata.get("user_id")]
                    refs = [str(item) for item in refs if item]
                    sources.append(
                        GroundingSourceRecord(
                            source_type=source_type,
                            label=tool.tool_name,
                            source_ref=refs[0] if refs else None,
                            confidence=metadata.get("confidence"),
                            detail=tool.answer_text,
                            metadata=metadata,
                        )
                    )
                for source_ref in metadata.get("source_refs", []) or []:
                    sources.append(
                        GroundingSourceRecord(
                            source_type=source_type or GroundingSourceType.VENUE,
                            label=tool.tool_name,
                            source_ref=str(source_ref),
                            metadata={"tool_name": tool.tool_name},
                        )
                    )

            if latest_perception is not None:
                confidence_values = [
                    item.confidence.score
                    for item in latest_perception.observations
                    if item.confidence and item.confidence.score is not None
                ]
                sources.append(
                    GroundingSourceRecord(
                        source_type=GroundingSourceType.PERCEPTION,
                        label=latest_perception.scene_summary or latest_perception.provider_mode.value,
                        source_ref=latest_perception.source_frame.fixture_path or latest_perception.source_frame.file_name,
                        confidence=round(sum(confidence_values) / len(confidence_values), 2)
                        if confidence_values
                        else None,
                        detail=latest_perception.source_frame.source_kind,
                        metadata={
                            "provider_mode": latest_perception.provider_mode.value,
                            "limited_awareness": latest_perception.limited_awareness,
                            "source_kind": latest_perception.source_frame.source_kind,
                        },
                    )
                )
                if latest_perception.limited_awareness:
                    sources.append(
                        GroundingSourceRecord(
                            source_type=GroundingSourceType.LIMITED_AWARENESS,
                            label="perception_limited_awareness",
                            detail=latest_perception.message or latest_perception.scene_summary,
                            metadata={"provider_mode": latest_perception.provider_mode.value},
                        )
                    )
                observed_at = latest_perception.source_frame.captured_at or latest_perception.created_at
                snapshot_claim_kind = (
                    latest_perception.observations[0].claim_kind
                    if latest_perception.observations
                    else (SceneClaimKind.WATCHER_HINT if latest_perception.tier == PerceptionTier.WATCHER else SceneClaimKind.SEMANTIC_OBSERVATION)
                )
                freshness = DEFAULT_FRESHNESS_POLICY.assessment(
                    observed_at=observed_at,
                    claim_kind=snapshot_claim_kind,
                ).freshness if observed_at is not None else FactFreshness.UNKNOWN
                for observation in latest_perception.observations:
                    if observation.observation_type.value == "scene_summary":
                        continue
                    label = observation.text_value or (
                        str(int(observation.number_value))
                        if observation.number_value is not None
                        else str(observation.bool_value).lower() if observation.bool_value is not None else observation.observation_type.value
                    )
                    sources.append(
                        GroundingSourceRecord(
                            source_type=GroundingSourceType.PERCEPTION_FACT,
                            label=label,
                            source_ref=latest_perception.source_frame.fixture_path or latest_perception.source_frame.file_name,
                            fact_id=observation.observation_id,
                            claim_kind=observation.claim_kind,
                            freshness=freshness,
                            confidence=observation.confidence.score,
                            detail=observation.justification,
                            metadata={
                                "observation_type": observation.observation_type.value,
                                "quality_class": observation.quality_class.value if observation.quality_class is not None else None,
                            },
                        )
                    )

            if world_model is not None:
                sources.append(
                    GroundingSourceRecord(
                        source_type=GroundingSourceType.WORLD_MODEL,
                        label=world_model.engagement_state.value,
                        detail=world_model.attention_target.target_label if world_model.attention_target else None,
                        confidence=world_model.engagement_confidence.score,
                        metadata={
                            "participants_in_view": len(world_model.active_participants_in_view),
                            "attention_target": world_model.attention_target.target_label
                            if world_model.attention_target
                            else None,
                            "limited_awareness": world_model.perception_limited_awareness,
                        },
                    )
                )
                if world_model.attention_target is not None:
                    sources.append(
                        GroundingSourceRecord(
                            source_type=GroundingSourceType.PERCEPTION_FACT,
                            label=world_model.attention_target.target_label or "attention_target",
                            fact_id="attention_target",
                            claim_kind=world_model.attention_target.claim_kind,
                            freshness=world_model.attention_target.freshness,
                            confidence=world_model.attention_target.confidence.score,
                            detail=world_model.attention_target.rationale,
                            metadata={"source_tier": world_model.attention_target.source_tier.value},
                        )
                    )
                for collection, source_type in (
                    (world_model.recent_visible_text, GroundingSourceType.PERCEPTION_FACT),
                    (world_model.visual_anchors, GroundingSourceType.PERCEPTION_FACT),
                    (world_model.recent_named_objects, GroundingSourceType.PERCEPTION_FACT),
                    (world_model.recent_participant_attributes, GroundingSourceType.PERCEPTION_FACT),
                ):
                    for item in collection[:4]:
                        sources.append(
                            GroundingSourceRecord(
                                source_type=source_type,
                                label=item.label,
                                fact_id=getattr(item, "observation_id", getattr(item, "anchor_id", None)),
                                claim_kind=item.claim_kind,
                                freshness=item.freshness,
                                confidence=item.confidence.score,
                                detail=item.justification if hasattr(item, "justification") else None,
                                metadata={
                                    "source_tier": item.source_tier.value,
                                    "quality_class": item.quality_class.value if item.quality_class is not None else None,
                                },
                            )
                        )

            for note in session.operator_notes[-3:]:
                sources.append(
                    GroundingSourceRecord(
                        source_type=GroundingSourceType.OPERATOR_NOTE,
                        label=note.author or "operator",
                        detail=note.text,
                    )
                )

            if user_memory and user_memory.display_name:
                sources.append(
                    GroundingSourceRecord(
                        source_type=GroundingSourceType.USER_MEMORY,
                        label=user_memory.display_name,
                        detail=user_memory.user_id,
                    )
                )

            return self.dedupe(sources)
        except Exception:
            logger.exception("Failed to collect grounding sources for session %s", session.session_id)
            raise

    def executive_sources(
        self,
        decisions: list[ExecutiveDecisionRecord],
    ) -> list[GroundingSourceRecord]:
        sources: list[GroundingSourceRecord] = []
        for decision in decisions:
            sources.append(
                GroundingSourceRecord(
                    source_type=GroundingSourceType.EXECUTIVE_POLICY,
                    label=decision.decision_type.value,
                    detail=decision.note,
                    metadata={"reason_codes": list(decision.reason_codes)},
                )
            )
        return sources

    def shift_sources(
        self,
        snapshot: ShiftSupervisorSnapshot | None,
        transitions: list[ShiftTransitionRecord],
    ) -> list[GroundingSourceRecord]:
        if snapshot is None:
            return []
        sources = [
            GroundingSourceRecord(
                source_type=GroundingSourceType.SHIFT_POLICY,
                label=snapshot.state.value,
                detail=snapshot.last_policy_note,
                metadata={
                    "reason_codes": list(snapshot.reason_codes),
                    "override_active": snapshot.override_active,
                    "timers": [item.model_dump(mode="json") for item in snapshot.timers],
                },
            )
        ]
        for transition in transitions:
            sources.append(
                GroundingSourceRecord(
                    source_type=GroundingSourceType.SHIFT_POLICY,
                    label=f"{transition.from_state.value}->{transition.to_state.value}",
                    detail=transition.note,
                    metadata={"reason_codes": list(transition.reason_codes), "trigger": transition.trigger},
                )
            )
        return sources

    def merge(
        self,
        current: list[GroundingSourceRecord],
        additional: list[GroundingSourceRecord],
    ) -> list[GroundingSourceRecord]:
        return self.dedupe([*current, *additional])

    def _grounding_type_for_knowledge_source(self, knowledge_source: str) -> GroundingSourceType | None:
        mapping = {
            "profile_memory": GroundingSourceType.PROFILE_MEMORY,
            "episodic_memory": GroundingSourceType.EPISODIC_MEMORY,
            "semantic_memory": GroundingSourceType.SEMANTIC_MEMORY,
            "perception_facts": GroundingSourceType.PERCEPTION_FACT,
            "venue_document": GroundingSourceType.VENUE,
            "venue_pack": GroundingSourceType.VENUE,
        }
        return mapping.get(knowledge_source)

    def dedupe(
        self,
        sources: list[GroundingSourceRecord],
    ) -> list[GroundingSourceRecord]:
        deduped: list[GroundingSourceRecord] = []
        seen: set[tuple[str, str, str | None, str | None]] = set()
        for source in sources:
            key = (
                source.source_type.value,
                source.label,
                source.source_ref,
                source.detail,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(source)
        return deduped
