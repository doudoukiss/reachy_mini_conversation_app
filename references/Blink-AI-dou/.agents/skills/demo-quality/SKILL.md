---
name: demo-quality
description: Use when implementing demo-facing features, operator tools, or investor scenarios so the project remains polished, replayable, and honest.
---

When working on demo-facing features in this repository:

1. Optimize for:
   - the same local-first companion defined in `docs/north_star.md`, not a separate robot or operator product
   - a believable local companion experience with optional embodiment and browser/operator support, not just a passing demo script
   - replayable scenarios
   - visible command / event logs
   - visible run / checkpoint / trace state when the Agent OS is involved
   - clear success / failure states
   - graceful safe fallback
   - concise operator controls
   - credible desktop-first operation in `desktop_bodyless` or `desktop_virtual_body`
   - semantic embodiment that still reads clearly even when no physical body is connected
   - typed fallback and honest device-health reporting
   - exportable evidence that can feed later review or episode creation
   - demo lanes that match the maintained grounded-expression architecture instead of drifting into one-off motion logic

2. Avoid:
   - hidden manual steps
   - fake confidence about unimplemented capabilities
   - language that makes the robot, Action Plane, or concierge mode sound like the default identity of Blink-AI
   - presenting the optional tethered or Jetson path as if it were the required default
   - overly flashy UI that harms reliability
   - fragile one-off demo scripts
   - reviving older maintained investor surfaces after they have been retired
   - narration-timed chatty body motion when one atomic animation per cue is the proven transport shape

3. Required checks:
   - can the scenario be replayed?
   - is the active embodiment state visible when a body path is involved?
   - is the active skill or subagent visible when it matters?
   - is the selected runtime mode and body-driver mode visible?
   - are failures inspectable?
   - does the system degrade safely?
   - does the demo use the grounded catalog or a documented V3-V8 lane rather than an unsupported composite path?

4. If you add a new scenario:
   - document it in `docs/investor_demo.md`
   - add or update at least one test or scripted replay path

5. If the scenario touches the robot head:
   - read `docs/hardware_grounded_expression_architecture.md`
   - read `docs/investor_show_runbook.md`
   - use `GET /api/operator/body/expression-catalog` as the capability source of truth
   - keep structural motion conservative and derive expressivity mainly from eyes, lids, brows, and sequencing quality
