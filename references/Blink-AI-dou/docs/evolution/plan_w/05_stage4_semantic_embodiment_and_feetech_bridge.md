# Stage 4 — Semantic Embodiment and Feetech Bridge

## Status

Baseline implemented.

The repo now has:

- canonical semantic body names with compatibility aliases
- richer semantic compiler and virtual preview
- calibration v2 records
- serial dry-run and fixture-replay parity
- serial health and command-outcome reporting

## What landed

- semantic registry for expression, gaze, gesture, animation, and safety actions
- planner-facing semantic commands kept above raw servo details
- body preview and body command tooling with canonical-name reporting
- calibration workflow centered on `uv run body-calibration`
- serial driver/health surfaces that keep dry-run, fixture, and live lanes behind one boundary

## Remaining hardening work

- live serial bring-up on powered hardware remains a gated follow-up, not a completed baseline
- calibration quality still needs real-hardware validation beyond templates and dry-run fixtures
- continue tightening operator-visible health reporting during actual live serial faults
- preserve semantic/body boundary discipline as future hardware work resumes

## Maintained acceptance truth

Stage 4 should now be read as:

- semantic embodiment boundary complete enough for product work
- live hardware validation still intentionally gated
- future servo-board return should extend the body package, not re-open brain architecture
