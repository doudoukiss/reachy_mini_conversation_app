# Development Guide

This guide is the practical entry point for engineers working on Blink-AI after the initial feature-building phase.

Before making large changes, read [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md) first, then [current_direction.md](/Users/sonics/project/Blink-AI/docs/current_direction.md), and then [evolution/README.md](/Users/sonics/project/Blink-AI/docs/evolution/README.md) if you need historical context.

If you are onboarding someone to the daily-use product path, start them with [companion_quickstart.md](/Users/sonics/project/Blink-AI/docs/companion_quickstart.md) before handing them the full repo guide.
If you are changing memory, continuity, or companion behavior rules, also read [relationship_runtime.md](/Users/sonics/project/Blink-AI/docs/relationship_runtime.md).

## Product framing for contributors

- Blink-AI is a terminal-first, local-first, character-presence companion OS with optional embodiment.
- `uv run local-companion` is the primary product surface.
- `uv run blink-appliance` and `/console` are browser/operator surfaces around the same core runtime.
- The character presence runtime is the next major product layer, built around a `fast loop / slow loop` split.
- The relationship runtime is the bounded continuity layer inside the companion.
- `venue_demo` is an explicit vertical mode for community concierge / guide demos and pilots.
- Embodiment stays central to the architecture, but the body is optional for product usefulness and day-to-day development.
- Robot and venue-demo layers should read as mode-specific deployments of the same companion core, not competing product identities.

## System Structure

### Default runtime entrypoint

- `src/embodied_stack/desktop/cli.py`
  - Terminal-first companion and lower-level desktop CLI entrypoints used by `uv run local-companion`.
- `src/embodied_stack/desktop/launcher.py`
  - Browser/operator localhost appliance entrypoint used by `uv run blink-appliance`.
- `src/embodied_stack/desktop/app.py`
  - Default FastAPI entrypoint for local development and the main one-process runtime.
- `src/embodied_stack/desktop/runtime.py`
  - In-process companion runtime that owns desktop bodyless, virtual-body, and serial-body behavior.
- `src/embodied_stack/desktop/profiles.py`
  - Runtime-profile helpers that map desktop runtime modes to body-driver behavior and compose the active desktop demo profile.
- `src/embodied_stack/desktop/runtime_profile.py`
  - Appliance profile persistence, runtime-layout repair, config precedence, and runtime reset helpers.

### Brain-side modules

- `src/embodied_stack/brain/app.py`
  - Brain service factory and operator-facing HTTP surface used by both desktop and tethered entrypoints.
- `src/embodied_stack/brain/orchestrator.py`
  - Thin runtime coordinator that keeps request sequencing, dependency wiring, and trace/session orchestration.
- `src/embodied_stack/brain/orchestration/`
  - Internal helper package for the branch-heavy runtime paths.
  - `interaction.py`: speech and non-speech turn handling, reply shaping, and command generation.
  - `grounding.py`: grounding-source collection, dedupe, and executive/shift grounding augmentation.
  - `state_projection.py`: world-state refresh, trace outcome derivation, world-model diffs, and session-summary helpers.
- `src/embodied_stack/brain/memory.py`
  - File-backed local state for sessions, user memory, traces, incidents, perception, and world state.
- `src/embodied_stack/brain/venue_knowledge.py`
  - Pilot-site content ingestion for FAQs, rooms, schedules, contacts, and docs.
- `src/embodied_stack/brain/perception/`
  - Package facade for perception providers, fixture replay, event publishing, and perception history.
- `src/embodied_stack/brain/executive.py`
  - Deterministic interaction policy layered on top of dialogue results.
- `src/embodied_stack/brain/skill_library/`
  - First-party companion and venue/demo skills, including greeting/re-entry, unresolved-thread follow-up, day planning, observe-and-comment, and mode-specific concierge playbooks.
- `src/embodied_stack/brain/shift_supervisor.py`
  - Long-horizon operating state such as ready, assist, follow-up, quiet, closing, and degraded.
