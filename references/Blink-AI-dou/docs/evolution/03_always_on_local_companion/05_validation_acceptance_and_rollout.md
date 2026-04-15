# 05 — Validation, Acceptance, and Rollout

## Validation philosophy

This milestone should be validated as a **real local product loop**, not just as unit-tested plumbing.

You want to prove that Blink-AI can operate as a local multimodal companion on the M4 Pro machine.

## Required validation layers

### 1. Unit and component tests

Cover:

- Ollama profile resolution
- runtime backend status and fallbacks
- continuous voice state transitions
- interruption / cancel behavior
- scene observer event generation
- trigger engine decisions
- memory promotion and retrieval
- bodyless / virtual-body continuity

### 2. Deterministic replay tests

Add fixtures for:

- person enters view, then user says hello
- user asks a visual question
- user interrupts a reply
- reminder becomes due while user is idle
- scene changes but user does not want interruption
- local model temporarily unavailable

### 3. Live local smoke tests

A human should be able to verify:

- microphone capture works
- camera capture works
- speaker output works
- Blink-AI can answer naturally with local models
- Blink-AI can remain silent when it should
- Blink-AI can proactively speak in bounded, non-annoying ways

## Acceptance criteria for the milestone

### A. Local model integration

- `qwen3.5:9b` and `embeddinggemma:300m` are first-class supported local defaults
- operator/runtime status clearly reports local model health
- failures degrade honestly

### B. Continuous local interaction

- Blink-AI can run a continuous local loop without the browser being required
- interruption and cancel work visibly
- typed fallback remains available

### C. Scene awareness

- the system tracks scene freshness and presence continuously
- heavy scene analysis is invoked only when justified
- scene-grounded answers stay honest

### D. Proactive behavior

- Blink-AI can greet or remind when appropriate
- Blink-AI respects cooldowns and suppression rules
- proactive behavior is logged and reviewable

### E. Memory quality

- a useful personal fact can be remembered and retrieved later
- a session can be summarized and used in later turns
- retrieval provenance stays inspectable

## Suggested commands to keep working

Use the repo’s existing validation culture and extend it.

Current baseline commands should continue to pass:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.demo.local_companion_checks
PYTHONPATH=src uv run python -m embodied_stack.demo.multimodal_checks
```

Add new milestone commands such as:

```bash
PYTHONPATH=src uv run python -m embodied_stack.demo.always_on_local_checks
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli companion --no-export
PYTHONPATH=src uv run python -m embodied_stack.desktop.cli story --story-name local_companion_story
```

## Metrics worth recording

- time to transcript
- time to first audible reply
- interruption latency
- scene-refresh latency
- proactive-trigger precision
- false-positive proactive rate
- memory retrieval hit rate
- fallback rate
- model cold-start vs warm-start latency

## Rollout order

1. get the canonical local model profile stable
2. get continuous voice stable
3. get scene observer stable
4. add proactive trigger engine
5. add daily-use polish and evidence packs

## Definition of done

Blink-AI should feel like a coherent local companion system, not like a set of disconnected robotics demos.
