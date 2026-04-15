# Blink-AI Expressive Behavior System v1

## Recommendation

The overall product should still prioritize a solid safe action substrate for browser/computer-use and workflow actions. That is the larger remaining architectural gap.

However, the **embodiment subsystem itself is already mature enough for a bounded expansion of movements and expressions**. The current body stack already has: semantic action names, a compiler, profile-based joint limits, virtual preview, calibration, live-motion gating, tuning overrides, and body-side tests. So the right move is **not** to invent arbitrary new behaviors. It is to extend the semantic body library in a disciplined way.

## Design rules

1. **No mouth-first emotions.** This robot does not have a mouth, cheeks, or shoulders. So emotions must be expressed mainly through head yaw/pitch/roll, gaze, lids, and brows.
2. **Youthful means light, quick, and contemporary — not childish.** Prefer bright attention shifts, soft asymmetry, and short social beats over exaggerated cartoon movement.
3. **Every new action must belong to a family.**
   - Expressions = held states
   - Gestures = short transient beats
   - Animations = multi-beat sequences
4. **Every new action must recover cleanly.** Multi-beat actions should settle back into `friendly` or `listen_attentively`, not leave the head stranded in a strained pose.
5. **Keep the system internally legible.** `friendly`, `curious_bright`, and `playful` should feel related; `focused_soft` should feel like a lighter sibling of `thinking`; `bashful` should use down-and-away gaze rather than impossible smile semantics.

## New expressions

### `curious_bright`
Use for novelty, discovery, and positive attention. Brighter eyes and a mild brow lift.

### `focused_soft`
Use for concentration without looking severe. Slight lid narrowing and a stable centered pose.

### `playful`
Use sparingly in warm, low-stakes rapport moments. Small tilt, mild asymmetry, lively gaze.

### `bashful`
Use for gentle self-effacing moments, soft thanks, or shy acknowledgement. Down-and-away gaze with softened lids.

## New gestures

### `double_blink`
A crisp two-beat blink. Contemporary, lightweight acknowledgement.

### `acknowledge_light`
A minimal nod with a tiny brow lift. A quieter sibling of `nod_small`.

### `playful_peek_left` / `playful_peek_right`
A quick sideways peek with head-eye coupling and a tiny brow accent. Use only in relaxed social contexts.

## New animations

### `youthful_greeting`
Friendly → curious_bright → double blink → listen_attentively.

### `soft_reengage`
A short down glance → focused_soft → double blink → listen_attentively.

### `playful_react`
Playful pose → side peek → recover to friendly.

## Rollout guidance

- Expressions and gestures are safe for semantic smoke and teacher review.
- Multi-beat animations remain bench-first and should be used after review.
- Do not switch default orchestration policies to these actions automatically yet. First collect teacher review and runtime evidence.
