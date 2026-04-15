from __future__ import annotations

from datetime import timedelta

from embodied_stack.brain.orchestration.interaction import select_dialogue_perception_snapshot
from embodied_stack.shared.models import (
    PerceptionConfidence,
    PerceptionObservation,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSnapshotRecord,
    PerceptionSnapshotStatus,
    PerceptionSourceFrame,
    utc_now,
)


def _snapshot(
    *,
    provider_mode: PerceptionProviderMode,
    status: PerceptionSnapshotStatus,
    source: str,
    scene_summary: str,
    limited_awareness: bool,
    age_seconds: float,
    observations: list[PerceptionObservation] | None = None,
) -> PerceptionSnapshotRecord:
    captured_at = utc_now() - timedelta(seconds=age_seconds)
    source_frame = PerceptionSourceFrame(
        source_kind=provider_mode.value,
        captured_at=captured_at,
    )
    return PerceptionSnapshotRecord(
        session_id="visual-session",
        provider_mode=provider_mode,
        source=source,
        status=status,
        limited_awareness=limited_awareness,
        scene_summary=scene_summary,
        source_frame=source_frame,
        observations=observations or [],
    )


def test_visual_queries_prefer_recent_semantic_snapshot_over_scene_observer_note():
    semantic = _snapshot(
        provider_mode=PerceptionProviderMode.OLLAMA_VISION,
        status=PerceptionSnapshotStatus.OK,
        source="before_reply_generation",
        scene_summary="A front desk and lobby sign are visible.",
        limited_awareness=False,
        age_seconds=8,
        observations=[
            PerceptionObservation(
                observation_type=PerceptionObservationType.LOCATION_ANCHOR,
                text_value="front desk",
                confidence=PerceptionConfidence(score=0.85, label="high"),
                source_frame=PerceptionSourceFrame(source_kind="ollama_vision"),
            )
        ],
    )
    watcher = _snapshot(
        provider_mode=PerceptionProviderMode.MANUAL_ANNOTATIONS,
        status=PerceptionSnapshotStatus.OK,
        source="scene_observer",
        scene_summary="scene observer motion changed",
        limited_awareness=False,
        age_seconds=2,
        observations=[
            PerceptionObservation(
                observation_type=PerceptionObservationType.SCENE_SUMMARY,
                text_value="scene observer motion changed",
                confidence=PerceptionConfidence(score=0.9, label="high"),
                source_frame=PerceptionSourceFrame(source_kind="manual_annotations"),
            )
        ],
    )

    selected = select_dialogue_perception_snapshot([watcher, semantic], visual_query=True)

    assert selected is semantic


def test_failed_semantic_snapshot_does_not_outrank_useful_nonsemantic_snapshot():
    failed_semantic = _snapshot(
        provider_mode=PerceptionProviderMode.OLLAMA_VISION,
        status=PerceptionSnapshotStatus.FAILED,
        source="before_reply_generation",
        scene_summary="Perception is currently limited.",
        limited_awareness=True,
        age_seconds=1,
    )
    watcher = _snapshot(
        provider_mode=PerceptionProviderMode.MANUAL_ANNOTATIONS,
        status=PerceptionSnapshotStatus.OK,
        source="scene_observer",
        scene_summary="One person is still in view near the display.",
        limited_awareness=False,
        age_seconds=2,
        observations=[
            PerceptionObservation(
                observation_type=PerceptionObservationType.PEOPLE_COUNT,
                number_value=1,
                confidence=PerceptionConfidence(score=0.8, label="high"),
                source_frame=PerceptionSourceFrame(source_kind="manual_annotations"),
            )
        ],
    )

    selected = select_dialogue_perception_snapshot([failed_semantic, watcher], visual_query=True)

    assert selected is watcher


def test_recent_limited_awareness_snapshot_beats_materially_older_grounded_scene_for_visual_queries():
    older_grounded = _snapshot(
        provider_mode=PerceptionProviderMode.OLLAMA_VISION,
        status=PerceptionSnapshotStatus.OK,
        source="before_reply_generation",
        scene_summary="A workshop room sign is clearly visible.",
        limited_awareness=False,
        age_seconds=25,
        observations=[
            PerceptionObservation(
                observation_type=PerceptionObservationType.VISIBLE_TEXT,
                text_value="Workshop Room",
                confidence=PerceptionConfidence(score=0.9, label="high"),
                source_frame=PerceptionSourceFrame(source_kind="ollama_vision"),
            )
        ],
    )
    recent_degraded = _snapshot(
        provider_mode=PerceptionProviderMode.STUB,
        status=PerceptionSnapshotStatus.DEGRADED,
        source="investor_scene",
        scene_summary="Perception is running in stub mode. Situational awareness is limited.",
        limited_awareness=True,
        age_seconds=0,
    )

    selected = select_dialogue_perception_snapshot([older_grounded, recent_degraded], visual_query=True)

    assert selected is recent_degraded