- `src/embodied_stack/brain/operator/`
  - Operator-service package that owns aggregated operator workflows over the same orchestrator and edge gateway used by demos.

### Edge-side modules

- `src/embodied_stack/edge/app.py`
  - Optional FastAPI entrypoint for the fake robot or future tethered/Jetson-shaped runtime.
- `src/embodied_stack/edge/controller.py`
  - Command application, duplicate suppression, and telemetry/history aggregation.
- `src/embodied_stack/edge/drivers.py`
  - Driver profiles and adapter wiring for fake-robot and Jetson landing-zone compatibility modes.
- `src/embodied_stack/edge/adapters.py`
  - Actuator, input, and monitor adapter boundaries.
- `src/embodied_stack/edge/safety.py`
  - Command validation, capability checks, and motion clamping.

### Shared and support modules

- `src/embodied_stack/shared/contracts/`
  - Domain-organized Pydantic contracts split into `edge.py`, `brain.py`, `perception.py`, `demo.py`, `operator.py`, and `body.py`.
- `src/embodied_stack/shared/models.py`
  - Compatibility re-export shim for the shared contract surface. Existing imports from `embodied_stack.shared.models` must continue to work for one stable iteration.
- `src/embodied_stack/body/`
  - Semantic embodiment layer, normalized body-state models, head-profile loading, and driver interfaces.
- `src/embodied_stack/action_plane/`
  - Stage 6 digital-side-effect runtime, including connector registry, connector implementations, connector health, deterministic policy, approval lifecycle, replay, idempotent execution persistence, and the Stage 6D workflow runtime under `action_plane/workflows/`.
- `src/embodied_stack/multimodal/`
  - Desktop-local camera and perception glue modules.
- `src/embodied_stack/voice/`
  - STT/TTS and local voice-pipeline abstractions.
- `src/embodied_stack/desktop/devices/`
  - Device-runtime package facade for desktop camera, microphone, speaker, and AVFoundation selection helpers.
- `src/embodied_stack/brain/tooling/`
  - Compatibility package for Agent OS tool registry and knowledge-tool ownership slices.
- `src/embodied_stack/demo/`
  - Demo orchestration, evidence artifacts, tethered workflows, shift simulator, and episode export.
- `src/embodied_stack/demo/episodes/`
  - Package facade for episode export and artifact-store logic.
- `src/embodied_stack/sim/`
  - Local scenario runner for deterministic dry-run sequences.

## Daily Workflow

### Environment setup

```bash
brew install uv
uv sync --dev
```

### Core validation

```bash
make validate
```

Equivalent manual commands:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

### Demo validation

```bash
make demo-checks
make multimodal-demo-checks
make tethered-smoke
```

### Local desktop stack

Preferred daily-use product loop:

```bash
uv run local-companion
```

This is the primary terminal-first companion path. It keeps `personal_local` as the default context and treats the browser console as optional.
It also exposes relationship continuity as inspectable runtime state: explicit profile preferences, open follow-ups from reminders/session digests, and bounded tone or boundary preferences that show up in `/status` and the operator snapshot.

```bash
uv run blink-appliance
```

This is the preferred browser/operator appliance path when you want the console, Action Center, approvals, or browser-led inspection. It starts the service on localhost, repairs runtime directories, provisions local appliance auth through a short-lived bootstrap exchange, and opens `/setup` or `/console` in the browser.
It remains valuable, but it is not required for the daily terminal-first companion loop.

Lower-level local service control remains available through:

```bash
uv run uvicorn embodied_stack.desktop.app:app --reload --port 8000
```

Useful explicit desktop-first config:

```bash
BLINK_RUNTIME_MODE=desktop_virtual_body
BLINK_MODEL_PROFILE=companion_live
BLINK_BACKEND_PROFILE=companion_live
BLINK_VOICE_PROFILE=desktop_local
BLINK_CAMERA_SOURCE=default
BLINK_BODY_DRIVER=virtual
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json
```

