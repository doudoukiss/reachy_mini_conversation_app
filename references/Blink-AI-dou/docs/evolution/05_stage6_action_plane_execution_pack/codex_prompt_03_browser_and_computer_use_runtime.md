Read `AGENTS.md`, `README.md`, `PLAN.md`, `docs/current_direction.md`, `docs/architecture.md`, and the Stage 6A/6B code first.

Then implement **Stage 6C — Browser and Computer-Use Runtime**.

## Project context

The repository already exposes `browser_task` as a tool concept, but it still reports unsupported.
That placeholder now needs to become a real bounded browser capability.

The browser runtime should make Blink-AI more useful as a local assistant now, and later provide the same kind of safe action substrate that future embodied workflows can reuse.

## What to build

1. Implement a browser runtime behind a connector/action interface.
2. Start with a read-first capability set:
   - open URL
   - capture page title
   - extract visible text
   - capture screenshot artifact
   - summarize page state
3. Add bounded action capabilities:
   - identify candidate click targets
   - click a target
   - type into a target field
   - submit a form
4. Require preview and approval for effectful browser actions where appropriate.
5. Persist browser artifacts under `runtime/actions/browser/`.
6. Surface browser state in the console:
   - current page
   - last screenshot
   - pending action preview
   - recent action results
7. Replace the current honest unsupported placeholder path with a real supported path when configured, while preserving honest degradation when unavailable.
8. Add deterministic stub/fixture browser support for CI tests.
9. Add tests for:
   - read-only snapshot mode
   - preview generation
   - approval gating
   - artifact persistence
   - honest unsupported fallback

## Constraints

- Do not begin with arbitrary system-wide computer control.
- Browser work must stay inspectable and bounded.
- Avoid hidden automation.
- Preserve body-optional operation.
- Keep the runtime useful even when the browser runtime is unavailable.

## Definition of done

- `browser_task` is now real when configured.
- The browser runtime is bounded, inspectable, and safe.
- Artifacts and approvals are visible.
- Tests pass.

## Validation

Run:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

At the end, return:
- files changed
- supported browser actions
- approval policy
- artifact locations
- how unsupported/degraded behavior works
