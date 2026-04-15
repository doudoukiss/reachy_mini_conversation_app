from __future__ import annotations

from pathlib import Path

from embodied_stack.shared.models import InvestorSceneCatalogResponse, InvestorSceneDefinition, InvestorSceneStep


DATA_DIR = Path(__file__).resolve().parent / "data"

INVESTOR_SCENE_SEQUENCES: dict[str, tuple[str, ...]] = {
    "desktop_story": (
        "greeting_presence",
        "attentive_listening",
        "wayfinding_usefulness",
        "memory_followup",
        "safe_fallback_failure",
    ),
    "local_companion_story": (
        "natural_discussion",
        "observe_and_comment",
        "companion_memory_follow_up",
        "knowledge_grounded_help",
        "safe_degraded_behavior",
    ),
    "multimodal_story": (
        "approach_and_greet",
        "two_person_attention_handoff",
        "disengagement_shortening",
        "scene_grounded_comment",
        "uncertainty_admission",
        "stale_scene_suppression",
        "operator_correction_after_wrong_scene_interpretation",
    ),
}


INVESTOR_SCENES = {
    "greeting_presence": InvestorSceneDefinition(
        scene_name="greeting_presence",
        title="Greeting And Presence",
        description="Show a person detection event turning into a clear, embodied greeting.",
        session_id="investor-live-main",
        steps=[
            InvestorSceneStep(
                action_type="inject_event",
                label="Detect a nearby visitor",
                event_type="person_detected",
                payload={"confidence": 0.96},
            ),
        ],
    ),
    "attentive_listening": InvestorSceneDefinition(
        scene_name="attentive_listening",
        title="Attentive Listening",
        description="Use a brief backchannel turn so the desktop runtime visibly stays engaged without over-talking.",
        session_id="investor-live-main",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Visitor pauses and asks Blink-AI to wait",
                input_text="hold on",
            ),
        ],
    ),
    "wayfinding_usefulness": InvestorSceneDefinition(
        scene_name="wayfinding_usefulness",
        title="Wayfinding Usefulness",
        description="Ask for a destination and show concrete spoken guidance plus edge-safe commands.",
        session_id="investor-live-main",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for the workshop room",
                input_text="Where is the workshop room?",
            ),
        ],
    ),
    "venue_helpful_question": InvestorSceneDefinition(
        scene_name="venue_helpful_question",
        title="Venue Helpful Question",
        description="Ask a useful venue question and show a concrete answer plus embodied attention on the desktop runtime.",
        session_id="investor-live-main",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for the workshop room",
                input_text="Where is the workshop room?",
            ),
        ],
    ),
    "memory_followup": InvestorSceneDefinition(
        scene_name="memory_followup",
        title="Memory Follow-Up",
        description="Repeat the direction request and show that the brain remembers the last discussed location.",
        session_id="investor-live-main",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for the directions again",
                input_text="Can you repeat how to get there?",
            ),
        ],
    ),
    "operator_escalation": InvestorSceneDefinition(
        scene_name="operator_escalation",
        title="Operator Escalation",
        description="Show a human handoff request becoming an explicit escalation with visible operator state.",
        session_id="investor-escalation",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for human help",
                input_text="I need a human operator to help with a lost item.",
            ),
        ],
    ),
    "safe_fallback_failure": InvestorSceneDefinition(
        scene_name="safe_fallback_failure",
        title="Safe Fallback On Failure",
        description="Trigger degraded heartbeat and low battery so the robot visibly enters safe idle.",
        session_id="investor-fallback",
        steps=[
            InvestorSceneStep(
                action_type="inject_event",
                label="Inject degraded heartbeat",
                event_type="heartbeat",
                payload={"network_ok": False, "latency_ms": 850.0},
            ),
            InvestorSceneStep(
                action_type="inject_event",
                label="Inject low battery",
                event_type="low_battery",
                payload={"battery_pct": 11.0},
            ),
        ],
    ),
    "natural_discussion": InvestorSceneDefinition(
        scene_name="natural_discussion",
        title="Natural Discussion",
        description="Start a local companion conversation, store a name and preference, and answer with grounded venue help.",
        session_id="local-companion-live",
        user_id="local-companion-user",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Introduce the visitor and ask for a calm place",
                input_text="Hi, my name is Alex. I prefer the quiet route. Where is the quiet room?",
            ),
        ],
    ),
    "observe_and_comment": InvestorSceneDefinition(
        scene_name="observe_and_comment",
        title="Observe And Comment",
        description="Replay a camera-grounded scene and answer from fresh visible text instead of a canned line.",
        session_id="local-companion-live",
        user_id="local-companion-user",
        steps=[
            InvestorSceneStep(
                action_type="perception_fixture",
                label="Replay a sign-reading frame",
                fixture_path=str(DATA_DIR / "perception_visible_sign_image.json"),
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask what is visible",
                input_text="What sign can you see right now?",
            ),
        ],
    ),
    "companion_memory_follow_up": InvestorSceneDefinition(
        scene_name="companion_memory_follow_up",
        title="Memory Follow-Up",
        description="Ask what Blink-AI remembers about the current visitor and route preference.",
        session_id="local-companion-live",
        user_id="local-companion-user",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for remembered profile details",
                input_text="What do you remember about me?",
            ),
        ],
    ),
    "knowledge_grounded_help": InvestorSceneDefinition(
        scene_name="knowledge_grounded_help",
        title="Knowledge-Grounded Help",
        description="Ask for current venue help and answer from imported knowledge rather than a generic reply.",
        session_id="local-companion-live",
        user_id="local-companion-user",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for this week's events",
                input_text="What events are happening this week?",
            ),
        ],
    ),
    "safe_degraded_behavior": InvestorSceneDefinition(
        scene_name="safe_degraded_behavior",
        title="Safe Degraded Behavior",
        description="Keep the local companion honest when current visual grounding is unavailable.",
        session_id="local-companion-degraded",
        user_id="local-companion-user",
        steps=[
            InvestorSceneStep(
                action_type="perception_snapshot",
                label="Submit limited-awareness perception",
                perception_mode="stub",
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask a visual question with no fresh grounding",
                input_text="What sign can you see right now?",
            ),
        ],
    ),
    "approach_and_greet": InvestorSceneDefinition(
        scene_name="approach_and_greet",
        title="Approach And Greet",
        description="Replay a perception-grounded approach sequence and show deterministic embodied greeting behavior.",
        session_id="investor-multimodal",
        steps=[
            InvestorSceneStep(
                action_type="perception_fixture",
                label="Replay approach clip",
                fixture_path=str(DATA_DIR / "perception_approach_and_greet.json"),
            ),
        ],
    ),
    "read_visible_sign_and_answer": InvestorSceneDefinition(
        scene_name="read_visible_sign_and_answer",
        title="Read Visible Sign And Answer",
        description="Replay a sign-reading frame, then answer using grounded visible text instead of a scripted claim.",
        session_id="investor-multimodal",
        steps=[
            InvestorSceneStep(
                action_type="perception_fixture",
                label="Replay sign frame",
                fixture_path=str(DATA_DIR / "perception_visible_sign_image.json"),
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask what sign is visible",
                input_text="What sign can you see right now?",
            ),
        ],
    ),
    "scene_grounded_comment": InvestorSceneDefinition(
        scene_name="scene_grounded_comment",
        title="Scene Grounded Comment",
        description="Replay a noticeboard scene and answer from fresh grounded scene facts instead of a generic camera summary.",
        session_id="investor-scene-grounding",
        steps=[
            InvestorSceneStep(
                action_type="perception_fixture",
                label="Replay noticeboard frame",
                fixture_path=str(DATA_DIR / "perception_noticeboard_scan.json"),
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for a grounded scene comment",
                input_text="What do you notice in the scene right now?",
            ),
        ],
    ),
    "remember_person_context_across_turns": InvestorSceneDefinition(
        scene_name="remember_person_context_across_turns",
        title="Remember Person Context Across Turns",
        description="Store a visitor's name and recall it on a later turn in the same session.",
        session_id="investor-memory",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Introduce the visitor",
                input_text="Hi, my name is Maya.",
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for memory recall",
                input_text="Do you remember me?",
            ),
        ],
    ),
    "detect_disengagement_and_shorten_reply": InvestorSceneDefinition(
        scene_name="detect_disengagement_and_shorten_reply",
        title="Detect Disengagement And Shorten Reply",
        description="Mark engagement as dropping, then show a shorter reply chosen by explicit executive policy.",
        session_id="investor-engagement",
        steps=[
            InvestorSceneStep(
                action_type="perception_fixture",
                label="Replay disengagement clip",
                fixture_path=str(DATA_DIR / "perception_disengagement_clip.json"),
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask a broad events question",
                input_text="What events are happening this week?",
            ),
        ],
    ),
    "disengagement_shortening": InvestorSceneDefinition(
        scene_name="disengagement_shortening",
        title="Disengagement Shortening",
        description="Replay a disengaging scene and confirm the final reply gets shortened by explicit policy.",
        session_id="investor-engagement",
        steps=[
            InvestorSceneStep(
                action_type="perception_fixture",
                label="Replay disengagement clip",
                fixture_path=str(DATA_DIR / "perception_disengagement_clip.json"),
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask a broad events question",
                input_text="What events are happening this week?",
            ),
        ],
    ),
    "two_person_attention_handoff": InvestorSceneDefinition(
        scene_name="two_person_attention_handoff",
        title="Two Person Attention Handoff",
        description="Track two visitors, then hand attention to the participant who speaks most recently.",
        session_id="investor-attention-handoff",
        steps=[
            InvestorSceneStep(
                action_type="inject_event",
                label="Detect two visitors",
                event_type="people_count_changed",
                payload={
                    "people_count": 2,
                    "participant_ids": ["visitor_a", "visitor_b"],
                    "confidence": 0.94,
                },
            ),
            InvestorSceneStep(
                action_type="inject_event",
                label="Second visitor speaks",
                event_type="speech_transcript",
                payload={
                    "text": "Can you help me get to the front desk?",
                    "participant_id": "visitor_b",
                    "confidence": 0.92,
                },
            ),
        ],
    ),
    "escalate_after_confusion_or_accessibility_request": InvestorSceneDefinition(
        scene_name="escalate_after_confusion_or_accessibility_request",
        title="Escalate After Confusion Or Accessibility Request",
        description="Show clarification first, then a deterministic human escalation for accessibility-sensitive help.",
        session_id="investor-escalation-multimodal",
        steps=[
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask an ambiguous follow-up",
                input_text="Where is it",
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Request accessible help",
                input_text="I need the accessible route and a staff member to help me.",
            ),
        ],
    ),
    "uncertainty_admission": InvestorSceneDefinition(
        scene_name="uncertainty_admission",
        title="Uncertainty Admission",
        description="Use limited-awareness perception and verify the reply explicitly admits uncertainty instead of pretending to know the scene.",
        session_id="investor-uncertainty-admission",
        steps=[
            InvestorSceneStep(
                action_type="perception_snapshot",
                label="Submit stub perception state",
                perception_mode="stub",
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask what the cameras can see",
                input_text="What can you see from the cameras right now?",
            ),
        ],
    ),
    "perception_unavailable_honest_fallback": InvestorSceneDefinition(
        scene_name="perception_unavailable_honest_fallback",
        title="Perception Unavailable Honest Fallback",
        description="Keep the scene honest when perception is limited and a visual question still arrives.",
        session_id="investor-limited-awareness",
        steps=[
            InvestorSceneStep(
                action_type="perception_snapshot",
                label="Submit stub perception state",
                perception_mode="stub",
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask a visual question",
                input_text="What sign can you see?",
            ),
        ],
    ),
    "stale_scene_suppression": InvestorSceneDefinition(
        scene_name="stale_scene_suppression",
        title="Stale Scene Suppression",
        description="Inject an old semantic snapshot and verify the reply refuses to treat stale scene facts as current truth.",
        session_id="investor-stale-scene",
        steps=[
            InvestorSceneStep(
                action_type="perception_snapshot",
                label="Submit stale scene snapshot",
                payload={"captured_at_offset_seconds": -120.0},
                annotations=[
                    {
                        "observation_type": "visible_text",
                        "text_value": "Front Desk",
                        "confidence": 0.9,
                    },
                    {
                        "observation_type": "scene_summary",
                        "text_value": "A front desk sign is visible near the entrance.",
                        "confidence": 0.82,
                    },
                ],
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for a current scene answer",
                input_text="What sign can you see right now?",
            ),
        ],
    ),
    "operator_correction_after_wrong_scene_interpretation": InvestorSceneDefinition(
        scene_name="operator_correction_after_wrong_scene_interpretation",
        title="Operator Correction After Wrong Scene Interpretation",
        description="Show an operator annotation overriding an earlier scene interpretation and becoming the new grounded answer.",
        session_id="investor-operator-correction",
        steps=[
            InvestorSceneStep(
                action_type="perception_snapshot",
                label="Submit initial semantic interpretation",
                annotations=[
                    {
                        "observation_type": "visible_text",
                        "text_value": "Front Desk",
                        "confidence": 0.84,
                    },
                    {
                        "observation_type": "scene_summary",
                        "text_value": "The scene appears to show a front desk sign.",
                        "confidence": 0.8,
                    },
                ],
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask for the initial sign reading",
                input_text="What sign can you see right now?",
            ),
            InvestorSceneStep(
                action_type="perception_snapshot",
                label="Apply operator correction",
                payload={"claim_kind": "operator_annotation"},
                annotations=[
                    {
                        "observation_type": "visible_text",
                        "text_value": "Workshop Room ->",
                        "confidence": 0.98,
                        "metadata": {"justification": "operator corrected sign text"},
                    },
                    {
                        "observation_type": "scene_summary",
                        "text_value": "Operator correction: the sign points toward the workshop room.",
                        "confidence": 0.95,
                    },
                ],
            ),
            InvestorSceneStep(
                action_type="voice_turn",
                label="Ask which scene fact should be trusted",
                input_text="What sign can you see now after the correction?",
            ),
        ],
    ),
}


def list_investor_scenes() -> InvestorSceneCatalogResponse:
    return InvestorSceneCatalogResponse(items=list(INVESTOR_SCENES.values()))
