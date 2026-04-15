Read `AGENTS.md`, `README.md`, `PLAN.md`, `docs/current_direction.md`, `docs/architecture.md`, and all Stage 6A–6E code first.

Then implement **Stage 6F — Productize the Local Action Companion**.

## Project context

By this point Blink-AI should already have:
- action protocol
- approvals
- connector gateway
- browser runtime
- workflow runtime
- action bundles and evals

Now the system needs to feel like a real product capability rather than a hidden engineering subsystem.

## What to build

1. Add a first-class action center to the console with:
   - pending approvals
   - active workflows
   - connector health
   - recent action history
   - browser preview/artifacts
2. Extend `uv run blink-appliance` and `uv run local-companion` so Stage 6 features are discoverable and usable with minimal terminal friction.
3. Add CLI controls for:
   - list approvals
   - approve/reject
   - list workflows
   - inspect action history
   - replay recent action bundle
4. Add restart-safe recovery behavior for pending approvals and resumable workflows.
5. Add runbooks and Make targets for Stage 6 validation.
6. Update docs:
   - `README.md`
   - `PLAN.md`
   - `docs/current_direction.md`
   - `docs/architecture.md`
   - `docs/protocol.md`
   - `docs/development_guide.md`
7. Add end-to-end tests for the product path:
   - request action
   - preview appears
   - approval happens
   - action executes
   - history appears
   - evidence bundle exports

## Constraints

- Keep bodyless mode first-class.
- Keep the browser/console experience honest and legible.
- Prefer simple product surfaces over flashy complexity.
- Do not reintroduce terminal-heavy friction as the main path.

## Definition of done

- A non-technical operator can use Stage 6 safely.
- The local appliance exposes the action plane clearly.
- Recovery and transparency are strong.
- Tests pass.

## Validation

Run:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

At the end, return:
- files changed
- new console/CLI surfaces
- updated docs
- end-to-end behavior
- any release caveats
