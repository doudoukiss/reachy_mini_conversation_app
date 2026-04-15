# Acceptance Matrix

## A. Repo health
- install/sync works
- tests collect cleanly
- default commands in README and Makefile still work
- no stale docs or broken links in the main workflow

Suggested commands:
- `uv sync --dev`
- `uv run pytest --collect-only -q`
- `uv run pytest -q`
- `make validate`

## B. Companion runtime
Must pass:
- terminal-first path starts reliably
- console path starts reliably
- local profile selection is clear
- no-token / no-robot path still works
- state transitions are visible and sane

Suggested suites:
- `uv run pytest tests/desktop tests/brain/test_operator_console.py tests/brain/test_agent_os_runtime.py -q`
- `uv run pytest tests/desktop/test_cli.py tests/desktop/test_runtime.py tests/desktop/test_always_on_runtime.py -q`

## C. Character presence / relationship runtime
Must pass:
- identity is consistent across turns
- relationship memory retrieval is useful, not noisy
- no obvious memory policy violations
- initiative remains bounded and rate-limited

Suggested suites:
- `uv run pytest tests/brain/test_companion_memory.py tests/brain/test_grounded_memory.py tests/brain/test_memory_policy.py tests/brain/test_memory_store.py -q`
- `uv run pytest tests/evals/test_local_companion_checks.py tests/evals/test_continuous_local_checks.py -q`

## D. Fast loop / slow loop behavior
Must pass:
- liveness is maintained during slower work
- interruption/degraded behavior is coherent
- the user can still understand what the system is doing

Suggested suites:
- `uv run pytest tests/desktop/test_streaming_local_runtime.py tests/desktop/test_always_on_logic.py tests/desktop/test_runtime_profile.py -q`

## E. Action safety
Must pass:
- unsupported actions fail honestly
- approvals are respected
- action policy dominates agent ambition
- tool failures surface clearly

Suggested suites:
- `uv run pytest tests/brain/test_agent_os_tools.py tests/brain/test_agent_os_hooks.py tests/brain/test_orchestrator_integration.py -q`
- `uv run pytest tests/evals/test_regressions.py tests/demo/test_http_gateway.py -q`

## F. Embodiment / avatar / robot projection
Must pass:
- semantic actions compile correctly
- no joint-limit / calibration regressions
- virtual path stays valid with no real hardware
- live serial tools remain gated and explicit

Suggested suites:
- `uv run pytest tests/body -q`
- `make serial-doctor BLINK_SERIAL_PORT=<your_port>`
- only after explicit confirmation: `make serial-bench ...`

## G. End-to-end demo / replay / eval
Must pass:
- scenario runner dry-run works
- smoke checks work
- demo/eval artifacts generate
- failures are diagnosable from artifacts

Suggested commands:
- `make dry-run`
- `make smoke`
- `make demo-checks`
- `uv run pytest tests/demo tests/evals -q`

## H. Human acceptance
Must pass:
- 20–30 minute real use session feels coherent
- no repeated identity drift
- initiative is not annoying
- memory corrections actually stick
- user can understand errors and stop the system easily
