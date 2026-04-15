# Stage F — Research Bridge and World-Class Evaluation v2

## Objective

Turn Blink-AI’s research bridge into something serious enough to support later planner/policy experiments without corrupting the product runtime.

## Step-by-step work order

### Step 1 — Strengthen replay determinism

Tasks:

1. Define what “strict replay” means for this repo.
2. Separate acceptable vs unacceptable divergence.
3. Record deterministic inputs explicitly:
   - normalized scene facts
   - selected tools
   - retrieved memory candidates
   - planner input envelope
   - embodiment output envelope
4. Improve replay reports so divergence is obvious.

### Step 2 — Expand planner adapter discipline

Tasks:

1. Keep the current baseline planner adapter clean.
2. Add clearer planner capability metadata.
3. Support comparison across multiple planners without changing source episodes.
4. Make scoring surfaces useful for human review.

### Step 3 — Improve research/export schemas

Tasks:

1. Evolve the research bundle carefully.
2. Keep export artifacts decomposed and inspectable.
3. Add convenience bridges for future LeRobot/Open-X-like conversion, but keep them honestly labeled as repo-native adapters until deeply validated.
4. Add explicit versioning and provenance.

### Step 4 — Build a real benchmark family

Include at least these benchmark families:

- local appliance reliability
- tool protocol integrity
- perception/world-model freshness
- social-runtime quality
- memory retrieval quality
- teacher annotation completeness
- embodiment action validity
- replay determinism
- planner comparison quality
- export/dataset hygiene

### Step 5 — Add release-style evidence packs

Tasks:

1. Every major benchmark run should emit an evidence bundle.
2. Each evidence bundle should contain:
   - run metadata
   - environment metadata
   - source episodes
   - replay outputs
   - scores
   - divergences
   - logs
3. Keep the bundle locally inspectable.

## Suggested file targets

- `src/embodied_stack/brain/planner_interface.py`
- `src/embodied_stack/demo/research.py`
- `src/embodied_stack/demo/replay_harness.py`
- `src/embodied_stack/demo/benchmarks/`
- `src/embodied_stack/shared/contracts/research.py`
- `tests/evals/`

## Definition of done

- replay divergence is easier to understand and score
- planner comparisons are cleaner and more reproducible
- research exports are better versioned and better documented
- benchmark coverage reflects product reality, not only curated demos
- evidence packs make quality claims easier to defend

## Validation

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.demo.research
PYTHONPATH=src uv run python -m embodied_stack.demo.checks
PYTHONPATH=src uv run python -m embodied_stack.demo.multimodal_checks
```
