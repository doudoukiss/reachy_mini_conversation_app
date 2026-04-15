# Stage 1 — Agent OS and Tool Protocol

## Status

Baseline implemented.

The repo now has:

- explicit Agent OS runs and checkpoints
- skill metadata and registered first-party skills
- bounded subagents
- typed internal tool protocol
- hook execution records
- operator-visible run and checkpoint APIs

## What landed

- `Run`, `Checkpoint`, `Skill`, `Subagent`, and typed tool concepts are first-class
- traces expose active skill, active subagent, typed tool calls, validation outcomes, failure state, and fallback reason
- effectful/operator-sensitive tools are checkpoint-aware
- tool metadata carries version, family, permission, latency, and effect classification
- planner/runtime behavior is inspectable through operator APIs and exported artifacts

## Remaining hardening work

- checkpoint resume is still replay-shaped in practice rather than a true mid-turn continuation from serialized execution state
- keep reducing compatibility shims and legacy naming now that the structured runtime path is established
- continue hardening tool allowlist discipline and recovery behavior across less-common degraded paths
- avoid new product logic that bypasses the structured Agent OS path

## Maintained acceptance truth

Stage 1 is no longer about inventing Agent OS primitives.
It is about keeping them coherent and enforced:

- every meaningful turn should keep flowing through the explicit runtime
- traces should stay readable and trustworthy
- future planner work should build on this boundary rather than around it
