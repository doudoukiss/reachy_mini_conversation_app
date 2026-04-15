# Performance Asset Schema Example

This is a concrete starting point for the first show asset.

Use it as the basis for:

- `src/embodied_stack/demo/data/performance_investor_ten_minute_v1.json`

The exact final schema can change slightly during implementation, but the structure below is the intended shape.

```json
{
  "show_name": "investor_ten_minute_v1",
  "title": "Blink-AI Investor Performance",
  "version": "v1",
  "session_id": "investor-show-main",
  "defaults": {
    "response_mode": "ambassador",
    "proof_voice_mode": "stub_demo",
    "proof_speak_reply": false,
    "narration_voice_mode": "macos_say",
    "continue_on_error": true
  },
  "segments": [
    {
      "segment_id": "opening_reveal",
      "title": "Opening Reveal",
      "target_start_seconds": 0,
      "target_duration_seconds": 60,
      "investor_claim": "Blink-AI feels alive immediately and knows what it is.",
      "cues": [
        {
          "cue_id": "open_caption",
          "cue_kind": "caption",
          "label": "Opening caption",
          "text": "Blink-AI — Local-first companion. Optional embodiment."
        },
        {
          "cue_id": "open_expr",
          "cue_kind": "body_semantic_smoke",
          "label": "Friendly opening pose",
          "action": "friendly",
          "intensity": 0.58,
          "repeat_count": 1,
          "continue_on_error": true
        },
        {
          "cue_id": "open_blink",
          "cue_kind": "body_semantic_smoke",
          "label": "Opening blink",
          "action": "blink_soft",
          "intensity": 0.45,
          "repeat_count": 1,
          "continue_on_error": true
        },
        {
          "cue_id": "open_left",
          "cue_kind": "body_semantic_smoke",
          "label": "Look left",
          "action": "look_left",
          "intensity": 0.60,
          "repeat_count": 1,
          "continue_on_error": true
        },
        {
          "cue_id": "open_right",
          "cue_kind": "body_semantic_smoke",
          "label": "Look right",
          "action": "look_right",
          "intensity": 0.60,
          "repeat_count": 1,
          "continue_on_error": true
        },
        {
          "cue_id": "open_forward",
          "cue_kind": "body_semantic_smoke",
          "label": "Return forward",
          "action": "look_forward",
          "intensity": 0.55,
          "repeat_count": 1,
          "continue_on_error": true
        },
        {
          "cue_id": "open_line_1",
          "cue_kind": "narrate",
          "label": "Opening narration",
          "text": "Good morning. I'm Blink-AI.",
          "voice_mode": "macos_say",
          "continue_on_error": false
        },
        {
          "cue_id": "open_line_2",
          "cue_kind": "narrate",
          "label": "Product framing",
          "text": "What you are seeing is not a separate robot mind. It is the same local-first companion runtime living on the nearby computer, projected into this head when embodiment is useful.",
          "voice_mode": "macos_say",
          "continue_on_error": false
        }
      ]
    },
    {
      "segment_id": "grounded_perception",
      "title": "Grounded Perception",
      "target_start_seconds": 125,
      "target_duration_seconds": 75,
      "investor_claim": "Blink-AI answers from current evidence, not canned lines.",
      "cues": [
        {
          "cue_id": "perception_caption",
          "cue_kind": "caption",
          "text": "Grounded perception"
        },
        {
          "cue_id": "sign_scene",
          "cue_kind": "run_scene",
          "scene_name": "read_visible_sign_and_answer",
          "speak_reply": false,
          "voice_mode": "stub_demo",
          "expect_reply_contains": ["Workshop Room"],
          "continue_on_error": true,
          "fallback_text": "The visual grounding path is limited right now, so I am staying with the verified scene output on screen rather than improvising."
        },
        {
          "cue_id": "sign_pose",
          "cue_kind": "body_semantic_smoke",
          "action": "thinking",
          "intensity": 0.50,
          "repeat_count": 1,
          "continue_on_error": true
        },
        {
          "cue_id": "sign_line",
          "cue_kind": "narrate",
          "text": "The visible sign says Workshop Room, with the direction pointing to the right. That answer is grounded in the current scene record, not pulled from a canned script.",
          "voice_mode": "macos_say",
          "continue_on_error": false
        }
      ]
    }
  ]
}
```

## Practical rules for the final asset

1. Keep every investor-facing spoken line in the asset, not in Python.
2. Keep every proof expectation in the asset, not in test-only code.
3. Keep the chapter titles in the asset so the presentation page can render them directly.
4. Keep all body actions semantic and human-readable.
5. Keep cue ids stable because tests and artifacts will refer to them.
6. Keep fallback lines near the cues they protect.
7. Keep the asset under source control and review it like product copy, not just code.

## Final recommendation

The first implemented asset should use only the chapters already defined in the timeline doc.
Do not add extra scenes during implementation unless the team explicitly approves a longer cut.
