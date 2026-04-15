# Codex Implementation Sequence

This file is the main engineering plan. Codex should follow the steps in order and avoid broad refactors.

## Implementation principle

Build the smallest possible orchestration layer around what already exists.

The target is **not** a new product subsystem.  
The target is a **deterministic show mode** built on top of:

- existing investor scenes
- existing operator service calls
- existing serial-head semantic actions
- existing session and export plumbing
- existing presence / console surfaces

## Deliverables

Codex should produce:

1. a data-driven show definition
2. a runner that executes the show deterministically
3. a clean presentation surface
4. a safe live-motion profile for the show
5. a CLI / API entrypoint
6. artifact export and run summary
7. tests that keep the show from drifting

---

## Pass A — Must-have deterministic runner

### Step A1 — Add a performance-show data model

**Goal:** represent the investor show as data, not hard-coded imperative logic.

**Recommended files to touch**
- `src/embodied_stack/shared/contracts/operator.py`
- `src/embodied_stack/shared/__init__.py` or re-export path if needed
- `src/embodied_stack/shared/models.py`

**Add models for**
- `PerformanceCue`
- `PerformanceSegment`
- `PerformanceShowDefinition`
- `PerformanceShowCatalogResponse`
- `PerformanceRunRequest`
- `PerformanceCueResult`
- `PerformanceRunResult`

**Recommended cue kinds**
- `narrate`
- `caption`
- `run_scene`
- `submit_text_turn`
- `inject_event`
- `perception_fixture`
- `perception_snapshot`
- `body_semantic_smoke`
- `body_write_neutral`
- `body_safe_idle`
- `pause`
- `export_session_episode`

**Important fields**
- `cue_id`
- `cue_kind`
- `label`
- `text`
- `scene_name`
- `action`
- `intensity`
- `repeat_count`
- `note`
- `expect_reply_contains`
- `fallback_text`
- `continue_on_error`
- `target_duration_ms`
- `session_id`
- `response_mode`
- `voice_mode`
- `speak_reply`

**Acceptance**
- the models serialize cleanly
- they can describe the full ten-minute show without code changes

---

### Step A2 — Add the show asset file

**Goal:** keep the show authored in a single human-editable asset.

**Recommended file**
- `src/embodied_stack/demo/data/performance_investor_ten_minute_v1.json`

**Why JSON**
- the repo already packages `demo/data/*.json`
- no extra package-data changes are required

**Asset should include**
- show metadata
- default session id
- chapter list
- cue list
- expected proof assertions
- fallback lines
- caption copy
- timing targets

**Important**
- use `speak_reply=false` for all proof scenes
- narration should be separate `narrate` cues
- proof scenes should run silently underneath

**Acceptance**
- the asset loads with no code-side special casing
- changing a line of narration does not require touching Python logic

---

### Step A3 — Build the performance-show runner

**Goal:** execute the show as a deterministic sequence.

**Recommended new module**
- `src/embodied_stack/demo/performance_show.py`

**Runner responsibilities**
- load the show asset
- resolve defaults
- execute cues in order
- collect cue results
- capture proof outputs
- assert expected substrings for proof steps
- keep moving on non-fatal degradation
- write a local run summary

**The runner should call existing surfaces where possible**
- `OperatorService.run_investor_scene(...)`
- `OperatorService.submit_text_turn(...)`
- `OperatorService.inject_event(...)`
- `OperatorService.submit_perception_snapshot(...)`
- `OperatorService.run_body_semantic_smoke(...)`
- `OperatorService.write_body_neutral(...)`
- `OperatorService.export_session_episode(...)`

**Design requirement**
Narration must be independent from proof execution.

That means:
- proof scenes run silently
- the robot's audible lines come from the show asset
- the performance runner speaks only the prewritten narration text

**Acceptance**
- a dry run can enumerate all cues
- a stub run can execute in bodyless / virtual mode
- a serial-body run can execute the same show with live-safe body cues

---

### Step A4 — Add narration execution

**Goal:** play prewritten lines reliably using the existing local voice path.

**First-version requirement**
Support at least:
- `macos_say`
- `stub_demo`

**Recommended implementation**
Reuse the existing local device speech path instead of inventing new audio plumbing.

**Optional polish**
Allow an `audio_asset_path` field later, but do not block V1 on pre-rendered audio.

**Important**
- narration should not depend on generated model text
- narration should remain readable as plain text for captions and tests

**Acceptance**
- a narration-only dry run works
- a live local run speaks the exact scripted lines in order

---

## Pass B — Operator and presentation surface

### Step B1 — Add operator-service methods

**Recommended files**
- `src/embodied_stack/brain/operator/service.py`
- `src/embodied_stack/brain/app.py`

**Add methods**
- `list_performance_shows()`
- `run_performance_show(show_name, request)`
- `get_performance_run(run_id)` or `get_performance_status(show_name, session_id)`

