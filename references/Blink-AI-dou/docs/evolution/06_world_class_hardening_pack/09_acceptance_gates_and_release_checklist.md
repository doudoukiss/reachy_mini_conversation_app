# Acceptance Gates and Release Checklist

Use this file as the hard gate before calling a stage “done.”

## Gate 0 — Engineering baseline

Must be true first:

- `uv run pytest` passes
- dry-run scenario path passes
- no known startup-blocking artifact corruption bug remains
- readiness and capability reporting are honest

## Gate 1 — Local appliance quality

Must be true:

- `uv run blink-appliance` works from a clean repo setup
- typed fallback remains usable
- device selection and permission problems are inspectable
- operator console clearly shows mode, fallback, and capability state

## Gate 2 — Agent OS discipline

Must be true:

- effectful behavior flows through typed tools
- skills, subagents, and hooks are visible in traces
- runs and checkpoints are inspectable and recoverable at defined boundaries

## Gate 3 — Situated intelligence quality

Must be true:

- watcher and semantic perception are clearly separated
- world facts carry freshness and provenance
- social-policy behavior is explicit and benchmarked
- uncertainty is admitted honestly

## Gate 4 — Memory and dataset flywheel quality

Must be true:

- memory policy is explicit
- teacher review is real and exportable
- episode bundles are reusable
- dataset manifests and split hygiene exist

## Gate 5 — Embodiment quality

Must be true before claiming body readiness:

- semantic embodiment compiler is stable
- virtual and dry-run parity is strong
- live serial health reporting is explicit
- calibration workflow is gated and safe

## Gate 6 — Research/eval credibility

Must be true before making strong quality claims:

- replay divergence is measurable
- benchmark pack covers real product behavior
- research bundles are versioned and reproducible enough to inspect
- quality claims can be defended with artifacts

## Release checklist for every major milestone

1. update `README.md` if product surface changed
2. update `PLAN.md` and `docs/current_direction.md` if milestone sequencing changed
3. update `docs/architecture.md` if boundaries changed
4. update `docs/protocol.md` if contracts changed
5. run validation commands
6. capture at least one evidence bundle for the milestone
7. confirm degraded paths still tell the truth
