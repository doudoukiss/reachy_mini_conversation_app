# North Star and Design Principles

## Status

This document is still current as a design-principles summary.

The authoritative product definition now lives in [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md).

The repo now largely matches this direction:

- terminal-first companion first
- deterministic shell around probabilistic reasoning
- semantic embodiment above raw hardware
- layered memory and episode exports
- replay, evidence, and benchmark discipline

## North Star

Blink-AI should become a **world-class terminal-first, local-first, character-presence companion OS with optional embodiment**.

In the current phase, the MacBook Pro is the active host for the local-first companion:

- camera = eyes
- microphone = ears
- speaker = voice
- local storage = memory substrate
- browser or native UI = operator surface
- semantic body runtime = optional future robot expression interface

The hardware body remains optional.

## Design Principles

### 1. Deterministic shell around probabilistic reasoning

Models may propose.
The runtime must decide, validate, trace, checkpoint, and degrade safely.

### 2. Terminal-first companion before operator or robot theatrics

The local Mac path must be believable, launchable, inspectable, and recoverable before broader operator tooling or robot-stack ambition matters.

### 3. Semantic embodiment above raw hardware

The brain should think in:

- `look_at_user`
- `listen_attentively`
- `friendly`
- `nod_small`
- `safe_idle`

It should not think in servo ids, baud rates, or register bytes.

### 4. Memory is architecture

Memory is not just extra prompt context.
Blink-AI should keep distinct policy and evidence around:

- profile memory
- episodic memory
- semantic memory
- world-state memory

### 5. Every meaningful interaction is a reusable artifact

The repo should keep producing inspectable local evidence:

- traces
- checkpoints
- world-model transitions
- episodes
- benchmark artifacts
- research bundles

### 6. Evaluation before hype

Claims should stay grounded in:

- replay
- benchmark runs
- artifact exports
- operator-visible runtime state
- passing tests

### 7. Local-first, cloud-optional

Cloud paths can improve quality, but the local system should remain real without them.

### 8. Future research bridge without current research bloat

The runtime should be ready for future learned policies and dataset export, but the current repo should stay product-usable and maintainable.

## What still matters most

- keep product usability ahead of speculative research work
- keep safety and degraded behavior visible
- keep the body boundary clean for future hardware return
- keep docs aligned with the actual implemented baseline