**API endpoints**
- `GET /api/operator/performance-shows`
- `POST /api/operator/performance-shows/{show_name}/run`
- `GET /api/operator/performance-shows/runs/{run_id}` or equivalent status endpoint

**Important**
The first implementation may be synchronous if that keeps the code simple and correct.
If Codex adds async/background execution, keep it explicit and observable.

**Acceptance**
- the show can be started from HTTP
- the run summary is retrievable after completion

---

### Step B2 — Add a clean performance presentation page

**Recommended files**
- `src/embodied_stack/brain/static/performance.html`
- `src/embodied_stack/brain/static/performance.js`
- optional minor additions to `console.css`

**Purpose of this page**
- display the current chapter
- show the current scripted line as caption
- mirror the presence shell
- show one or two proof cards only
- avoid raw operator clutter

**Suggested layout**
- left: chapter title + claim
- center: presence shell / hero state
- right: proof cards
- bottom: current narration caption

**Polling sources**
- presence state from existing presence endpoint
- performance run status from the new performance status endpoint

**Acceptance**
- page reads well from across a room
- page keeps working even when the robot is preview-only
- page never depends on a hidden manual refresh

---

### Step B3 — Add CLI entrypoints

**Recommended files**
- `src/embodied_stack/desktop/cli.py`
- `pyproject.toml`
- optional `Makefile`

**Add CLI**
- `performance-show`
- `performance-catalog`
- `performance-dry-run`

**Suggested command shape**
- `uv run local-companion performance-show investor_ten_minute_v1`
- or a dedicated console script like `investor-performance-show`

**Optional Make targets**
- `make investor-show`
- `make investor-show-dry`

**Acceptance**
- operator can start the show from terminal without browsing the console first
- dry-run prints chapter and cue order cleanly

---

## Pass C — Motion polish without product drift

### Step C1 — Make semantic tuning path configurable

**Problem today**
The body driver loads a default semantic tuning path directly.

**Recommended files**
- `src/embodied_stack/config.py`
- `src/embodied_stack/body/driver.py`

**Add setting**
- `blink_body_semantic_tuning_path: str | None = None`

**Behavior**
- if configured, use the configured path
- otherwise fall back to the existing default

**Why**
This lets the show use a demo-specific tuning file without mutating the everyday default tuning path.

**Acceptance**
- normal runtime behavior is unchanged when the setting is absent
- the investor show can opt into a safe, slightly more expressive tuning profile

---

### Step C2 — Add the investor-show tuning file

**Recommended runtime artifact**
- `runtime/body/semantic_tuning/robot_head_investor_show_v1.json`

**Important**
This file should:
- slightly increase expressiveness
- stay under conservative live-safe limits
- avoid bench-only actions
- be validated through the existing teacher-review / live observation loop

**Acceptance**
- show motions look larger and cleaner than the default
- no new unsafe motion path is introduced

---

## Pass D — Artifacts and evidence

### Step D1 — Add performance-run artifact output

**Recommended directory**
- `runtime/performance_runs/<run_id>/`

**Files to write**
- `run_summary.json`
- `cue_results.json`
- `session_export.json`
- `proof_results.json`
- `manifest.json`

**Important**
Include:
- show name
- session id
- chapter list
- cue results
- expected proof checks
- any degraded segments
- export paths

**Acceptance**
- every run leaves behind a self-contained artifact directory
- an operator can inspect one JSON file and understand what happened

---

### Step D2 — Thread the show metadata into episode export

**Recommended**
When exporting the session episode, attach:
- show name
- show version
- chapter timing
- cue results
- proof expectations
- degraded steps

This keeps the show data compatible with the existing evidence and replay story.

**Acceptance**
- exported session artifacts clearly say they came from the investor performance mode

---

## Pass E — Documentation and polish

### Step E1 — Update investor demo docs lightly
Do not rewrite core product docs. Add narrow references only.

**Recommended files**
- `docs/investor_demo.md`
- optional short pointer from `README.md`

**Update scope**
- add one section for deterministic investor performance mode
- mention the CLI/API entrypoint
- mention that the show is a side-track around the same companion core

### Step E2 — Keep the main product framing intact
Do not let docs imply:
- robot-first identity
- hidden teleoperation
- new autonomy claims
- a replacement for live interactive demos

---

## Suggested implementation order in plain English

1. Add contracts.
2. Add the JSON show asset.
3. Build the runner in pure Python.
4. Make proof cues silent and narration deterministic.
5. Expose the runner through operator service and CLI.
6. Add the show page.
7. Add configurable tuning path and show-specific tuning file.
8. Add artifact output.
9. Add tests.
10. Add narrow docs.

If Codex follows that order, the work should stay controlled and low-risk.
