Read docs/current_direction.md, docs/architecture.md, docs/embodiment_runtime.md, README.md, and embodiment-related skill/docs first.

Then reclassify the robot and demo layers so they support the main product instead of confusing it.

What to do:
1. Update docs so the robot is clearly presented as an optional embodiment of the companion core.
2. Update docs so `venue_demo` and concierge flows are clearly vertical/demo modes.
3. Preserve serial-head integration, semantic body actions, and bench tooling.
4. Ensure embodiment docs do not imply the body is required for Blink-AI to be valuable.
5. Update any skill files or contributor docs that still make embodiment or concierge behavior sound primary.

Constraints:
- Do not weaken the embodiment architecture.
- Do not remove demo flows.
- Keep the semantic body layer central for future hardware.

Definition of done:
- The repo tells a consistent story: companion core first, embodiment second, vertical modes third.
- The body remains a strong subsystem without hijacking the product thesis.

Validation:
- uv run pytest
- dry-run scenario runner

At the end, return:
- files changed
- embodiment invariants preserved
- any remaining docs that still need cleanup
