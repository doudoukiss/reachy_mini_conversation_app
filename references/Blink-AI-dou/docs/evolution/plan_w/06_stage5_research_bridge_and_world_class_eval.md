# Stage 5 — Research Bridge and World-Class Evaluation

## Status

Baseline implemented, but this stage still has the largest meaningful remaining gap.

The repo now has:

- a planner adapter boundary
- a deterministic baseline comparison planner
- episode replay artifacts under `runtime/replays/`
- derived `blink_research_bundle/v1` exports
- benchmark families for export validity, planner swap compatibility, replay determinism, annotation completeness, and dataset split hygiene

## What landed

- orchestration now depends on a planner adapter boundary rather than directly on one planner implementation
- exported episodes can be replayed against registered planners without mutating the source episode bundle
- research bundle export decomposes observations, planner IO, tool traces, memory actions, labels, and split metadata into separate artifacts
- benchmark runs can score source episodes, replay runs, and episode-vs-replay comparisons through one benchmark surface
- operator APIs and CLI entrypoints now expose planner listing, replay launching, replay lookup, and research export

## Remaining hardening work

- strict replay determinism is not solved yet; current strict-mode replays are inspectable but can still diverge structurally
- the deterministic baseline planner is useful for comparison, but still intentionally simple
- research adapters such as `lerobot_like` are convenience exports, not deeply validated canonical interchange formats
- benchmark scoring should keep improving so replay divergence and dataset-quality signals become more decision-useful

## Maintained acceptance truth

Stage 5 should be read honestly:

- the bridge exists
- the export and replay surfaces exist
- future research work can attach without redesigning the runtime
- but determinism hardening and richer replay fidelity remain active work, not solved problems
