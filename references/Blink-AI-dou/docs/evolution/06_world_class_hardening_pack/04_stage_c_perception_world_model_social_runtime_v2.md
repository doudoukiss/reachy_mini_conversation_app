# Stage C — Perception, World Model, and Social Runtime v2

## Objective

Make Blink-AI’s intelligence feel **situated and socially grounded**, not merely conversational.

## Step-by-step work order

### Step 1 — Split watcher and semantic runtime clearly

Tasks:

1. Separate cheap continuous watcher logic from heavier semantic analysis.
2. Define explicit watcher outputs:
   - presence
   - motion / new entrant
   - probable attention target
   - likely engagement shift
   - refresh recommendation
3. Define explicit semantic outputs:
   - scene facts
   - visible objects/anchors
   - visible text
   - participant attributes only when justified
   - uncertainty and provenance

### Step 2 — Add stronger freshness and claim discipline

Tasks:

1. Every world fact should carry:
   - timestamp
   - provenance
   - freshness TTL
   - confidence or quality class
2. Prevent stale semantic claims from silently leaking into later turns.
3. Distinguish:
   - watcher hint
   - semantic observation
   - operator annotation
   - memory-derived assumption

### Step 3 — Harden participant and attention policy

Tasks:

1. Improve participant routing for multi-person settings.
2. Keep a stable current speaker hypothesis.
3. Improve attention-target logic.
4. Make greet suppression and re-engagement policy more explicit.
5. Handle disengagement and interruption cleanly.

### Step 4 — Upgrade the social runtime from heuristics to policy modules

Tasks:

1. Split social policy into explicit modules such as:
   - greeting policy
   - interruption policy
   - disengagement policy
   - escalation policy
   - attract-mode policy
2. Keep the policies deterministic where possible.
3. Keep model reasoning focused on content, not policy bookkeeping.

### Step 5 — Improve scene-grounded dialogue

Tasks:

1. Ensure dialogue consumes normalized world-model facts rather than raw camera output.
2. Make grounded references inspectable.
3. Keep honest limited-awareness fallback when perception quality is weak.

### Step 6 — Expand benchmark and replay coverage

Add fixtures and benchmark scenarios for:

- approach and greeting
- two-person attention handoff
- disengagement shortening
- scene-grounded comment
- uncertainty admission
- stale-scene suppression
- operator correction after a wrong scene interpretation

## Suggested file targets

- `src/embodied_stack/brain/perception/`
  - `watcher.py`
  - `semantic_refresh.py`
  - `scene_facts.py`
  - `freshness.py`
  - `uncertainty.py`
- `src/embodied_stack/brain/social/`
  - `greeting_policy.py`
  - `attention_policy.py`
  - `disengagement_policy.py`
  - `escalation_policy.py`
- `src/embodied_stack/brain/world_model/` if modularized further

## Definition of done

- watcher and semantic layers are clearly separated
- world-model facts carry provenance and freshness discipline
- social behavior is explicit and testable
- Blink-AI feels more aware and less like a chat wrapper
- benchmark coverage expands to real social-runtime edge cases

## Validation

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.demo.multimodal_checks
PYTHONPATH=src uv run python -m embodied_stack.demo.checks
```
