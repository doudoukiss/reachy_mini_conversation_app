# Repo Change Map and Execution Order

## Recommended execution order

### Step 1
Complete **Stage 0 — Local Appliance Reliability**.

Stop if:
- Blink-AI still requires terminal babysitting,
- device selection is still implicit,
- local auth is still confusing,
- camera/mic/speaker failures are not clearly recoverable.

### Step 2
Complete **Stage 1 — Agent OS and Tool Protocol**.

Stop if:
- skills are still informal,
- tools are not typed,
- subagents are not explicit,
- traces do not show structured decision flow.

### Step 3
Complete **Stage 2 — Continuous Perception, World Model, Social Runtime**.

Stop if:
- scene grounding is still mostly turn-triggered,
- the world model cannot distinguish fresh vs stale facts,
- social behavior is not tied to explicit state.

### Step 4
Complete **Stage 3 — Memory, Episode Flywheel, Teacher Mode**.

Stop if:
- memory remains a loose store instead of layered architecture,
- sessions do not export into useful episodes,
- human feedback cannot be attached cleanly.

### Step 5
Complete **Stage 4 — Semantic Embodiment and Feetech Bridge**.

Stop if:
- the brain can still reach raw servo protocol directly,
- the body compiler is not validated in virtual mode,
- live serial and dry-run do not share the same interface.

### Step 6
Complete **Stage 5 — Research Bridge and World-Class Evaluation**.

Stop if:
- planners are not swappable,
- replay is not deterministic,
- benchmark coverage is still mostly demo-centric.

## File-by-file focus map

### Desktop runtime
Existing area:
- `src/embodied_stack/desktop/`

Needs:
- launcher
- doctor
- device catalog
- explicit runtime profile manager
- local appliance orchestration
- setup wizard support

### Brain runtime
Existing areas:
- `src/embodied_stack/brain/app.py`
- `src/embodied_stack/brain/orchestrator.py`
- `src/embodied_stack/brain/executive.py`

Needs:
- stronger split between service runtime, planner runtime, and UI state
- clearer planner interface
- richer trace and checkpoint APIs

### Agent OS
Existing area:
- `src/embodied_stack/brain/agent_os/`

Needs:
- formal registry
- subagent runtime
- skill metadata
- lifecycle hooks
- checkpointing
- run-state recovery
- typed tool protocol integration

### Memory
Existing areas:
- `src/embodied_stack/brain/memory.py`
- `src/embodied_stack/brain/grounded_memory.py`

Needs:
- explicit memory layers
- write/promotion policies
- correction/deletion flows
- memory status UI

### Perception and multimodal
Existing areas:
- `src/embodied_stack/brain/perception.py`
- `src/embodied_stack/multimodal/`

Needs:
- continuous watcher
- structured event stream
- world-model normalization
- confidence and freshness logic
- triggered richer analysis path

### Body
Existing areas:
- `src/embodied_stack/body/`
- `src/embodied_stack/body/serial/`

Needs:
- stronger semantic catalog
- animation library
- calibration lifecycle
- bring-up tools
- health/state polling

### Shared contracts
Existing area:
- `src/embodied_stack/shared/`

Needs:
- tool schemas
- planner interface
- episode schema
- benchmark result schema
- versioning discipline

## Cross-stage quality gates

Every stage must add:
- tests
- replayability
- operator visibility
- exportable evidence
- clear degraded behavior

## Commands that should remain valid or improve

- `uv run pytest`
- `uv run local-companion`
- `uv run blink-appliance`
- current demo and replay commands
- current export paths

## Non-goals for this plan

- a full humanoid manipulation stack
- end-to-end VLA training on the MacBook
- rewriting the whole system in Rust or C++
- requiring the servo board for core progress
