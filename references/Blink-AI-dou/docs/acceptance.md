# Acceptance

This is the maintained acceptance harness for the current Blink-AI milestone.

Use this document when you need to answer a practical question:

- did I break the repo?
- did I break the terminal-first companion path?
- is the current Mac demoable?
- is this change strong enough for a release-candidate pass?

`make validate` is still the basic checkpoint gate. The acceptance harness sits above it and turns the repo's existing pytest, certification, burn-in, and eval entrypoints into a repeatable staged workflow.

## Acceptance Lanes

### Quick acceptance

Use for day-to-day milestone validation:

```bash
make acceptance-quick
```

This runs:

- `pytest --collect-only`
- focused repo-health, desktop/runtime, Agent OS, memory/relationship, action-plane, and embodiment pytest slices
- `local-companion-checks`
- `always-on-local-checks`
- `continuous-local-checks`
- the scenario dry-run

It is the fastest lane that still touches the current companion milestone in a meaningful way.

### Full acceptance

Use for authoritative automated milestone validation on the no-robot path:

```bash
make acceptance-full
```

This runs:

- the full pytest suite
- the scenario dry-run
- `local-companion-certify`
- `local-companion-burn-in`
- `demo-checks`

Important:

- `local-companion-certify` may report `degraded_but_acceptable` on a machine that is still useful but not fully proven. The full lane records that as degraded, not silently green.
- hardware is still out of scope for this lane by design.

### Release-candidate acceptance

Use before calling the current milestone release-candidate ready:

```bash
make acceptance-rc
```

This runs:

- everything in the full lane
- `smoke-runner`
- `multimodal-demo-checks`

Unlike the full lane, release-candidate acceptance requires the no-robot certification verdict to be `certified`, not merely degraded-but-acceptable.

### Manual local-Mac acceptance

Use for the human acceptance pass on the target Mac:

```bash
make acceptance-manual-local
```

This does not fake automation. It prints and records the terminal-first human acceptance sequence for:

- startup and mode clarity
- terminal-first conversation
- console interaction
- memory continuity
- initiative behavior
- action approval behavior
- degraded mode clarity
- shutdown and reset

Use [human_acceptance.md](/Users/sonics/project/Blink-AI/docs/human_acceptance.md) as the authoritative 20 to 30 minute checklist and scripted walkthrough.

### Optional hardware acceptance

Use only when the serial head is part of the current proof:

```bash
make acceptance-hardware
```

This lane is intentionally separate from the default companion acceptance path.

It runs live-serial pytest markers only when the required environment is present:

- `BLINK_SERIAL_PORT`
- `BLINK_HEAD_CALIBRATION` for motion smoke

If those prerequisites are absent, the lane reports honest skips instead of pretending hardware validation happened.

### Investor-show acceptance lanes

Use these when you are changing the deterministic investor-show lane rather than the general companion milestone:

```bash
make acceptance-investor-show-quick
make acceptance-investor-show-full
make acceptance-investor-show-hardware
```

`acceptance-investor-show-quick` covers:

- investor-show pytest slice
- `investor_expressive_motion_v8` `performance-dry-run`
- a representative English narration benchmark smoke on the real selected voice
- a proof-only bodyless run

`acceptance-investor-show-full` adds:

- a representative Chinese narration benchmark smoke on the real selected voice
- a full bodyless run with `stub_demo` narration for automation speed
- a full virtual-body run with `stub_demo` narration for automation speed
- a forced degraded rehearsal for the grounded-perception chapter

`acceptance-investor-show-hardware` stays separate and only covers the live-serial prerequisites for the robot head.

Use [investor_show_runbook.md](/Users/sonics/project/Blink-AI/docs/investor_show_runbook.md) after the automated lane is green. That runbook is the maintained source for cue-smoke, degraded rehearsal, dress rehearsal, projector operation, and post-show reset.

## Test Surface Inventory

The current automated test surface is inventoried into these acceptance categories:

- `repo health`
  - `tests/shared/`
  - `tests/backends/test_router.py`
  - `tests/test_config.py`
  - `tests/test_persistence.py`
  - `tests/test_makefile_serial_targets.py`
  - `tests/test_makefile_acceptance_targets.py`
- `desktop/runtime`
  - `tests/desktop/`
  - `tests/edge/test_edge_runtime.py`
- `Agent OS`
  - `tests/brain/test_agent_os_*`
  - `tests/brain/test_auth.py`
  - `tests/brain/test_brain_api.py`
  - `tests/brain/test_operator_console.py`
  - `tests/brain/test_orchestrator_integration.py`
  - `tests/brain/test_participant_routing.py`
- `memory/relationship`
  - the remaining `tests/brain/` coverage for memory, presence, initiative, perception, world model, and bounded continuity
- `action plane`
  - `tests/action_plane/`
  - `tests/demo/test_action_flywheel.py`
- `embodiment/serial`
  - `tests/body/`
- `demos/evals`
  - `tests/demo/`
  - `tests/evals/`

Some files are intentionally cross-cutting. The acceptance harness assigns each file to one primary category so the inventory stays readable.

## Artifacts

Every acceptance lane writes machine-readable and human-readable artifacts under:

```text
runtime/diagnostics/acceptance/<run_id>/
```

Key files:

- `acceptance.json`
- `acceptance.md`
- `commands/*.stdout.log`
- `commands/*.stderr.log`

If you only need the current inventory without running commands:

```bash
make acceptance-inventory
```

## Contributor Rule

Use this order:

1. `make validate` while iterating
2. `make acceptance-quick` before considering a change stable
3. `make acceptance-full` before merging milestone-sensitive work
4. `make acceptance-rc` before calling the milestone release-candidate ready
5. `make acceptance-manual-local` and `make acceptance-hardware` only when the target proof actually requires those lanes
6. `make acceptance-investor-show-quick` and `make acceptance-investor-show-full` when you changed the deterministic investor-show lane
