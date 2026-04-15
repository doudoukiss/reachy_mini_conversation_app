from __future__ import annotations

import json
from datetime import timedelta

import httpx

from embodied_stack.brain.llm import (
    DialogueContext,
    DialoguePromptBuilder,
    DialogueEngineFactory,
    FallbackDialogueEngine,
    GRSAIDialogueEngine,
    OllamaDialogueEngine,
    RuleBasedDialogueEngine,
)
from embodied_stack.shared.models import (
    CompanionContextMode,
    EmbodiedWorldModel,
    OperatorNote,
    PerceptionConfidence,
    PerceptionProviderMode,
    PerceptionSnapshotRecord,
    PerceptionSnapshotStatus,
    PerceptionSourceFrame,
    ResponseMode,
    SessionRecord,
    ToolInvocationRecord,
    UserMemoryRecord,
    WorldState,
    WorldModelObservation,
    utc_now,
)


def _build_context(
    *,
    with_tool: bool = True,
    context_mode: CompanionContextMode = CompanionContextMode.VENUE_DEMO,
) -> DialogueContext:
    tool_invocations = []
    if with_tool:
        tool_invocations.append(
            ToolInvocationRecord(
                tool_name="wayfinding_lookup",
                answer_text="The Front Desk is in the Lobby near the main entrance.",
                metadata={"location_key": "front_desk"},
                notes=["keyword_match:front_desk"],
            )
        )

    session = SessionRecord(
        session_id="provider-session",
        response_mode=ResponseMode.GUIDE,
        current_topic="wayfinding" if with_tool else None,
        conversation_summary="Visitor asked for directions to the front desk.",
        operator_notes=[OperatorNote(text="Offer the April volunteer packet if asked.")],
    )
    return DialogueContext(
        session=session,
        world_state=WorldState(),
        tool_invocations=tool_invocations,
        context_mode=context_mode,
        user_memory=UserMemoryRecord(user_id="user-123", display_name="Alex"),
    )


def test_grsai_dialogue_backend_returns_provider_reply():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://grsaiapi.com/v1/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "gpt-4o-mini"

        system_prompt = payload["messages"][0]["content"]
        assert "The Front Desk is in the Lobby near the main entrance." in system_prompt
        assert "Offer the April volunteer packet if asked." in system_prompt
        assert "Remembered user identity: Alex" in system_prompt
        assert "Do not claim autonomous base movement" in system_prompt

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "The Front Desk is in the lobby near the main entrance."
                        }
                    }
                ]
            },
        )

    engine = GRSAIDialogueEngine(
        api_key="test-key",
        base_url="https://grsaiapi.com/v1",
        text_base_url=None,
        model="gpt-4o-mini",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = engine.generate_reply("Where is the front desk?", _build_context())
    assert result.reply_text == "The Front Desk is in the lobby near the main entrance."
    assert result.intent == "wayfinding"
    assert result.engine_name == "grsai:gpt-4o-mini"


def test_grsai_dialogue_timeout_falls_back_to_rule_based():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    engine = FallbackDialogueEngine(
        primary=GRSAIDialogueEngine(
            api_key="test-key",
            base_url="https://grsai.dakka.com.cn",
            text_base_url=None,
            model="gpt-4o-mini",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(handler),
        ),
        fallback=RuleBasedDialogueEngine(),
    )

    result = engine.generate_reply("Where is the front desk?", _build_context())
    assert result.fallback_used is True
    assert "Front Desk" in result.reply_text
    assert result.engine_name == "rule_based"
    assert result.debug_notes[0] == "primary_failed:grsai_timeout"


def test_grsai_dialogue_empty_response_falls_back():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "   "}}]},
        )

    engine = FallbackDialogueEngine(
        primary=GRSAIDialogueEngine(
            api_key="test-key",
            base_url="https://grsai.dakka.com.cn",
            text_base_url=None,
            model="gpt-4o-mini",
            timeout_seconds=1.0,
            transport=httpx.MockTransport(handler),
        ),
        fallback=RuleBasedDialogueEngine(),
    )

    result = engine.generate_reply("Where is the front desk?", _build_context())
    assert result.fallback_used is True
    assert "Front Desk" in result.reply_text
    assert result.debug_notes[0] == "primary_failed:grsai_returned_empty_response"


def test_grsai_backend_without_credentials_uses_offline_fallback():
    factory = DialogueEngineFactory(
        backend="grsai",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="llama3.2:3b",
        grsai_api_key=None,
        grsai_base_url="https://grsai.dakka.com.cn",
        grsai_text_base_url=None,
        grsai_model="gpt-4o-mini",
        grsai_timeout_seconds=1.0,
    )

    result = factory.build().generate_reply("Where is the front desk?", _build_context())
    assert result.fallback_used is True
    assert result.engine_name == "rule_based"
    assert "Front Desk" in result.reply_text
    assert result.debug_notes[0] == "primary_failed:grsai_api_key_missing"


