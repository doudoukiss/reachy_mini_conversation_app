Read `AGENTS.md`, `README.md`, `PLAN.md`, `docs/current_direction.md`, `docs/architecture.md`, and all Stage 6A–6D code first.

Then implement **Stage 6E — Action Episode Flywheel and Evaluation**.

## Project context

The repo already has strong replay/eval infrastructure for perception, dialogue, embodiment, and research export.
Stage 6 must extend that discipline to effectful work.

## What to build

1. Add an action-bundle export format, preferably as a sidecar bundle rather than a breaking redesign of existing episode bundles.
2. Link action bundles to existing episode exports where relevant.
3. Add replay support for action bundles against:
   - stub connectors
   - dry-run connectors
   - deterministic browser fixtures
4. Add eval suites for:
   - approval correctness
   - workflow resume correctness
   - connector safety policy
   - browser artifact completeness
   - action trace completeness
   - proactive restraint
5. Add teacher/reviewer annotations for action quality.
6. Extend the research bridge carefully so action runs can be replayed and compared without mutating source evidence.
7. Add tests for:
   - bundle schema validity
   - replay determinism on fixtures
   - eval scoring
   - annotation persistence
   - bundle/episode linkage

## Constraints

- Preserve existing episode and research surfaces as much as possible.
- Prefer additive exports over premature breaking schema changes.
- Keep action evidence human-readable and machine-usable.

## Definition of done

- Action runs produce durable export bundles.
- Action bundles can be replayed and scored.
- Teachers can annotate action quality.
- Tests pass.

## Validation

Run:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

At the end, return:
- files changed
- bundle formats added or extended
- replay/eval capabilities
- teacher annotation path
- remaining research gaps
