from __future__ import annotations

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.shared.models import ConversationTurn, SessionCreateRequest, UserMemoryRecord


def test_record_turn_memory_promotes_reminder_and_note(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    session = store.create_session(SessionCreateRequest(session_id="companion-memory", user_id="visitor-1"))
    user_memory = UserMemoryRecord(user_id="visitor-1", display_name="Alex")
    store.upsert_user_memory(user_memory)
    toolbox = KnowledgeToolbox(settings=settings, memory_store=store)

    session.last_user_text = "Remind me to bring the badge tomorrow."
    session.last_reply_text = "I will keep that as a local reminder."
    session.conversation_summary = "We captured a follow-up reminder."
    session.transcript.append(ConversationTurn(event_type="speech_transcript", user_text=session.last_user_text, reply_text=session.last_reply_text))
    store.upsert_session(session)
    promotions = toolbox.record_turn_memory(
        session=session,
        user_memory=user_memory,
        trace_id="trace-reminder",
        reply_text=session.last_reply_text,
        intent="general_conversation",
        source_refs=[],
    )

    session.last_user_text = "Make a note that I am rehearsing the investor demo script."
    session.last_reply_text = "Saved that as a local note."
    session.conversation_summary = "We also captured a local note."
    session.transcript.append(ConversationTurn(event_type="speech_transcript", user_text=session.last_user_text, reply_text=session.last_reply_text))
    store.upsert_session(session)
    promotions.extend(
        toolbox.record_turn_memory(
            session=session,
            user_memory=user_memory,
            trace_id="trace-note",
            reply_text=session.last_reply_text,
            intent="workspace_context_help",
            source_refs=[],
        )
    )

    reminder_items = store.list_reminders(session_id=session.session_id, user_id=user_memory.user_id).items
    note_items = store.list_companion_notes(session_id=session.session_id, user_id=user_memory.user_id).items

    assert any(item.reminder_text == "bring the badge" for item in reminder_items)
    assert any("investor demo script" in item.content for item in note_items)
    assert {item.promotion_type for item in promotions} >= {"episodic_memory", "personal_reminder", "local_note"}


def test_record_turn_memory_writes_session_digest_after_meaningful_turns(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    session = store.create_session(SessionCreateRequest(session_id="digest-session", user_id="visitor-2"))
    user_memory = UserMemoryRecord(user_id="visitor-2", display_name="Maya")
    store.upsert_user_memory(user_memory)
    toolbox = KnowledgeToolbox(settings=settings, memory_store=store)

    for index in range(8):
        session.transcript.append(
            ConversationTurn(
                event_type="speech_transcript",
                user_text=f"turn {index} question",
                reply_text=f"turn {index} answer",
            )
        )
    session.last_user_text = "What were we discussing?"
    session.last_reply_text = "We were reviewing the flow."
    session.conversation_summary = "We reviewed the flow and left one follow-up."
    store.upsert_session(session)

    promotions = toolbox.record_turn_memory(
        session=session,
        user_memory=user_memory,
        trace_id="trace-digest",
        reply_text=session.last_reply_text,
        intent="remember_and_follow_up",
        source_refs=[],
    )
    digests = store.list_session_digests(session_id=session.session_id, user_id=user_memory.user_id).items
    lookup = toolbox.lookup(
        "Give me a recap of our recent session.",
        session=session,
        user_memory=user_memory,
        world_state=store.get_world_state(),
        world_model=store.get_world_model(),
        latest_perception=None,
    )

    assert digests
    assert any(item.promotion_type == "session_digest" for item in promotions)
    assert any(item.tool_name == "recent_session_digest" for item in lookup)