For terminal-first companion use, quick smoke checks, and the daily product loop:

```bash
uv run local-companion
uv run local-companion-story
uv run local-companion-checks
uv run local-companion-certify
uv run local-companion-failure-drills
uv run local-companion-burn-in
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli shell
```

`uv run local-companion` is the maintained terminal-first companion path. It auto-exports a session evidence bundle on exit unless `--no-export` is passed.

Use `uv run local-companion --help` for the concise command-line guide, then `/help` inside the loop for the runtime command map. Use `/console` only when you want the optional browser operator surface from the same runtime.

`uv run local-companion-story` runs the maintained repeatable local companion walkthrough.

`uv run local-companion-checks` runs the focused local companion eval suite for mic or speaker loop closure, webcam grounding, fallback honesty, memory recall, relationship continuity with bounded tone/follow-up behavior, uncertainty honesty, and bodyless or virtual-body continuity.

`uv run local-companion-certify` is the maintained no-robot certification lane. It runs the doctor, the three local companion suites, the maintained local companion story, the maintained desktop story regression lane, and a deterministic Action Plane linkage check, then writes an aggregate bundle under `runtime/diagnostics/local_companion_certification/<cert_id>/`.

`uv run local-companion-failure-drills` is the deterministic failure-injection lane for provider timeouts, malformed tool results, tool exceptions, device denial, memory conflict resolution, approval denial, unsupported actions, and serial safety gates.

`uv run local-companion-burn-in` is the bounded long-run lane for repeated turns, reminder/workflow continuity, interruption recovery, trigger stability, repeated startup or shutdown, repeated mode switching, and export linkage under `runtime/diagnostics/local_companion_burn_in/<suite_id>/`.

For milestone acceptance, use these Make targets:

```bash
make acceptance-quick
make acceptance-full
make acceptance-rc
make acceptance-manual-local
make acceptance-hardware
```

- `acceptance-quick` runs the high-yield focused pytest slices plus the three maintained local companion suites and the scenario dry-run.
- `acceptance-full` runs the full repo validation, scenario dry-run, certification, burn-in, and demo checks.
- `acceptance-rc` runs the stricter release-candidate lane, including smoke and multimodal demo checks, and requires a fully certified no-robot certification result.
- `acceptance-manual-local` records the manual local-Mac acceptance checklist instead of pretending it can be automated.
- `acceptance-hardware` keeps the optional live-serial lane separate and honestly skipped when the required environment is absent.

The older `stabilize-fast`, `stabilize-full`, and `stabilize-live-local` targets remain as compatibility aliases to the acceptance targets.

Use [acceptance.md](/Users/sonics/project/Blink-AI/docs/acceptance.md) for the maintained test-surface inventory, artifact layout, and lane definitions.

Canonical interaction profiles are `companion_live`, `m4_pro_companion`, `cloud_demo`, `local_dev`, and `offline_stub`.

Use them this way:

- `companion_live`: default daily-use product profile. It keeps memory, orchestration, and local media on-device, prefers low-latency provider dialogue when configured, and keeps semantic vision selective instead of default-on.
- `m4_pro_companion`: local-first flagship fallback. Use it when you want the strongest all-local companion path on the Mac, with Ollama text plus optional Ollama vision.
- `cloud_demo`: explicit provider-backed demo profile when you want cloud-first reasoning and multimodal perception for a guided showcase.
- `local_dev`: development-oriented profile for browser or fixture-heavy iteration with cheaper local fallbacks.
- `offline_stub`: deterministic no-provider fallback for robustness, CI, and honest degraded operation.

Canonical backend profiles are `companion_live`, `cloud_best`, `m4_pro_companion`, `local_balanced`, `local_fast`, and `offline_safe`.

Use the backend profiles this way:

