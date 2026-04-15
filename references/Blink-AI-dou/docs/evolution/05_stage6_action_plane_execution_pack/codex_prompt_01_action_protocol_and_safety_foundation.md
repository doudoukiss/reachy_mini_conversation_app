Read `AGENTS.md`, `README.md`, `PLAN.md`, `docs/current_direction.md`, `docs/architecture.md`, and `docs/protocol.md` first.

Then implement **Stage 6A — Action Protocol and Safety Foundation**.

## Project context

Blink-AI already has:
- a local appliance and local companion path
- Agent OS with typed tools, checkpoints, traces, and skills/subagents
- memory, perception, world model, and semantic embodiment
- serial head support and a research bridge

The main missing system is a safe digital action substrate.

There is already a repo signal for this gap:
- `browser_task` exists in the tool surface but currently reports unsupported
- the tool surface is stronger for read/preview than for governed effectful action

## What to build

1. Add a new shared contract surface for typed action requests, approvals, execution results, connector descriptors, and workflow-state primitives.
2. Add a new `action_plane` package with:
   - models
   - approval/policy service
   - execution/idempotency store
   - basic gateway abstraction
3. Introduce a deterministic risk model and approval policy.
4. Integrate the new action substrate into the Agent OS tool path.
5. Route at least these effectful tools through the action-plane foundation:
   - `write_memory`
   - `body_command`
   - `body_safe_idle`
6. Persist pending approvals and action executions under `runtime/actions/`.
7. Emit trace/audit records for action state transitions.
8. Add tests for:
   - schema validation
   - approval policy
   - idempotency
   - restart-safe pending approval reload
   - Agent OS integration for preview / blocked / approval-required states

## Constraints

- Do not break the existing appliance and companion paths.
- Do not move body logic out of semantic embodiment.
- Do not execute any new side effect directly from the language-model layer.
- Prefer additive integration over broad refactors.
- Keep everything body-optional and local-first.

## Definition of done

- There is now a real typed action substrate in the repo.
- Effectful tools are no longer conceptually “just normal tools”.
- Action requests can be previewed, blocked, approved, and executed in a deterministic way.
- Tests pass.

## Validation

Run:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

At the end, return:
- files changed
- new models/contracts added
- how approvals work
- what effectful tools now route through the action plane
- any remaining compatibility caveats
