Read `AGENTS.md`, `README.md`, `PLAN.md`, `docs/current_direction.md`, `docs/architecture.md`, and the Stage 6A/6B/6C code first.

Then implement **Stage 6D — Workflow Runtime and Proactive Assistant**.

## Project context

Blink-AI now needs a bounded workflow system.
The project already has:
- memory
- reminders
- venue knowledge
- social runtime
- checkpoints
- approvals
- connectors
- browser runtime

What is missing is a real multi-step execution layer.

## What to build

1. Add workflow definitions and workflow-run records.
2. Add a workflow executor that supports:
   - start
   - pause
   - resume
   - retry
   - timeout
   - failure classification
3. Integrate approval pauses into workflow execution.
4. Support bounded triggers such as:
   - user request
   - due reminder
   - scheduled daily digest
   - event-start window
   - operator launch
5. Implement at least three initial workflows, for example:
   - save reminder + note from conversation
   - morning briefing
   - event lookup and open event page
6. Add proactive-assistant guardrails:
   - no surprise high-risk side effects
   - quiet-hours aware
   - context-mode aware
   - suggestion-first when uncertainty is meaningful
7. Surface workflow state in the console and CLI.
8. Keep embodied feedback optional but available through semantic body states like thinking / waiting_for_approval / safe_idle.
9. Add tests for:
   - pause/resume
   - deduplication after restart
   - approval boundaries
   - quiet-hours suppression
   - successful workflow completion

## Constraints

- No unconstrained long-running autonomous loops.
- Workflows must stay inspectable and bounded.
- Preserve the appliance and companion product paths.
- Keep the body optional.

## Definition of done

- Blink-AI can complete bounded multi-step work with pause/resume and approvals.
- Workflow state is explicit and operator-visible.
- Proactive behavior is governed, not theatrical.
- Tests pass.

## Validation

Run:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

At the end, return:
- files changed
- workflows added
- trigger model
- approval/resume behavior
- remaining limitations