- `companion_live`: default backend routing for daily companion use. Native camera snapshots stay cheap by default, while semantic vision is available for explicit visual queries and supervised refresh.
- `m4_pro_companion`: local-first backend routing with Ollama text, Ollama vision, local embeddings, and native Mac media services.
- `local_balanced`: local-first route that keeps stronger on-device reasoning while avoiding unnecessary always-hot vision residency.
- `local_fast`: smallest local latency and memory-pressure profile. Prefer it when unified memory or model cold-start cost is the bottleneck.
- `offline_safe`: deterministic no-provider route for bring-up and failure drills.

Canonical embodiment profiles are `bodyless`, `virtual_body`, and `serial_body`.

Useful CLI helpers:

```bash
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli reset
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli scene attentive_listening --reset-first
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli story --story-name desktop_story
```

The `desktop_story` sequence is the maintained default investor walkthrough for the one-process desktop runtime.

### Optional tethered compatibility stack

```bash
make demo-up
make demo-status
make demo-reset
```

Use this when you specifically want the two-process HTTP bridge. It launches the brain in `tethered_future` mode against the edge service.

## Debugging Notes

### Health and readiness

- Brain health: `GET /health`
- Brain readiness: `GET /ready`
- Edge health: `GET /health`
- Edge readiness: `GET /ready`

Use `/health` to confirm process identity and runtime profile.
Use `/ready` to inspect dependency-specific status such as store paths, dialogue configuration, edge transport, and operator auth.

### Local state and artifact paths

- Brain state: `runtime/brain_store.json`
- Operator auth token: `runtime/operator_auth.json`
- Appliance profile: `runtime/appliance_profile.json`
- Demo run artifacts: `runtime/demo_runs/`
- Demo check artifacts: `runtime/demo_checks/`
- Episode exports: `runtime/episodes/`
- Shift reports: `runtime/shift_reports/`
- Action Plane state: `runtime/actions/`
- Local companion certification: `runtime/diagnostics/local_companion_certification/`
- Local companion burn-in: `runtime/diagnostics/local_companion_burn_in/`
- Browser-live timeout artifacts: `runtime/diagnostics/live_turn_failures/`
- Tethered stack metadata: `runtime/tethered_demo/live/stack_info.json`

These runtime paths are local working state and generated evidence, not durable repository documentation. Keep source-of-truth docs under `docs/` and treat `runtime/` as disposable local output unless you are intentionally preserving an artifact.

`runtime/actions/` currently persists the Stage 6 gateway, browser, and workflow state:
- `pending_approvals.json`
- `execution_log.json`
- `connector_health.json`
- `browser/`
- `exports/action_bundles/<bundle_id>/`
- `exports/action_replays/<replay_id>/`
- `workflows/run_index.json`
- `workflows/trigger_state.json`
- `workflows/runs/<workflow_run_id>.json`
- `workflows/artifacts/<workflow_run_id>/...`

Treat `runtime/` as a single-writer workspace for the currently running Blink-AI process tree.
Do not point multiple live appliance, demo, or tethered stacks at the same runtime directory unless you intentionally isolate their store and artifact paths first.

If `runtime/brain_store.json` becomes malformed, the brain now starts with a clean in-memory snapshot and moves the broken file aside as `brain_store.json.corrupt-*`.

Mutable singleton JSON files under `runtime/` now write atomically and keep short `.bak` history.
Append-only artifact directories write each JSON file atomically and quarantine malformed files as `*.corrupt-*` instead of crashing list views.

Malformed demo, shift-report, or episode summaries are skipped during listing instead of breaking operator-facing views.

Unexpected orchestration-helper failures are logged before they bubble out of request handling.
That log path should now be one of the first places to check when a request fails without an obvious protocol or dependency error.

Browser-live timeouts now write a dedicated failure bundle under `runtime/diagnostics/live_turn_failures/`.
Each bundle captures request metadata, stage timings, latest perception, backend status, voice state, and the latest Action Plane snapshot so “no reply for five minutes” bugs stop being silent.

