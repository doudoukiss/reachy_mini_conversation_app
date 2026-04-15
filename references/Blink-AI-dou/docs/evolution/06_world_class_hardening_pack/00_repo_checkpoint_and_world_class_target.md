# Repo Checkpoint and World-Class Target

## 1. What the current repository already does well

The newest Blink-AI checkpoint already has a strong foundation:

- desktop-first local runtime
- browser-first appliance entrypoint plus local companion loop
- explicit Agent OS concepts: runs, checkpoints, skills, subagents, typed tools
- multimodal perception abstractions and world-model state
- layered memory and episode export
- semantic embodiment and a serial landing zone
- research bundle, replay, and benchmark beginnings

That means the project is **not** blocked on architecture invention.
The next work is mostly about **hardening, simplification, and making the good architecture unavoidable**.

## 2. What is still weak or risky

### A. Green-baseline discipline is not strong enough yet

A current pytest run stops on a readiness test failure. That is a warning sign:

- the codebase is large enough that “mostly working” is no longer good enough
- readiness/capability semantics are still too easy to drift
- world-class systems need a boring, trustworthy baseline

### B. Large files still blur ownership

Priority files to split and simplify include:

- `src/embodied_stack/desktop/devices.py`
- `src/embodied_stack/brain/operator_console.py`
- `src/embodied_stack/demo/episodes.py`
- `src/embodied_stack/brain/perception.py`
- `src/embodied_stack/brain/agent_os/tools.py`
- `src/embodied_stack/brain/tools.py`
- `src/embodied_stack/brain/grounded_memory.py`

### C. Persistence and observability are not yet world-class

Current local JSON/file-backed persistence is acceptable for this phase, but it needs:

- atomic write semantics
- corruption recovery everywhere, not only in selected stores
- explicit single-writer assumptions
- retention/backup policy
- structured logging and event correlation

### D. Readiness and capability reporting need a cleaner contract

The current repo appears to conflate:

- service aliveness
- local usability through fallback
- full media/device availability
- “best experience” availability

Those are different concepts and must be represented separately.

### E. Research/eval is present but not yet strict enough

The project already exports episodes and replay bundles, but strict replay determinism, dataset hygiene, and comparison scoring are still honest active-work areas.

### F. Live embodiment remains intentionally gated

That is correct.
Do not weaken this rule.
The body path should advance through:

- semantic compiler quality
- fixture parity
- transport health
- calibration discipline
- powered-hardware bring-up only when safety conditions are real

## 3. What “world-class” should mean for this exact project

Blink-AI should become:

## A world-class local embodied companion OS that can later inhabit a robot body without redesigning the brain.

That means the system should be able to:

1. launch locally with one boring command
2. see, hear, speak, remember, and act through typed tools
3. explain its own capability state and degraded reasons
4. maintain high-quality traces, checkpoints, and evidence
5. produce reusable episodes and benchmark artifacts from real usage
6. emit semantic embodiment commands that can drive virtual or real hardware later
7. support research attachment points without becoming research-only software

## 4. Architecture invariants

Do not violate these during implementation:

1. Keep the Mac/local runtime as the current product center of gravity.
2. Keep the body optional.
3. Keep raw servo protocol below the semantic body layer.
4. Keep the deterministic shell around probabilistic reasoning.
5. Keep tool contracts typed, logged, and versioned.
6. Keep every major behavior measurable and replayable.
7. Keep local-first behavior strong; cloud must remain optional.

## 5. Strategic sequencing

The correct sequence from this repo state is:

1. platform hardening and consolidation
2. Agent OS / ACI hardening
3. perception + social-runtime quality
4. memory + teacher + dataset flywheel quality
5. embodiment + deployment spine hardening
6. research bridge + world-class eval hardening

This order matters.
Do not start with live-hardware work or frontier-model experiments while Stage A is still unstable.
