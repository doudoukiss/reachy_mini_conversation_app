# World-Class Deterministic Investor Show

This folder defines a **side-track performance mode** for investor demos that stays aligned with Blink-AI's current product direction:

- the **local-first companion** remains the main product
- the **robot head remains optional embodiment**
- the show must be **honest, deterministic, replayable, and safe**
- the show must rely on **existing repo capabilities first**, with only thin orchestration added around them

This is **not** a product pivot toward a robot-first identity. It is a contained, high-confidence demo layer built on top of the same companion core so the team can keep the main development track intact.

## What this bundle contains

Read the files in this order:

1. [01_show_brief_and_success_criteria.md](./01_show_brief_and_success_criteria.md)
   - the demo thesis, investor psychology, guardrails, and world-class bar
2. [02_ten_minute_timeline_and_stage_directions.md](./02_ten_minute_timeline_and_stage_directions.md)
   - the exact ten-minute performance structure, cues, and runtime proof beats
3. [03_full_script_text.md](./03_full_script_text.md)
   - the clean script text for robot voice, off-stage prompts, and captions
4. [04_codex_implementation_sequence.md](./04_codex_implementation_sequence.md)
   - the engineering plan Codex should follow, in execution order
5. [05_motion_and_servo_safety.md](./05_motion_and_servo_safety.md)
   - live-safe motion palette, tuning rules, and validation order
6. [06_demo_day_runbook.md](./06_demo_day_runbook.md)
   - setup, launch, recovery, and operator workflow
7. [07_tests_and_acceptance_gates.md](./07_tests_and_acceptance_gates.md)
   - automated tests, rehearsal gates, and stop/go criteria

## Deliverable this plan is aiming at

A new deterministic show mode, tentatively named:

- `investor_ten_minute_v1`

With these characteristics:

- runs on the same desktop runtime and serial-head path already in the repo
- uses **prewritten narration** for reliability
- uses **real proof cues** under the hood:
  - investor scenes
  - perception fixtures
  - memory updates
  - venue knowledge
  - operator escalation
  - safe idle
  - exportable evidence
- uses **semantic body actions**, not raw servo choreography
- works in a **network-degraded** environment
- leaves behind an artifact bundle that proves what actually happened

## Design stance

The key move is to split the show into two layers:

### 1. Narration layer
A deterministic sequence of prewritten lines, played locally through the existing voice path or pre-rendered local audio.

### 2. Proof layer
The same runtime quietly performs real actions underneath:
- scene runs
- world-model transitions
- memory updates
- incident creation
- safe-idle transitions
- artifact export

The audience hears the polished scripted story, while the system still produces real traces and visible state. This creates a demo that is both **cinematic** and **honest**.

## Non-negotiable constraints for Codex

Codex should preserve these:

- **Do not change the product thesis.**
  - Blink-AI remains a local-first companion with optional embodiment.
- **Do not hard-code raw servo motion into the brain.**
  - Use the existing semantic body surface.
- **Do not rely on bench-only live actions by default.**
  - Prefer smoke-safe semantic actions for the live robot.
- **Do not require network connectivity for the ten-minute show.**
  - The performance must run in an offline-safe or local-safe mode.
- **Do not let generated model wording drive the investor-facing audio.**
  - The investor-facing narration must stay prewritten.
- **Do not make claims the runtime cannot back up.**
  - Every spoken claim must correspond to a visible artifact, deterministic fixture, or validated state change.
