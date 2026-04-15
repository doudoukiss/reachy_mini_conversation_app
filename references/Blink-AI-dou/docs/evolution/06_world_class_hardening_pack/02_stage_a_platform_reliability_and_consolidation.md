# Stage A — Platform Reliability and Consolidation

## Objective

Make Blink-AI a boringly reliable local appliance and restore a fully green engineering baseline.

This stage comes first because the current repo is big enough that architectural quality only matters if the local product surface is trustworthy.

## Step-by-step work order

### Step 1 — Restore a green validation baseline

Start here.

Tasks:

1. Run `uv run pytest -x` and fix the current first failing test.
2. Investigate the readiness contract around `/ready`.
3. Redesign readiness semantics so they distinguish between:
   - process health
   - local usability through fallback
   - full media capability
   - best-experience capability
4. Update tests so offline/degraded but usable local runtime is still represented honestly.

Target outcome:

- `uv run pytest` passes from a clean checkout
- service readiness is no longer too strict for offline/degraded but usable modes

### Step 2 — Make the local appliance the unquestioned default

Tasks:

1. Keep `uv run blink-appliance` as the canonical launch path.
2. Ensure `local-companion` and lower-level service entrypoints are explicitly secondary.
3. Remove hidden manual steps from first-run setup.
4. Make runtime mode, device mode, and model profile clearly visible in one place.
5. Ensure the browser and no-browser recovery paths are both supported and documented.

Target outcome:

- new users can launch Blink-AI without terminal babysitting
- browser-first flow is stable, but not the only recovery path

### Step 3 — Fix device and media routing discipline

Tasks:

1. Make device selection explicit and inspectable:
   - camera source
   - microphone source
   - speaker output mode
2. Add a stable policy for default device selection when monitors expose media devices.
3. Improve macOS permission diagnostics.
4. Distinguish:
   - permission denied
   - device missing
   - device busy
   - supported fallback active
5. Keep typed fallback working even when all live media is unavailable.

Target outcome:

- no ambiguity about why camera/mic/speaker are or are not active
- external-monitor media devices cannot silently hijack the experience

### Step 4 — Harden persistence and runtime artifact writes

Tasks:

1. Introduce atomic writes for all important runtime artifacts.
2. Add corruption recovery for stores and report files consistently.
3. Add explicit backup/rotation rules for:
   - brain store
   - episodes
   - replays
   - run/checkpoint artifacts
   - incident tickets
4. Document single-writer assumptions.
5. Add tests for malformed JSON/artifact recovery.

Target outcome:

- runtime artifacts do not become a silent source of instability

### Step 5 — Add structured logging and event correlation

Tasks:

1. Create a small, boring structured logging policy.
2. Add correlation IDs across:
   - session
   - run
   - checkpoint
   - perception event
   - tool call
   - voice turn
   - body command batch
3. Make background failures visible.
4. Keep logs readable locally.

Target outcome:

- a user or operator can understand what happened without guesswork

### Step 6 — Consolidate oversized modules

Start with the highest-value splits:

- `desktop/devices.py`
- `brain/operator_console.py`
- `brain/perception.py`
- `demo/episodes.py`
- `brain/agent_os/tools.py`
- `brain/tools.py`

Do not perform aesthetic refactors only.
Each split must improve ownership and testability.

## Suggested file targets

- `src/embodied_stack/desktop/`
  - `device_catalog.py`
  - `device_selection.py`
  - `camera_runtime.py`
  - `audio_runtime.py`
  - `device_health.py`
- `src/embodied_stack/brain/operator/`
  - `appliance.py`
  - `console_snapshot.py`
  - `incidents.py`
  - `runs.py`
  - `memory_review.py`
- `src/embodied_stack/persistence/` or equivalent internal package
  - atomic writes
  - corruption helpers
  - backup strategy
- `src/embodied_stack/observability/`
  - structured log helpers
  - correlation context

## Definition of done

- full pytest suite passes
- readiness semantics are clearer and honest
- local appliance launch is simpler and more reliable
- device/media routing is explicit
- artifact writes are corruption-resistant
- logging and error visibility are materially better
- major oversized files are reduced without breaking public behavior

## Validation

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
uv run blink-appliance --doctor
```