def test_ollama_dialogue_engine_retries_once_on_cold_start_timeout():
    attempts: list[float] = []
    failures: list[tuple[str, float | None, bool]] = []

    class _ColdStartEngine(OllamaDialogueEngine):
        def _perform_chat(self, *, messages: list[dict[str, str]], timeout_seconds: float):
            del messages
            attempts.append(timeout_seconds)
            if len(attempts) == 1:
                raise httpx.TimeoutException("cold start")
            return httpx.Response(200, json={"message": {"content": "warm path reply"}}), 245.0

    engine = _ColdStartEngine(
        base_url="http://127.0.0.1:11434",
        model="qwen3.5:9b",
        timeout_seconds=12.0,
        cold_start_timeout_seconds=30.0,
        warm_checker=lambda: False,
        failure_reporter=lambda reason, timeout_seconds, retry_used: failures.append((reason, timeout_seconds, retry_used)),
    )

    result = engine.generate_reply("Hello?", _build_context(with_tool=False))

    assert attempts == [12.0, 30.0]
    assert result.reply_text == "warm path reply"
    assert result.debug_notes == ["ollama_chat_retry"]
    assert failures == [("ollama_timeout", 12.0, True)]


def test_ollama_dialogue_engine_disables_thinking_for_live_turns():
    captured_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"message": {"content": "fast reply"}})

    engine = OllamaDialogueEngine(
        base_url="http://127.0.0.1:11434",
        model="qwen3.5:9b",
    )

    original_client = httpx.Client

    class _MockClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    httpx.Client = _MockClient
    try:
        result = engine.generate_reply("Say hi.", _build_context(with_tool=False))
    finally:
        httpx.Client = original_client

    assert result.reply_text == "fast reply"
    assert captured_payloads
    assert captured_payloads[0]["think"] is False


def test_dialogue_prompt_builder_uses_personal_local_identity():
    builder = DialoguePromptBuilder()

    messages = builder.build_chat_messages(
        "What can you do?",
        _build_context(with_tool=False, context_mode=CompanionContextMode.PERSONAL_LOCAL),
    )
    prompt = messages[0]["content"]
    user_message = messages[1]["content"]

    assert "local-first personal companion running on a nearby Mac" in prompt
    assert "community concierge robot" not in prompt
    assert "Default to local companion capabilities" in prompt
    assert "Do not default to venue-guide wording" in prompt
    assert user_message.startswith("User request:")
    assert "Visitor request" not in user_message


def test_dialogue_prompt_builder_keeps_personal_local_identity_with_venue_knowledge():
    builder = DialoguePromptBuilder()
    context = _build_context(with_tool=False, context_mode=CompanionContextMode.PERSONAL_LOCAL)
    context.venue_context = "- workshop_room: downstairs on the quiet side"

    messages = builder.build_chat_messages("Where is the quiet room?", context)
    prompt = messages[0]["content"]

    assert "local-first personal companion running on a nearby Mac" in prompt
    assert "operating in venue_demo" not in prompt
    assert "Keep the personal companion identity even when venue knowledge is loaded" in prompt
    assert "Default to local companion capabilities" in prompt


def test_rule_based_dialogue_uses_personal_local_capabilities_copy():
    engine = RuleBasedDialogueEngine()

    result = engine.generate_reply(
        "What can you do?",
        _build_context(with_tool=False, context_mode=CompanionContextMode.PERSONAL_LOCAL),
    )

    assert "local notes" in result.reply_text
    assert "reminders" in result.reply_text
    assert "greet visitors" not in result.reply_text


def test_rule_based_personal_local_mode_keeps_local_capabilities_with_venue_context():
    context = _build_context(with_tool=False, context_mode=CompanionContextMode.PERSONAL_LOCAL)
    context.venue_context = "- workshop_room: downstairs on the quiet side"

    result = RuleBasedDialogueEngine().generate_reply("What can you do?", context)

    assert "local notes" in result.reply_text
    assert "reminders" in result.reply_text
    assert "greet visitors" not in result.reply_text


def test_rule_based_fallback_in_personal_local_mode_avoids_venue_concierge_default():
    context = _build_context(with_tool=False)
    context.context_mode = CompanionContextMode.PERSONAL_LOCAL
    context.venue_context = None

    result = RuleBasedDialogueEngine().generate_reply("Can you help me think through today?", context)

    assert "local notes, reminders" in result.reply_text
    assert "venue questions, rooms, events" not in result.reply_text


def test_rule_based_visual_reply_avoids_stale_world_model_when_latest_snapshot_is_limited():
    captured_at = utc_now()
    context = _build_context(with_tool=False, context_mode=CompanionContextMode.PERSONAL_LOCAL)
    context.latest_perception = PerceptionSnapshotRecord(
        session_id="visual-session",
        provider_mode=PerceptionProviderMode.STUB,
        status=PerceptionSnapshotStatus.FAILED,
        limited_awareness=True,
        scene_summary="Perception is currently limited.",
        source_frame=PerceptionSourceFrame(source_kind="camera", captured_at=captured_at),
    )
    context.world_model = EmbodiedWorldModel(
        recent_visible_text=[
            WorldModelObservation(
                label="Workshop Room",
                confidence=PerceptionConfidence(score=0.95, label="high"),
                observed_at=captured_at - timedelta(seconds=10),
                expires_at=captured_at + timedelta(seconds=20),
                source_event_type="visible_text_detected",
            )
        ]
    )

    result = RuleBasedDialogueEngine().generate_reply("What sign can you see right now?", context)

    assert "visual situational awareness is limited right now" in result.reply_text.lower()
    assert "Workshop Room" not in result.reply_text
