# Engineering Review - 2026-03-30

This document records the repository checkpoint review and stabilization pass completed on 2026-03-30.

## Scope Inspected

The review focused on the code and docs that define the current product surface and future maintenance cost:

- brain HTTP entrypoints, auth, orchestrator, memory, shift runner, perception, and operator console integration
- edge HTTP entrypoints, controller, driver profiles, adapter boundaries, and command safety
- demo and ops tooling, including HTTP gateway behavior, report storage, episode export, and tethered workflows
- shared contracts and repository-level docs: `README.md`, `tutorial.md`, architecture/protocol docs, and validation workflow

## Current Assessment

The repository is in a credible checkpoint state for a pre-hardware embodied robotics platform:

- the Mac brain / Jetson edge split is preserved cleanly in the main runtime paths
- the fake-robot and tethered-demo workflows are real, deterministic, and well covered by tests
- the investor-demo surface is materially better than a prototype because it has traces, reports, safe fallback, and operator visibility

The main risks are no longer broad correctness failures. They are consolidation risks:

- oversized core modules
- file-backed local persistence assumptions
- background/runtime error visibility gaps
- operator/demo artifact robustness when local files are malformed

## Follow-up Update: Core Modularization

After the initial stabilization pass, the next consolidation iteration was completed without changing the public API or runtime artifact schemas.

Completed changes:

- shared contracts were split into `src/embodied_stack/shared/contracts/edge.py`, `brain.py`, `perception.py`, `demo.py`, and `operator.py`
- `src/embodied_stack/shared/models.py` now acts as a compatibility re-export shim so existing imports continue to work
- the shim is intentional and should stay for one stable iteration before removal is considered
- `src/embodied_stack/brain/orchestrator.py` was reduced to a thinner coordination facade
- branch-heavy runtime logic moved into `src/embodied_stack/brain/orchestration/interaction.py`, `grounding.py`, and `state_projection.py`
- direct regression coverage was added for shim imports plus key orchestrator flows: speech, telemetry, incident escalation, shift ticks, and perception-published events

This follow-up resolved the two most obvious consolidation bottlenecks called out in the original review while keeping operator behavior, trace shape, and protocol compatibility intact.

## Current Status Note

Since this review was written, the repository has also completed the desktop-first embodiment refactor:

- `src/embodied_stack/desktop/` is now the default local runtime entrypoint
- `src/embodied_stack/body/` owns semantic embodiment, normalized body state, and future transport boundaries
- shared contracts now include semantic body commands and runtime/body capability metadata
- the edge package remains in place as an optional tethered or future Jetson bridge, not the required default runtime

Treat this document as the preserved checkpoint review for the 2026-03-30 stabilization pass, not as the full current architecture description. For the current runtime shape, use [README.md](/Users/sonics/project/Blink-AI/README.md), [docs/architecture.md](/Users/sonics/project/Blink-AI/docs/architecture.md), and [docs/development_guide.md](/Users/sonics/project/Blink-AI/docs/development_guide.md).

## Bugs Found And Fixed

### 1. Corrupted local brain state could block startup

Problem:
- `MemoryStore` loaded `runtime/brain_store.json` without recovery behavior.
- A malformed or partially written file could crash the brain during initialization.

Fix:
- startup now falls back to an empty snapshot
- the invalid store is moved aside as `brain_store.json.corrupt-*`
- the recovery path is logged so the failure is visible

### 2. Late user identification left user memory inconsistent

Problem:
- if a session was created anonymously and a `user_id` was attached later, `visit_count`, `last_session_id`, and preferred response mode were not updated reliably

Fix:
- `ensure_session(...)` now synchronizes user-memory linkage when identity arrives after session creation

### 3. HTTP safe-idle degradation lost the real transport error

Problem:
- `HttpEdgeGateway.force_safe_idle(...)` returned a degraded heartbeat using the caller-supplied reason instead of the real transport failure detail
- that hid the actual networking failure during debugging

Fix:
- degraded heartbeat state now preserves the actual transport error detail

### 4. Background shift-autonomy failures were silent

Problem:
- the background autonomy loop swallowed exceptions without any signal

Fix:
- background tick failures are now logged instead of disappearing silently

### 5. Corrupted demo/report artifacts could break listings

Problem:
- malformed demo-run, shift-report, or episode files could break operator-facing artifact reads

Fix:
- invalid artifacts are now skipped or ignored with logged warnings instead of crashing list/get paths

## Validation Run During Review

These commands were run after the stabilization pass:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
PYTHONPATH=src uv run python -m embodied_stack.demo.checks
```

Result:

- `112` tests passed
- scenario dry-run passed
- demo checks passed

## Architectural Concerns Not Yet Fixed

### Large files and blurred ownership

The most obvious maintenance debt is concentration of logic:

- `src/embodied_stack/shared/contracts/brain.py`
- `src/embodied_stack/shared/contracts/demo.py`
- `src/embodied_stack/brain/venue_knowledge.py`
- `src/embodied_stack/brain/shift_supervisor.py`

`src/embodied_stack/shared/models.py` still exists, but only as a compatibility shim.
That is the right tradeoff for this checkpoint, not a new design target.

The remaining large files still work, but they increase review cost, make behavior harder to localize, and will slow future refactors.

### Local persistence remains single-process oriented

The current JSON-backed runtime is a good fit for simulation-first, single-operator work.
It is not yet designed for:

- concurrent writers
- multi-process mutation of the same store
- larger-scale history retention

That is acceptable for the current phase, but it should stay an explicit assumption.

### Perception mode semantics need eventual cleanup

The perception system is honest and usable, but `video_file_replay` is a replay workflow rather than a general-purpose live submission mode.
That distinction should remain explicit in future UI/config cleanup.

## Documentation Improvements Made

### New project-memory review

- added this review file so the checkpoint assessment is preserved in-repo

### New contributor-oriented development guide

- added `docs/development_guide.md`
- documented module boundaries, validation commands, runtime artifact paths, debugging surfaces, and current limitations

### README and tutorial updates

- linked the new engineering/development docs from the main README
- added a `make validate` workflow for the checkpoint validation path
- appended a tutorial phase entry for the stabilization checkpoint so repo history stays current

## Recommended Next Priorities

### 1. Split oversized modules by domain responsibility

Priority targets:

- keep the `shared/models.py` compatibility shim stable for one iteration, then remove it once internal imports have migrated cleanly
- split venue ingestion from venue query logic
- break `shift_supervisor.py` into policy, schedule, and transition-projection helpers if it continues to grow

### 2. Introduce explicit runtime logging policy

There is still no consistent structured logging strategy across brain, edge, demo tooling, and background threads.
The project now has more moving parts than ad hoc logging comfortably supports.

### 3. Harden persistence boundaries before multi-process growth

If the next phase expands operator tooling or adds multiple long-running workers, the file-backed store should gain:

- explicit write ownership expectations
- corruption-resistant write strategy
- clearer backup and retention policy for runtime artifacts

### 4. Keep demo surface honest while tightening semantics

Specifically:

- keep fake-robot and multimodal-replay paths clearly labeled as such
- keep readiness and operator surfaces aligned with real capability boundaries
- avoid letting demo convenience settings imply nonexistent live hardware support
