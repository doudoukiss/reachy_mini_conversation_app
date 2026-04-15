Read:
- README.md
- 00_north_star_and_design_principles.md
- 01_stage0_local_appliance_reliability.md
- 07_repo_change_map_and_execution_order.md

Then inspect the current repo carefully before editing anything.

Goal:
Turn Blink-AI into a reliable zero-terminal local appliance on macOS, with the MacBook as the active embodiment host and the browser/UI as the primary interaction surface.

Project context:
- The current repo already has a desktop-first runtime, local companion CLI, operator console, local Ollama path, and semantic body layer.
- The current bottleneck is usability and reliability, not lack of architecture ideas.
- The user must be able to run Blink-AI locally without living in the terminal.
- The robot body is optional in this phase.

Build:
1. A first-class local appliance launcher command.
2. A doctor/setup flow that checks:
   - Ollama availability
   - required models
   - runtime directory
   - camera/mic/speaker availability
   - permission state when practical
   - local auth readiness
3. Explicit device discovery and selection.
4. Safer default device routing for MacBook-local use.
5. A better localhost auth experience that avoids confusing token-file behavior.
6. A clearer split between the headless service and the UI surface.
7. A browser-visible runtime status page that shows:
   - active model profile
   - camera/mic/speaker selection
   - device health
   - memory status
   - body mode
   - fallback state
8. Stable typed fallback when audio or camera is unavailable.
9. Docs and tests.

Constraints:
- Do not remove the existing CLI tools; keep them as lower-level diagnostics.
- Do not require cloud services.
- Keep local Ollama as the default preferred runtime.
- Keep the body optional and safely degradable.
- Avoid breaking existing tests unless a behavior is intentionally replaced.
- Prefer boring, maintainable code.

Definition of done:
- A user can launch Blink-AI with one command and use it locally.
- Terminal babysitting is no longer required for normal use.
- Device and auth state are visible and recoverable.
- Typed fallback always works.
- Tests pass.

Validation:
- uv run pytest
- launch the new appliance command locally
- verify the UI loads and reports device status
- verify typed fallback works when media is disabled

At the end, return:
- files changed
- new commands added
- runtime behavior changes
- any remaining manual setup required
