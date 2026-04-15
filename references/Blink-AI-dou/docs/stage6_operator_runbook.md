# Stage 6 Operator Runbook

This runbook is the maintained operator workflow for the Stage 6 Action Plane, browser runtime, workflows, bundles, replays, and restart-review handling.

Use this alongside:

- [README.md](/Users/sonics/project/Blink-AI/README.md)
- [development_guide.md](/Users/sonics/project/Blink-AI/docs/development_guide.md)
- [protocol.md](/Users/sonics/project/Blink-AI/docs/protocol.md)

## Purpose

Stage 6 is now productized as one operator surface.

For daily companion use, start with `uv run local-companion`. This runbook is specifically for the optional operator layer that sits around that terminal-first runtime.

Within Stage 6 operator work:

- `/console` is the primary Action Center
- `blink-appliance` exposes Stage 6 readiness during setup and runtime
- `local-companion` provides `/actions ...` fallback and power-user controls

The Action Center is the place to resolve:

- pending approvals
- paused or blocked workflows
- restart-review items
- recent action failures
- bundle inspection and replay follow-up

## Starting the Operator Surface

Preferred browser-first operator path:

```bash
uv run blink-appliance
```

Terminal-first companion path with optional operator follow-up:

```bash
uv run local-companion
```

After appliance login, go to `/console`. If there are pending approvals or restart-review items, the Action Center should already be highlighted with the next recommended step.

## Action Center Workflow

The Action Center is driven by:

```text
GET /api/operator/action-plane/overview
```

Use it in this order:

1. Check the summary chips.
2. Open the first attention item.
3. Read the inspector summary and `next_step_hint`.
4. Review browser preview, artifacts, and linked bundle or workflow state.
5. Approve, reject, resume, retry, or replay explicitly.

The main Action Center areas are:

- summary chips for pending approvals, waiting workflows, degraded connectors, restart-review items, and recent replay state
- one merged attention queue for approvals, workflow pauses, restart-review items, and recent failures
- one shared inspector for whichever item is selected
- browser preview artifacts, including screenshot and candidate targets when available
- recent history, recent bundles, and recent replays

## Approval Handling

When an action is pending approval:

1. Select it in the Action Center.
2. Read the `operator_summary`.
3. Confirm the target, artifacts, and any browser preview.
4. Either approve or reject it.

Console/API path:

- `GET /api/operator/action-plane/approvals`
- `POST /api/operator/action-plane/approvals/{action_id}/approve`
- `POST /api/operator/action-plane/approvals/{action_id}/reject`

CLI path:

```bash
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli approval-list
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli approval-approve <action_id> --operator-note "approved"
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli approval-reject <action_id> --operator-note "rejected"
```

Interactive `local-companion` path:

```text
/actions approvals
/actions approve <action_id> [note]
/actions reject <action_id> [note]
```

Rules:

- never assume preview-only means executed
- never approve blindly when browser preview or target resolution is unclear
- rejected actions stay blocked until an explicit retry or rerun path is used

## Workflow Resume And Retry

Workflows are code-defined and reentrant. They may pause because of:

- pending approval
- operator pause
- failed step
- quiet-hours suppression
- suggestion-only policy
- restart review

Operator/API path:

- `GET /api/operator/action-plane/workflows`
- `GET /api/operator/action-plane/workflows/runs`
- `GET /api/operator/action-plane/workflows/runs/{run_id}`
- `POST /api/operator/action-plane/workflows/runs/{run_id}/resume`
- `POST /api/operator/action-plane/workflows/runs/{run_id}/retry`
- `POST /api/operator/action-plane/workflows/runs/{run_id}/pause`

CLI path:

```bash
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-list
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-runs --session-id <session_id>
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-resume <workflow_run_id>
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-retry <workflow_run_id>
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-pause <workflow_run_id>
```

Interactive `local-companion` inspection path:

```text
/actions workflows
```

Resume vs retry:

- use `resume` when the run is paused behind approval or restart-review and should continue from the next incomplete step
- use `retry` when the current step failed or was rejected and should be attempted again explicitly

## Browser Degraded Mode

Browser runtime absence is degraded-but-usable, not blocking.

If the browser backend is unavailable:

- the appliance status should show degraded browser state
- the Action Center should still work for non-browser connectors
- browser-dependent actions should reject or degrade honestly
- do not treat missing Playwright support as a general Action Plane failure

Useful browser checks:

- `GET /api/operator/action-plane/browser/status`
- `POST /api/operator/action-plane/browser/task`

Smoke path:

```bash
make browser-runtime-smoke
```

## Restart-Review Handling

Restart reconciliation is conservative by design.

On boot:

- pending approvals reload as-is
- resumable workflows reload from persisted state
- any nonterminal action left in execution becomes `uncertain_review_required`
- dependent workflows pause with `runtime_restart_review`

Operator rules:

- never assume an effectful side effect succeeded after restart
- never auto-approve or auto-replay from restart state
- inspect the linked action, bundle, and workflow before resuming or retrying

What to do:

1. Open the restart-review item in the Action Center.
2. Read the `operator_summary` and `next_step_hint`.
3. Inspect linked artifacts and bundle history.
4. Decide whether to resume, retry, or leave blocked for later review.

## Bundle Inspection And Replay

Every top-level action or workflow now produces a durable `blink_action_bundle/v1` sidecar under:

```text
runtime/actions/exports/action_bundles/<bundle_id>/
```

Deterministic replays write under:

```text
runtime/actions/exports/action_replays/<replay_id>/
```

Operator/API path:

- `GET /api/operator/action-plane/bundles`
- `GET /api/operator/action-plane/bundles/{bundle_id}`
- `POST /api/operator/action-plane/bundles/{bundle_id}/teacher-review`
- `POST /api/operator/action-plane/replays`

CLI path:

```bash
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli action-bundle-list --limit 20
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli action-bundle-show <bundle_id>
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli action-bundle-teacher-review <bundle_id> --summary "good"
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli replay-action-bundle <bundle_id> --operator-note "deterministic replay"
```

Interactive `local-companion` inspection path:

```text
/actions history [limit]
/actions bundle <bundle_id>
```

Replay rules:

- use replay for deterministic inspection, not as a live side-effect shortcut
- replay always runs against stub or dry-run backends
- replay does not silently inherit old approvals

## Local Companion Quick Reference

The interactive loop now supports:

```text
/actions status
/actions approvals
/actions approve <action_id> [note]
/actions reject <action_id> [note]
/actions history [limit]
/actions connectors
/actions workflows
/actions bundle <bundle_id>
```

Use `/actions status` first when the browser console is unavailable.

## Validation Entry Points

Use these before demoing or after meaningful Stage 6 changes:

```bash
make action-plane-validate
make browser-runtime-smoke
make workflow-replay-smoke
make action-export-inspect
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

## Stop/Go Guidance

Proceed when:

- Action Center shows no unresolved surprise actions
- browser degradation is understood and acceptable for the current task
- restart-review items have been explicitly resolved or intentionally deferred
- the next operator step is clear in appliance status or Action Center guidance

Stop and investigate when:

- an effectful action appears to have executed without an approval boundary
- a restart-review item disappears without operator action
- a workflow resumes past an uncertain side effect automatically
- browser artifacts or bundle traces are missing for an action that should have produced them