### Auth and operator console

- Appliance mode is tokenless on localhost and opens `/console` directly.
- The console is still protected by the local operator token in non-appliance service modes.
- If `OPERATOR_AUTH_TOKEN` is unset, Blink-AI generates a runtime token file locally.
- The direct desktop-service and tethered paths write that token to `runtime/operator_auth.json` unless you override the path.
- Operator auth status is explicit in the runtime snapshot as `appliance_localhost_trusted`, `configured_static_token`, or `disabled_dev`.
- In appliance mode the browser shows `/setup` before `/console` until the local appliance profile is saved under `runtime/appliance_profile.json`.
- The setup flow now surfaces runtime-directory health, config source, device preset, selected native microphone/camera, speaker-routing support, and Ollama reachability before the operator relies on the console.
- Tests disable the background shift thread and use a fixed auth token.
- The console now exposes the composed active runtime profile, provider state, body status, fallback events, emitted embodied actions, and the latest companion latency signals.
- The console and local companion CLI also expose active skill, perception freshness, memory status, fallback state, model residency, and live-turn latency breakdown in the runtime snapshot.
- Treat `/console` as an optional operator surface around the terminal-first companion loop, not as the default daily-use identity of the product.
- `Reset + Run Desktop Story` is the fastest browser path to the maintained replayable investor sequence.
- `Reset + Run Local Companion Story` is the fastest browser path to the maintained local companion sequence.

For immediate intelligence testing, use `uv run blink-appliance`. Token auth is now only for direct non-appliance service launches.

Local companion session exports now also include a `runtime_snapshot.json` artifact so later review or eval can see the model profile, active skill, perception freshness, memory status, fallback state, device health, and body mode present at export time.

### Transport debugging

- Desktop-first development uses the in-process embodiment gateway by default.
- Brain-to-edge HTTP behavior is encapsulated in `HttpEdgeGateway` and is only on the critical path for tethered modes.
- A degraded transport should surface through:
  - readiness checks
  - `edge_transport_state`
  - `edge_transport_error`
  - safe-idle telemetry and heartbeat status

When the edge is unreachable, the gateway should degrade honestly without pretending commands were applied.

### Serial body debugging

The Feetech/ST landing zone now lives under `src/embodied_stack/body/serial/`.

Useful commands:

```bash
uv run blink-serial-doctor --ids 1-11 --auto-scan-baud
PYTHONPATH=src uv run python -m embodied_stack.body.calibration ports
PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport dry_run scan --ids 1-11
PYTHONPATH=src uv run python -m embodied_stack.body.calibration --transport dry_run read-health --ids 1-3
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport fixture_replay \
  --fixture src/embodied_stack/body/fixtures/robot_head_serial_fixture.json \
  read-position --ids 1
```

Live serial should only be used once the bus is powered and bench-observed:

```bash
PYTHONPATH=src uv run python -m embodied_stack.body.calibration \
  --transport live_serial \
  --port /dev/cu.usbmodem5B790314811 \
  --baud 1000000 \
  doctor --ids 1-11 --auto-scan-baud
```

Stage A remains read-only. The doctor workflow writes `runtime/serial/bringup_report.json`, includes request/response hex history, and prints a `suggest-env` block for `desktop_serial_body`.

Preferred Mac workflow:

1. `uv run blink-serial-doctor --ids 1-11 --auto-scan-baud`
2. inspect `runtime/serial/bringup_report.json`
3. rerun with `--port /dev/cu...` when multiple recommended ports exist
4. use `body-calibration read-position` and `body-calibration read-health` to confirm stable readback
5. only after Stage A is clean, move to live calibration capture in Stage B

Use [serial_head_mac_runbook.md](/Users/sonics/project/Blink-AI/docs/serial_head_mac_runbook.md) for the full failure-order runbook.

### Action Plane debugging

The Stage 6 Action Plane currently routes these bounded digital side effects:

