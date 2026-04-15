# Stage D — Memory, Episode, Teacher Mode, and Dataset v2

## Objective

Turn Blink-AI’s memory and exported artifacts into a serious data flywheel.

## Step-by-step work order

### Step 1 — Make memory policy explicit and score-based

Tasks:

1. Keep separate policies for:
   - profile memory
   - episodic memory
   - semantic memory
   - world memory
2. Add promotion/review scores rather than binary keep/drop behavior only.
3. Record why a memory item was promoted, corrected, merged, or tombstoned.
4. Make review debt visible.

### Step 2 — Strengthen teacher mode

Tasks:

1. Let a human reviewer annotate:
   - better reply
   - better memory choice
   - scene correction
   - better embodiment choice
   - success/failure label
2. Keep teacher annotations attached to episodes and runs.
3. Make teacher corrections exportable.

### Step 3 — Evolve episode schema carefully

Tasks:

1. Introduce a clearer episode schema evolution path.
2. Preserve backward compatibility or provide migration tooling.
3. Ensure each episode can include:
   - raw inputs
   - normalized scene facts
   - world-model deltas
   - selected skill/subagent
   - tools used
   - memory retrieved/written
   - final reply
   - semantic body actions
   - teacher annotations
   - benchmark labels

### Step 4 — Add dataset manifests and split hygiene

Tasks:

1. Group episodes into datasets with manifests.
2. Track train/dev/test or benchmark splits.
3. Prevent leakage between related episodes where needed.
4. Add data-quality metrics.

### Step 5 — Add privacy and redaction controls

Tasks:

1. Mark sensitive content and redaction state explicitly.
2. Support local-only exports vs research-oriented exports.
3. Keep personal assistant usage safe for later benchmarking and sharing.

### Step 6 — Make retrieval quality inspectable

Tasks:

1. Show why a memory was retrieved.
2. Show which retrieval backend was used.
3. Make memory misses inspectable.
4. Add benchmark cases for good vs bad memory retrieval.

## Suggested file targets

- `src/embodied_stack/brain/memory/` or deeper modularization
  - `policy.py`
  - `promotion.py`
  - `reviews.py`
  - `retrieval.py`
  - `redaction.py`
- `src/embodied_stack/demo/episodes/`
  - `models.py`
  - `capture.py`
  - `export.py`
  - `teacher.py`
  - `dataset_manifest.py`

## Definition of done

- memory behavior is more disciplined and reviewable
- teacher mode is a true supervision path, not a side note
- episode exports are richer and better structured
- dataset manifests and splits exist
- retrieval decisions are easier to inspect and benchmark

## Validation

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.demo.research
PYTHONPATH=src uv run python -m embodied_stack.demo.local_companion_checks
```
