# Local Companion Certification Runbook

This runbook is the maintained no-robot acceptance path for Blink-AI on a real Mac.

It answers two different questions:

1. Is the machine ready to prove the intended local companion path?
2. Is the repo/runtime behavior strong enough to present as a world-class local companion?

Use this flow when the robot is absent and the target product surface is `desktop_bodyless` or `desktop_virtual_body`.

## Daily Use Quick Start

This runbook is not only for certification. If you just want to use the product and test intelligence, start here:

```bash
uv run blink-appliance --open-console
```

Then open:

- [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console) for the full operator surface
- [http://127.0.0.1:8000/companion-test](http://127.0.0.1:8000/companion-test) for lightweight conversation testing

If you want terminal plus browser together, use:

```bash
uv run local-companion --open-console
```

The terminal loop accepts plain text directly and also supports:

- `/status`
- `/camera`
- `/listen`
- `/interrupt`
- `/export`
- `/actions status`
- `/actions approvals`
- `/actions approve <action_id> [note]`
- `/actions reject <action_id> [note]`
- `/actions history [limit]`
- `/actions connectors`
- `/actions workflows`
- `/actions bundle <bundle_id>`
- `/quit`

In `/console`, the most useful places to start are:

- `Live Conversation`
- `Perception Inputs`
- `Action Center`
- `Local Companion Readiness`

For voice testing in `/console`:

1. choose `browser_live` for text replies or `browser_live_macos_say` for spoken replies
2. click `Start Mic`
3. speak
4. click `Stop Mic + Send`

For camera testing in `/console`:

1. click `Enable Camera`
2. ask `what can you see from the camera`
3. click `Disable Camera` when finished

## Readiness Levels

- `machine_blocker`
  - The Mac cannot currently prove the intended local path.
  - Typical causes: Ollama unreachable, missing local model, denied camera permission, missing local capture dependency.
- `repo_or_runtime_bug`
  - The machine may be basically usable, but Blink-AI routed or behaved incorrectly.
  - Typical causes: wrong backend/profile resolution, broken local companion routing, failed local companion suite, broken Stage 6 linkage.
- `degraded_but_acceptable`
  - The companion is still usable and demoable in a bounded sense, but below the intended world-class bar.
  - Typical causes: a fallback path was honest, but the intended local path was not fully proven.
- `certified`
  - The Mac and the repo/runtime both proved the intended local product path.

## Command Order

Run these in order:

```bash
uv run local-companion-doctor
uv run local-companion-certify
uv run local-companion-failure-drills
uv run local-companion-burn-in
```

Or use the maintained Make targets:

```bash
make local-companion-certify
make local-companion-failure-drills
make local-companion-burn-in
make local-companion-stress
```

## What Each Command Proves

`uv run local-companion-doctor`

- probes Ollama reachability and local-model presence
- checks camera and native capture preflight
- verifies the actual backend path for the first and warm text turns
- verifies the personal-local behavior probe separately from the backend-path proof
- prints explicit next actions

`uv run local-companion-certify`

- runs the doctor
- runs `local-companion-checks`
- runs `always-on-local-checks`
- runs `continuous-local-checks`
- runs the maintained `local_companion_story`
- runs the maintained `desktop_story` regression lane
- verifies Action Plane workflow and episode-export linkage

`uv run local-companion-burn-in`

- exercises repeated text turns
- verifies the fast presence loop reaches honest `acknowledging`, `thinking_fast`, `tool_working`, `reengaging`, and `degraded` states when appropriate
- verifies reminder/workflow continuity after reopen
- checks interruption and resume behavior
- checks trigger stability
- checks repeated startup and shutdown cycles
- checks repeated push-to-talk and open-mic mode switching
- verifies export and action-bundle linkage after repeated activity

`uv run local-companion-failure-drills`

- injects local-model unavailable and provider-timeout paths
- injects malformed tool output and crashing tool handlers
- verifies mic unavailable, camera permission denied, and speaker unavailable surfaces stay inspectable
- verifies approval denial and unsupported action paths remain explicit
- verifies conflicting-memory correction, deletion, and honest no-hit retrieval
- verifies missing serial port, missing calibration, and unconfirmed live-write gates remain blocked safely

## Artifact Review

Certification artifacts are written under:

```text
runtime/diagnostics/local_companion_certification/<cert_id>/
```

Key files:

- `doctor/local_mbp_config_report.md`
- `local_companion_story.json`
- `desktop_story.json`
- `action_plane_validation.json`
- `certification.json`
- `../latest.json`
- `../latest_readiness.json`

Burn-in artifacts are written under:

```text
runtime/diagnostics/local_companion_burn_in/<suite_id>/
```

## Product Surfaces

The latest readiness state appears in:

- `local-companion` startup summary
- `/console` under `Local Companion Readiness`
- appliance status in `/api/appliance/status`
- runtime snapshot in `/api/operator/snapshot`

Use those surfaces to confirm that the same machine blockers or degraded warnings are visible to both operators and developers.

The runtime snapshot should now also show `presence_runtime` separately from `voice_loop`:

- `voice_loop`
  - microphone and speech-device lifecycle such as capture, endpointing, transcription, and barge-in
- `presence_runtime`
  - the user-facing fast loop such as `listening`, `acknowledging`, `thinking_fast`, `tool_working`, `speaking`, `reengaging`, and `degraded`

## Decision Rules

Use this rule set:

- `ship`
  - only when the certification verdict is `certified`
- `demo only`
  - when the verdict is `degraded_but_acceptable`
  - the system is still honest and useful, but the world-class bar is not yet proven
- `not ready`
  - when the verdict is `machine_blocker` or `repo_or_runtime_bug`

## When Doctor Is Red But Suites Are Green

Interpret that as a machine proof problem, not necessarily a product regression.

Typical response:

- fix Ollama or local-model availability
- fix camera permissions
- rerun `local-companion-doctor`
- rerun `local-companion-certify`

## When Doctor Is Green But Certification Is Red

Interpret that as a Blink-AI product/runtime regression.

Typical response:

- inspect the failed suite or story bundle
- inspect `action_plane_validation.json`
- inspect the linked episode export and `action_bundle_index`
- fix the repo/runtime issue
- rerun `local-companion-certify`

## World-Class Acceptance Rubric

The certification bundle scores these categories:

- usefulness
- honesty
- grounding
- memory continuity
- interruption and recovery
- latency and responsiveness
- proactive restraint
- operator clarity
- artifact completeness

Use the rubric plus the final verdict together. A green machine with weak artifact completeness or operator clarity is not a world-class local companion result.
