# Acceptance Gates and Release Checklist

## Global release gate

Do not call Stage 6 complete unless all of the following are true.

## Gate 1 — Protocol and policy

- action contracts are typed and documented
- approval policy is deterministic and tested
- idempotency keys prevent duplicate side effects
- blocked / preview / approval-required / executed states are all visible

## Gate 2 — Connector runtime

- connector registry exists
- at least three useful connectors are real and tested
- connector health appears in runtime status
- connector configuration and degradation are explicit

## Gate 3 — Browser runtime

- `browser_task` no longer defaults to only “unsupported” when the browser runtime is configured
- navigation and extraction work
- effectful browser steps require preview and approval where appropriate
- screenshot/text artifacts are persisted

## Gate 4 — Workflow runtime

- bounded workflows can pause and resume
- workflow restarts do not duplicate irreversible work
- proactive workflows respect quiet hours and risk policies
- failures are inspectable, not hidden

## Gate 5 — Evidence and eval

- action bundles export successfully
- replay works against stub connectors
- eval suites score approval correctness and workflow replay quality
- teacher annotations can be attached to action runs

## Gate 6 — Product surface

- console has an action center
- local companion can list and resolve approvals
- appliance mode remains the default path
- bodyless mode remains fully usable

## Gate 7 — Documentation

- `README.md` updated
- `PLAN.md` updated
- `docs/current_direction.md` updated
- `docs/architecture.md` updated
- `docs/protocol.md` updated
- `docs/development_guide.md` updated

## Recommended validation commands

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

Add new commands such as:

```bash
uv run python -m embodied_stack.action_plane.smoke --dry-run
uv run python -m embodied_stack.action_plane.replay --fixture basic_browser_open
uv run python -m embodied_stack.action_plane.workflow --fixture morning_briefing
```

## Human review checklist

- Can Blink-AI clearly explain what it is about to do?
- Can a human approve or reject with confidence?
- Can the system recover after restart?
- Are action traces intelligible to an operator?
- Does the system stay honest when the browser runtime or a connector is unavailable?
- Does the system still feel strong with no robot body attached?
