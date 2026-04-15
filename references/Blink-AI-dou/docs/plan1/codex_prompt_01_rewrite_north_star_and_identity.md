Read AGENTS.md, PLAN.md, README.md, docs/current_direction.md, docs/architecture.md, docs/development_guide.md, src/embodied_stack/brain/instructions/IDENTITY.md, and src/embodied_stack/brain/llm.py first.

Then recenter Blink-AI around a single product thesis:

Blink-AI is a terminal-first, local-first personal companion operating system with optional embodiment.

What to do:
1. Rewrite top-level docs so they consistently present Blink-AI as a personal companion first.
2. Keep community concierge / venue demo as an explicit vertical mode, not the hidden default identity.
3. Rewrite identity prompts and system-message language that still describe Blink-AI as a community concierge robot.
4. Preserve the existing `venue_demo` context mode and concierge skills, but make them clearly mode-specific.
5. Add a new doc `docs/product_direction.md` that explains:
   - primary product
   - primary surface
   - embodiment role
   - action-plane role
   - venue-demo role
6. Update any contributor-facing docs that conflict with this product thesis.

Constraints:
- Do not break current runtime behavior.
- Do not remove the demo or concierge flows.
- Do not remove embodiment.
- Prefer additive, high-signal wording changes over sweeping rewrites.

Definition of done:
- A new contributor can read the docs and understand Blink-AI as a personal companion first.
- Concierge behavior is still supported but clearly scoped.
- Identity prompts and repo docs no longer conflict.

Validation:
- uv run pytest
- PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
- grep results for concierge-first wording are reduced to mode-specific files only

At the end, return:
- files changed
- remaining concierge-specific files by design
- any wording that still needs follow-up
