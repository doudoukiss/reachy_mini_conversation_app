from __future__ import annotations

VISUAL_QUERY_PHRASES = (
    "what do you see",
    "what can you see",
    "do you see",
    "can you see",
    "what do the cameras see",
    "what can the cameras see",
    "what do you see from the camera",
    "what do you see from the cameras",
    "what can you see from the camera",
    "what can you see from the cameras",
    "what's in the camera view",
    "what is in the camera view",
    "what's in the scene",
    "what is in the scene",
    "what is visible",
    "what's visible",
    "what's on the sign",
    "what is on the sign",
    "what does that say",
    "who is there",
    "is anyone there",
    "how many people",
    "what objects",
    "what do you notice",
    "what can you make out",
    "look at",
)


def looks_like_visual_query(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return False
    if any(phrase in lowered for phrase in VISUAL_QUERY_PHRASES):
        return True
    if any(term in lowered for term in ("camera", "cameras", "scene", "view", "visible", "sign", "screen")) and any(
        term in lowered for term in ("see", "show", "look", "notice", "there", "around", "front")
    ):
        return True
    return False