- `write_memory`
- `promote_memory`
- `request_operator_help`
- `log_incident`
- `browser_task`
- `create_reminder`
- `list_reminders`
- `mark_reminder_done`
- `create_note`
- `append_note`
- `search_notes`
- `read_local_file`
- `stage_local_file`
- `export_local_bundle`
- `query_calendar`
- `draft_calendar_event`

Current Stage 6 Stage A/B/C/D/E/F rules:

- session-memory writes from normal user turns execute immediately
- proactive local writes downgrade to preview-only
- model-initiated operator-sensitive writes become pending approvals
- operator-console operator-sensitive writes execute with implicit operator approval
- `browser_task` now routes through the bounded browser runtime connector
- browser backends are `disabled`, `stub`, and `playwright`
- read-only browser actions (`open_url`, `capture_snapshot`, `extract_visible_text`, `summarize_page`, `find_click_targets`) execute immediately when the browser connector is supported and configured
- effectful browser actions (`click_target`, `type_text`, `submit_form`) remain approval-gated for user-turn and proactive invocations, and execute with implicit operator approval from the operator console
- browser runtime state persists under `runtime/actions/browser/`, with per-action artifacts under `runtime/actions/browser/<action_id>/` and per-session state under `runtime/actions/browser/sessions/`
- unsafe browser targets remain blocked by default: password fields, file uploads, `file:`, `chrome:`, `about:`, localhost, loopback, and private-network URLs unless explicitly allowlisted
- replays generate a fresh action request and re-enter policy instead of silently reusing old approval
- local-files actions stay inside `BLINK_ACTION_PLANE_LOCAL_FILE_ROOTS`, which defaults to the repo root in development
- workflows are code-defined and versioned in repo code, not authored as runtime graphs
- workflow connector steps reuse the same Action Plane gateway as normal tool calls
- workflow runs pause on pending approvals, persist under `runtime/actions/workflows/`, and resume or retry explicitly instead of replaying successful steps
- proactive workflow evaluation runs on the existing `ShiftAutonomyRunner` tick; there is no separate workflow daemon
- Action Plane work now writes live `blink_action_bundle/v1` sidecar bundles under `runtime/actions/exports/action_bundles/`
- deterministic Action Plane replay writes under `runtime/actions/exports/action_replays/` and always uses non-live stub or dry-run backends
- episode exports link related Action Plane work through `linked_action_bundles.json` and `derived_artifact_files["action_bundle_index"]`
- research and benchmark exports now carry linked action bundles, linked action replays, and action-quality metrics additively rather than replacing the existing episode or research formats
- `/console` now treats Stage 6 as a unified Action Center backed by `/api/operator/action-plane/overview`
- `local-companion` can now inspect and resolve Stage 6 work in-process through `/actions ...` slash commands
- runtime boot now reconciles nonterminal Stage 6 work conservatively: uncertain actions become `uncertain_review_required`, dependent workflows pause with `runtime_restart_review`, and nothing auto-replays or auto-approves after restart

Useful inspection points:

- `runtime/actions/pending_approvals.json`
- `runtime/actions/execution_log.json`
- `runtime/actions/connector_health.json`
- `runtime/actions/browser/`
- `runtime/actions/exports/action_bundles/`
- `runtime/actions/exports/action_replays/`
- `runtime/actions/workflows/`
- `/api/operator/snapshot` -> `runtime.action_plane`
- `/api/operator/action-plane/overview`
- `/api/operator/action-plane/status`
- `/api/operator/action-plane/connectors`
- `/api/operator/action-plane/browser/status`
- `/api/operator/action-plane/browser/task`
- `/api/operator/action-plane/approvals`
- `/api/operator/action-plane/history`
- `/api/operator/action-plane/bundles`
- `/api/operator/action-plane/bundles/{bundle_id}`
- `/api/operator/action-plane/replays`
- `/api/operator/action-plane/workflows`
- `/api/operator/action-plane/workflows/runs`
- `TypedToolCallRecord` action metadata inside the latest run or trace payloads

