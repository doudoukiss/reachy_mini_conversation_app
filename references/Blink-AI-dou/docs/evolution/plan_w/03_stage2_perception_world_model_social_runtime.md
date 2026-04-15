# Stage 2 — Continuous Perception, World Model, and Social Runtime

## Status

Baseline implemented.

The repo now has:

- watcher versus semantic perception tiers
- rolling scene-observer event state
- normalized scene facts before world-model storage
- richer world-model freshness, provenance, and uncertainty
- explicit `social_runtime_mode`

## What landed

- continuous cheap watcher signals for presence, engagement, and refresh recommendation
- triggered semantic refresh rather than expensive analysis every turn
- normalized scene facts flowing into the world model and operator surfaces
- explicit social-runtime and attention policy surfaces
- operator snapshot visibility for scene freshness, refresh reason, uncertainty, and limited-awareness state

## Remaining hardening work

- improve live watcher heuristics and threshold tuning on real local usage rather than only fixture-driven flows
- keep stale semantic facts from leaking into grounded behavior as new features are added
- continue tightening the boundary between watcher-derived policy signals and true semantic grounding claims
- keep social behavior explicit in policy/state instead of re-embedding it into prompt-only logic

## Maintained acceptance truth

Stage 2 should now be treated as a continuous-behavior quality stage:

- the perception/world-model split exists
- the social runtime exists
- future work is better grounding quality, better freshness discipline, and better live behavior tuning
