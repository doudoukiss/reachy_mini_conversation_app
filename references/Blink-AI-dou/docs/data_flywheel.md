# Blink-AI Data Flywheel

## Why this exists

This data flywheel serves the local-first companion and optional embodiment product. It is not a separate robot-data-first thesis.

Blink-AI already records useful demo-time evidence:

- transcripts
- traces
- tool usage
- perception snapshots
- world-model transitions
- executive decisions
- semantic embodiment commands and body-state changes
- command acknowledgements
- telemetry

The data flywheel layer packages those into a single reusable unit called an **episode**.

An episode is not yet a final machine-learning dataset standard. It is a clean local export format that preserves enough structure and provenance to support:

- future fine-tuning datasets
- replay and regression evals
- simulation analysis
- human labeling and review
- later conversion into other robotics-data formats

## Episode format

Episode exports are versioned. The current schema version is:

- `blink_episode/v2`

Each export produces a directory under:

- `runtime/episodes/<episode_id>/`

Core files:

- `summary.json`
- `episode.json`
- `sessions.json`
- `transcript.json`
- `traces.json`
- `tool_calls.json`
- `perception_snapshots.json`
- `world_model_transitions.json`
- `executive_decisions.json`
- `commands.json`
- `acknowledgements.json`
- `telemetry.json`
- `episodic_memory.json`
- `semantic_memory.json`
- `profile_memory.json`
- `relationship_memory.json`
- `procedural_memory.json`
- `memory_actions.json`
- `memory_reviews.json`
- `memory_retrievals.json`
- `grounding_sources.json`
- `asset_refs.json`
- `annotations.json`
- `manifest.json`

## What an episode contains

At minimum, the export includes:

- timestamps
- source type: `session` or `demo_run`
- session metadata
- transcript turns
- tool calls
- perception snapshots
- world-model transitions
- executive decisions
- emitted commands
- acknowledgements
- telemetry
- exported memory layers and memory audit logs
- runtime mode and body-driver context carried through the recorded telemetry and commands
- final world state
- final world model
- grounding sources used by the reply path
- annotation-ready labels

## Asset references

Episodes may also contain asset references when the runtime had them.

Current supported examples:

- perception fixture paths
- image-style frame references
- clip-style replay references
- optional audio-path hooks if transcript metadata explicitly provided them

This is intentionally conservative. Blink-AI does not invent asset provenance that the runtime did not actually capture.

## Annotation-ready labels

The exporter writes `annotations.json` with pending-review label suggestions for:

- `successful_grounding`
- `failed_grounding`
- `greeting_quality`
- `escalation_correctness`
- `safe_fallback_correctness`

These are not final human labels. They are review-ready suggestions meant to reduce later annotation friction.

## Redaction hooks

Current export hooks can redact:

- operator notes
- session memory

Relationship and procedural memory are exported because companion continuity needs to stay auditable. That does not change the governance rule: selective storage is better than storing everything.

When redactions are applied, the episode manifest and summary record them explicitly.

## Commands

List exported episodes:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.episodes list
```

Show one episode:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.episodes show <episode_id>
```

Export from a demo run:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.episodes export-run <run_id>
```

Export from a live session:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.episodes export-session <session_id>
```

You can also export from the operator console.

## How this maps to future training pipelines

The current format is Blink-native on purpose.

That means:

- it preserves project terminology directly
- it avoids premature commitment to a single robotics dataset standard
- it stays easy to inspect as plain JSON while the product loop is still changing

Later, this can map into LeRobot-style or similar pipelines roughly like this:

- episode metadata -> dataset episode header / task metadata
- transcript turns -> language observations and targets
- perception snapshots -> vision observations and frame-linked annotations
- world-model transitions -> latent-state or supervision targets
- executive decisions -> policy labels or critique targets
- commands + acknowledgements -> action and outcome supervision
- telemetry -> low-level environment context and safety outcome context
- annotation labels -> eval targets or fine-tuning quality tags

The important design choice is that Blink-AI keeps the exported structure explicit enough that a later conversion script can be written cleanly.

## What this does not do yet

- no large-scale dataset curation UI
- no deduplication or sampling service
- no remote labeling platform
- no automatic conversion into a public robotics-data format
- no privacy framework beyond the current local redaction hooks

That is intentional. The project is building the first reliable bridge from demos to data, not a full ML ops stack.