Useful browser runtime settings:

```bash
BLINK_ACTION_PLANE_BROWSER_BACKEND=disabled|stub|playwright
BLINK_ACTION_PLANE_BROWSER_HEADLESS=true|false
BLINK_ACTION_PLANE_BROWSER_STORAGE_DIR=runtime/actions/browser
BLINK_ACTION_PLANE_BROWSER_ALLOWED_HOSTS=
```

Useful Action Plane CLI helpers:

```bash
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli connector-status
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli approval-list
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli approval-approve <action_id> --operator-note "approved"
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli approval-reject <action_id> --operator-note "rejected"
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli action-history --limit 20
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli replay-action <action_id> --operator-note "retry"
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli action-bundle-list --limit 20
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli action-bundle-show <bundle_id>
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli action-bundle-teacher-review <bundle_id> --summary "good" --action-feedback "clear operator note"
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli replay-action-bundle <bundle_id> --operator-note "deterministic replay"
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-list
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-runs --session-id <session_id>
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-start <workflow_id> --inputs '{"key":"value"}'
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-resume <workflow_run_id>
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-retry <workflow_run_id>
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli workflow-pause <workflow_run_id>
```

Useful `local-companion` Stage 6 slash commands:

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

Useful Stage 6 validation targets:

```bash
make action-plane-validate
make browser-runtime-smoke
make workflow-replay-smoke
make action-export-inspect
make local-companion-certify
make local-companion-burn-in
```

Use [stage6_operator_runbook.md](/Users/sonics/project/Blink-AI/docs/stage6_operator_runbook.md) for the operator-facing recovery and Action Center workflow.
Use [local_companion_certification_runbook.md](/Users/sonics/project/Blink-AI/docs/local_companion_certification_runbook.md) for the no-robot local companion certification workflow.

Current built-in workflows:

- `capture_note_and_reminder`
- `morning_briefing`
- `event_lookup_and_open_page`
- `reminder_due_follow_up`

Useful workflow settings:

```bash
BLINK_WORKFLOW_MORNING_BRIEFING_TIME=09:00
BLINK_WORKFLOW_RUN_TIMEOUT_SECONDS=900
```

Stage B stays CLI-first and operator-gated. The default live calibration path is now `runtime/calibrations/robot_head_live_v1.json`, the default live baud is `1000000`, and the bench workflow is:

1. `body-calibration capture-neutral --confirm-live-write --confirm-visual-neutral`
2. `body-calibration set-range ... --in-place` for any joints that captured outside inherited limits and for mirrored lid or brow confirmations
3. `body-calibration validate-coupling --in-place`
4. `body-calibration arm-live-motion`
5. `body-calibration move-joint`, `sync-move`, `write-neutral`, `torque-on`, `torque-off`, `safe-idle`, and `bench-health`

Every Stage B bench write now records a JSON artifact under `runtime/serial/motion_reports/`, and the live arm lease is stored at `runtime/serial/live_motion_arm.json`.

Stage C lifts the same serial stack into `desktop_serial_body`. The desktop runtime now polls live serial state directly through the serial body driver, `/console` shows port, baud, confirmed-live status, arm state, last command outcome, target versus readback, and servo health, and the operator console can trigger connect, disconnect, scan, ping, read-health, write-neutral, arm, disarm, and semantic smoke without shelling out to CLI commands.

Stage D keeps that runtime path but upgrades the body surface from joint-safe smoke to semantic social actions. The canonical Stage D operator and bench surface is now action-based: `look_left`, `look_right`, `look_up`, `look_down_briefly`, `blink_soft`, `listen_attentively`, `friendly`, `thinking`, `concerned`, `confused`, `nod_small`, `tilt_curious`, `recover_neutral`, and `safe_idle`. `body-calibration list-semantic-actions` shows the current catalog, `body-calibration semantic-smoke --action ...` runs one semantic action through the compiler and serial bridge, and `body-calibration teacher-review` records operator feedback plus optional tuning deltas under `runtime/body/semantic_tuning/`.

