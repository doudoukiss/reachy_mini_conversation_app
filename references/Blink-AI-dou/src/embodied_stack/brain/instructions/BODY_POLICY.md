# Blink-AI Body Policy

Body policy is semantic, not servo-level.

Rules:
- Only emit high-level commands such as expression, gaze, gesture, animation, display, speak, stop, and safe_idle.
- Never emit raw servo bytes or transport-specific packets from the planner.
- Prefer canonical semantic names such as `friendly`, `listen_attentively`, `look_at_user`, `look_forward`, `nod_small`, and `recover_neutral`.
- Under uncertainty, prefer `listen_attentively` or `safe_idle` behavior over expressive overreach.
- When safe-idle is active, degrade motion immediately and keep messaging explicit.
