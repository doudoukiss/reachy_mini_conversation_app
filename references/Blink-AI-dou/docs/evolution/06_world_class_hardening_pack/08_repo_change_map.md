# Repo Change Map

This file tells Codex where to cut the code so the repo becomes easier to maintain.

## Highest-priority splits

### 1. `src/embodied_stack/desktop/devices.py`

Split into:

- `desktop/device_catalog.py`
- `desktop/device_selection.py`
- `desktop/audio_runtime.py`
- `desktop/camera_runtime.py`
- `desktop/device_health.py`
- `desktop/device_permissions.py`

### 2. `src/embodied_stack/brain/operator_console.py`

Split into:

- `brain/operator/appliance.py`
- `brain/operator/console_snapshot.py`
- `brain/operator/runs.py`
- `brain/operator/incidents.py`
- `brain/operator/memory_review.py`
- `brain/operator/perception.py`

### 3. `src/embodied_stack/demo/episodes.py`

Split into:

- `demo/episodes/models.py`
- `demo/episodes/capture.py`
- `demo/episodes/export.py`
- `demo/episodes/teacher.py`
- `demo/episodes/datasets.py`

### 4. `src/embodied_stack/brain/perception.py`

Split into:

- `brain/perception/watcher.py`
- `brain/perception/semantic_refresh.py`
- `brain/perception/facts.py`
- `brain/perception/freshness.py`
- `brain/perception/uncertainty.py`

### 5. `src/embodied_stack/brain/agent_os/tools.py` and `src/embodied_stack/brain/tools.py`

Split into:

- `brain/tooling/registry.py`
- `brain/tooling/executors.py`
- `brain/tooling/policies.py`
- `brain/tooling/results.py`
- `brain/tooling/permissions.py`

### 6. `src/embodied_stack/brain/grounded_memory.py` and adjacent memory modules

Split into:

- `brain/memory/retrieval.py`
- `brain/memory/promotion.py`
- `brain/memory/reviews.py`
- `brain/memory/redaction.py`
- `brain/memory/world_state.py`

## Secondary-priority splits

### 7. `src/embodied_stack/brain/venue_knowledge.py`

Split into:

- ingestion
- normalization
- query
- retrieval
- calendar integration

### 8. `src/embodied_stack/brain/shift_supervisor.py`

Split into:

- schedule policy
- state transitions
- attract mode
- closing/quiet-hours policy
- degradation policy

### 9. `src/embodied_stack/brain/app.py`

Keep the app factory thin.
Move route-local logic into focused service modules where useful.

## Rules for all splits

1. Do not change public behavior casually.
2. Move tests with the ownership split.
3. Preserve compatibility shims only when they reduce migration risk materially.
4. Update docs when boundaries change.
5. Prefer smaller, boring modules over framework-heavy abstractions.
