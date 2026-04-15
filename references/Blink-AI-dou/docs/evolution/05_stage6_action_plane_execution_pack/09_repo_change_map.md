# Repo Change Map

## New packages

### `src/embodied_stack/action_plane/`
Add:

- `models.py`
- `policy.py`
- `approvals.py`
- `registry.py`
- `gateway.py`
- `execution_store.py`
- `workflow.py`
- `artifacts.py`
- `replay.py`
- `health.py`

### `src/embodied_stack/action_plane/connectors/`
Add:

- `base.py`
- `reminders.py`
- `notes.py`
- `local_files.py`
- `calendar.py`
- `browser.py`
- `mcp.py`

## Shared contracts

Add or extend:

- `src/embodied_stack/shared/contracts/action.py`
- `src/embodied_stack/shared/contracts/__init__.py`

Consider limited additive extension to:
- `shared/contracts/brain.py`
- `shared/contracts/research.py`
- episode/export contracts only where necessary

## Existing modules to modify

### Agent OS
- `src/embodied_stack/brain/agent_os/tools.py`
- `src/embodied_stack/brain/agent_os/runtime.py`
- `src/embodied_stack/brain/agent_os/trace_store.py`
- `src/embodied_stack/brain/agent_os/checkpoints.py`
- `src/embodied_stack/brain/agent_os/aci.py`

### Desktop runtime
- `src/embodied_stack/desktop/runtime.py`
- `src/embodied_stack/desktop/app.py`
- `src/embodied_stack/desktop/cli.py`
- optional `src/embodied_stack/desktop/launcher.py`

### Console / browser UI
- `src/embodied_stack/brain/static/console.html`
- `src/embodied_stack/brain/static/console.js`
- `src/embodied_stack/brain/static/console.css`

### Demos / exports / research
- `src/embodied_stack/demo/episodes/service.py`
- `src/embodied_stack/demo/replay_harness.py`
- `src/embodied_stack/demo/research.py`
- new action-plane benchmark or eval modules

### Docs
- `README.md`
- `PLAN.md`
- `docs/current_direction.md`
- `docs/architecture.md`
- `docs/protocol.md`
- `docs/development_guide.md`

## Tests to add

Suggested new files:

- `tests/action_plane/test_protocol.py`
- `tests/action_plane/test_policy.py`
- `tests/action_plane/test_registry.py`
- `tests/action_plane/test_gateway.py`
- `tests/action_plane/test_browser_runtime.py`
- `tests/action_plane/test_workflow_runtime.py`
- `tests/brain/test_agent_os_action_tools.py`
- `tests/desktop/test_action_console.py`
- `tests/demo/test_action_bundle_exports.py`
- `tests/evals/test_action_plane_checks.py`

## Suggested runtime artifact directories

```text
runtime/actions/
  pending_approvals.json
  action_log.json
  connector_health.json
  browser/
  workflows/
  bundles/
```