Stage E standardizes the validation path into three tiers:

1. always-on CI: `uv run pytest` and `PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run`
2. manual Mac bench suite: `uv run blink-serial-bench --transport live_serial ...`
3. opt-in hardware pytest: `pytest -m live_serial` and `pytest -m live_serial_motion`

The maintained Stage E make targets are:

- `make serial-doctor`
- `make serial-bench`
- `make serial-neutral`
- `make serial-companion`

`make serial-bench` and `make serial-neutral` intentionally require `BLINK_CONFIRM_LIVE_WRITE=1` on live hardware. The bench suite writes one evidence directory under `runtime/serial/bench_suites/<suite_id>/` with doctor, scan, position, health, calibration snapshot, motion report index, console snapshot, body telemetry, failure summary, and normalized request/response history.

The current real-head observation sequence is also maintained in-repo:

```bash
BLINK_SERIAL_PORT=/dev/cu.usbmodem5B790314811 \
BLINK_SERVO_BAUD=1000000 \
BLINK_HEAD_PROFILE=src/embodied_stack/body/profiles/robot_head_v1.json \
BLINK_HEAD_CALIBRATION=runtime/calibrations/robot_head_live_v1.json \
bash scripts/serial_head_live_observation.sh
```

That script now:

- runs direct probes, sync groups, and semantic actions sequentially
- writes `write-neutral` between actions
- ends successful runs in a neutral hold with torque still on
- writes `neutral_tolerance_check.json` from the final `bench-health` snapshot
- falls back to `write-neutral`, then `safe-idle`, then `disarm-live-motion` on failure

Current live hardware note:

- the validated Mac adapter path is `/dev/cu.usbmodem5B790314811`
- the validated live baud is `1000000`
- the right brow issue was traced to a bad saved live neutral and corrected in `runtime/calibrations/robot_head_live_v1.json`

The opt-in hardware pytest gates are:

```bash
BLINK_RUN_LIVE_SERIAL_TESTS=1 uv run pytest -m live_serial
BLINK_RUN_LIVE_SERIAL_TESTS=1 BLINK_RUN_LIVE_SERIAL_MOTION_TESTS=1 uv run pytest -m live_serial_motion
```

The serial body driver refuses live motion when:

- the configured head profile path is missing
- the live transport has not confirmed a healthy servo reply
- live motion is not armed for the active port, baud, and calibration
- the saved calibration still has unresolved range conflicts or coupling validation gaps
- a compiled raw target would exceed the profile limits

## Known Limitations

- `src/embodied_stack/shared/models.py` is now a compatibility shim. It should remain in place for one stable iteration, then be removed only after internal imports have migrated cleanly to `src/embodied_stack/shared/contracts/`.
- `src/embodied_stack/shared/contracts/brain.py` and `src/embodied_stack/shared/contracts/demo.py` still carry a large share of the contract surface and will likely need another split if the schema set keeps growing.
- `src/embodied_stack/brain/venue_knowledge.py` and `src/embodied_stack/brain/shift_supervisor.py` remain the largest unsplit brain modules.
- The desktop runtime is now the primary path, but the local voice and multimodal adapters are still intentionally conservative and rely on typed fallback when a real device or provider path is unavailable.
- `src/embodied_stack/brain/orchestrator.py` is slimmer than before, but it is still the sequencing boundary for multiple subsystems and should stay intentionally boring.
- Persistence is file-backed and local-first. It is appropriate for the current single-process checkpoint, but it is not yet designed for concurrent writers or fleet-scale operation.
- The future Jetson path is still a simulation-first landing zone. Hardware adapter boundaries exist, but most real hardware integrations remain unwired.
- `video_file_replay` is a fixture-replay workflow, not a general-purpose live perception submission mode.
