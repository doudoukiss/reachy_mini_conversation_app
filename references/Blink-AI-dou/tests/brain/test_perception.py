from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import httpx
from PIL import Image

from embodied_stack.brain.perception import OllamaVisionPerceptionProvider
from embodied_stack.shared.models import (
    PerceptionSnapshotStatus,
    PerceptionSnapshotSubmitRequest,
    PerceptionSourceFrame,
    PerceptionTier,
)


TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WnS7S4AAAAASUVORK5CYII="
)


def _large_png_data_url(width: int = 1600, height: int = 900) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(220, 220, 220)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def test_stub_perception_provider_reports_limited_awareness(brain_client):
    response = brain_client.post(
        "/api/operator/perception/snapshots",
        json={
            "session_id": "perception-stub",
            "provider_mode": "stub",
            "publish_events": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["snapshot"]["status"] == "degraded"
    assert body["snapshot"]["limited_awareness"] is True
    assert body["snapshot"]["dialogue_eligible"] is False
    assert "limited" in body["snapshot"]["scene_summary"].lower()
    assert body["snapshot"]["events"][0]["event_type"] == "scene_summary_updated"


def test_manual_annotations_publish_structured_perception_events(brain_client):
    response = brain_client.post(
        "/api/operator/perception/snapshots",
        json={
            "session_id": "perception-manual",
            "provider_mode": "manual_annotations",
            "annotations": [
                {"observation_type": "people_count", "number_value": 1, "confidence": 0.96},
                {"observation_type": "visible_text", "text_value": "Check-In", "confidence": 0.84},
                {"observation_type": "location_anchor", "text_value": "Front Desk", "confidence": 0.88},
                {"observation_type": "scene_summary", "text_value": "One visitor is visible near the front desk sign.", "confidence": 0.8},
            ],
            "publish_events": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    event_types = {item["event_type"] for item in body["snapshot"]["events"]}
    assert {
        "person_visible",
        "people_count_changed",
        "visible_text_detected",
        "location_anchor_detected",
        "scene_summary_updated",
    } <= event_types
    assert body["snapshot"]["dialogue_eligible"] is True
    assert all(item["claim_kind"] == "operator_annotation" for item in body["snapshot"]["observations"])
    assert any(item["response"]["reply_text"] for item in body["published_results"])

    session = brain_client.get("/api/sessions/perception-manual")
    assert session.status_code == 200
    assert session.json()["transcript"][0]["event_type"] == "person_visible"


def test_watcher_tier_snapshot_normalizes_engagement_and_uncertainty(brain_client):
    response = brain_client.post(
        "/api/operator/perception/snapshots",
        json={
            "session_id": "perception-watcher",
            "provider_mode": "manual_annotations",
            "tier": "watcher",
            "trigger_reason": "new_arrival",
            "metadata": {
                "observer_capability_limits": ["person_attention_detection_unavailable"],
            },
            "annotations": [
                {"observation_type": "people_count", "number_value": 1, "confidence": 0.92},
                {"observation_type": "engagement_estimate", "number_value": 0.8, "confidence": 0.9},
            ],
            "publish_events": False,
        },
    )
    assert response.status_code == 200
    body = response.json()["snapshot"]
    engagement = next(
        item for item in body["observations"] if item["observation_type"] == "engagement_estimate"
    )
    assert engagement["text_value"] == "engaged"
    assert body["tier"] == PerceptionTier.WATCHER.value
    assert body["trigger_reason"] == "new_arrival"
    assert body["dialogue_eligible"] is False
    assert all(item["claim_kind"] == "watcher_hint" for item in body["observations"])
    assert "watcher_only_scene_facts" in body["uncertainty_markers"]
    assert body["device_awareness_constraints"] == ["person_attention_detection_unavailable"]


def test_browser_snapshot_ingestion_preserves_source_metadata(brain_client):
    response = brain_client.post(
        "/api/operator/perception/snapshots",
        json={
            "session_id": "perception-browser",
            "provider_mode": "browser_snapshot",
            "image_data_url": TINY_PNG_DATA_URL,
            "source_frame": {
                "source_kind": "browser_camera_snapshot",
                "source_label": "operator_console_camera",
                "frame_id": "browser-frame-1",
                "width_px": 640,
                "height_px": 480,
            },
            "publish_events": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["source_frame"]["frame_id"] == "browser-frame-1"
    assert body["snapshot"]["source_frame"]["width_px"] == 640
    assert body["snapshot"]["source_frame"]["mime_type"] == "image/png"
    persisted_path = Path(body["snapshot"]["source_frame"]["fixture_path"])
    assert persisted_path.exists()
    assert persisted_path.read_bytes()
    assert persisted_path.name.endswith(".png")
    latest_path = persisted_path.parents[1] / "latest_browser_snapshot.png"
    assert latest_path.exists()
    assert body["snapshot"]["limited_awareness"] is True


def test_perception_history_and_latest_snapshot_are_queryable(brain_client):
    first = brain_client.post(
        "/api/operator/perception/snapshots",
        json={
            "session_id": "perception-history",
            "provider_mode": "manual_annotations",
            "annotations": [{"observation_type": "people_count", "number_value": 1}],
        },
    )
    assert first.status_code == 200

    second = brain_client.post(
        "/api/operator/perception/snapshots",
        json={
            "session_id": "perception-history",
            "provider_mode": "manual_annotations",
            "annotations": [{"observation_type": "people_count", "number_value": 2}],
        },
    )
    assert second.status_code == 200

    latest = brain_client.get("/api/operator/perception/latest", params={"session_id": "perception-history"})
    assert latest.status_code == 200
    assert latest.json()["observations"][0]["number_value"] == 2.0

    history = brain_client.get("/api/operator/perception/history", params={"session_id": "perception-history", "limit": 2})
    assert history.status_code == 200
    items = history.json()["items"]
    assert len(items) == 2
    assert items[0]["observations"][0]["number_value"] == 2.0
    assert items[1]["observations"][0]["number_value"] == 1.0


def test_operator_snapshot_exposes_perception_state_and_fixture_catalog(brain_client):
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "embodied_stack"
        / "demo"
        / "data"
        / "perception_lobby_arrival.json"
    )
    replay = brain_client.post(
        "/api/operator/perception/replay",
        json={"session_id": "perception-replay", "fixture_path": str(fixture_path)},
    )
    assert replay.status_code == 200
    assert replay.json()["success"] is True

    snapshot = brain_client.get("/api/operator/snapshot", params={"session_id": "perception-replay"})
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["runtime"]["perception_provider_mode"] == "native_camera_snapshot"
    assert body["latest_perception"]["source_frame"]["source_kind"] == "video_file_replay"
    assert body["perception_history"]["items"]

    fixtures = brain_client.get("/api/operator/perception/fixtures")
    assert fixtures.status_code == 200
    fixture_names = {item["fixture_name"] for item in fixtures.json()["items"]}
    assert {"lobby_arrival", "noticeboard_scan"} <= fixture_names


def test_multimodal_provider_failure_degrades_honestly_without_fake_claims(brain_client):
    response = brain_client.post(
        "/api/operator/perception/snapshots",
        json={
            "session_id": "perception-failure",
            "provider_mode": "multimodal_llm",
            "image_data_url": TINY_PNG_DATA_URL,
            "publish_events": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["snapshot"]["status"] == "failed"
    assert body["snapshot"]["limited_awareness"] is True
    assert "limited" in body["snapshot"]["scene_summary"].lower()
    event_types = {item["event_type"] for item in body["snapshot"]["events"]}
    assert event_types == {"scene_summary_updated"}


def test_ollama_vision_provider_downscales_frames_and_parses_fenced_json():
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        observed["think"] = payload["think"]
        encoded = payload["messages"][1]["images"][0]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as resized:
            observed["size"] = resized.size
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": """```json
{"scene_summary":"A front desk monitor and lobby sign are visible.","limited_awareness":"false","message":"ollama_vision_processed","observations":[{"observation_type":"location_anchor","text_value":"front desk","confidence":0.82},{"observation_type":"named_object","text_value":"monitor","confidence":0.71}]}
```"""
                }
            },
        )

    provider = OllamaVisionPerceptionProvider(
        base_url="http://ollama.local",
        model="qwen3.5:9b",
        timeout_seconds=30.0,
        transport=httpx.MockTransport(handler),
    )
    snapshot = provider.analyze_snapshot(
        PerceptionSnapshotSubmitRequest(
            session_id="vision-local",
            provider_mode="ollama_vision",
            source="unit_test",
            image_data_url=_large_png_data_url(),
            source_frame=PerceptionSourceFrame(source_kind="browser_camera_snapshot"),
        )
    )

    assert observed["think"] is False
    assert max(observed["size"]) <= 512
    assert snapshot.status == PerceptionSnapshotStatus.OK
    assert snapshot.scene_summary == "A front desk monitor and lobby sign are visible."
    assert {item.text_value for item in snapshot.observations if item.text_value} >= {"front desk", "monitor"}
