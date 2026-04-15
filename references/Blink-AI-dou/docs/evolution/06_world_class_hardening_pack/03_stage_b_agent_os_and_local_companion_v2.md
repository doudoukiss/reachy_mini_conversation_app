# Stage B — Agent OS and Local Companion v2

## Objective

Upgrade the current runtime from “explicit agent plumbing exists” to a **truly disciplined Agent OS** that can support a world-class local assistant.

## Step-by-step work order

### Step 1 — Formalize the Agent-Computer Interface (ACI)

Treat Blink-AI’s environment as a typed operating surface.

The ACI should explicitly include:

- camera capture
- microphone input
- speech output
- memory read/write
- local files
- browser tasks
- operator status
- system health
- semantic body preview/command

Tasks:

1. Make tool envelopes stable and versioned.
2. Add permission/effect metadata to every effectful tool.
3. Normalize tool results so they always carry:
   - status
   - confidence if applicable
   - provenance
   - fallback_used
   - latency
   - error details
4. Ensure all effectful behavior flows through this ACI rather than ad hoc helper calls.

### Step 2 — Strengthen run/checkpoint lifecycle

Tasks:

1. Define a stricter run state machine.
2. Add explicit pause/resume/abort semantics.
3. Distinguish between:
   - turn-level checkpoint
   - tool-level checkpoint
   - conversation/session state
4. Make mid-run recovery behavior inspectable.

### Step 3 — Turn skills into real playbooks

Tasks:

1. Promote skill definitions from loose metadata toward reusable, inspectable playbooks.
2. Keep each skill bounded and named clearly.
3. Suggested first-class skills:
   - `general_companion_conversation`
   - `observe_and_comment`
   - `memory_followup`
   - `daily_planning`
   - `community_concierge`
   - `incident_escalation`
   - `safe_degraded_response`
4. Ensure skill selection is visible in traces and operator UI.

### Step 4 — Harden subagents and hooks

Tasks:

1. Keep subagents bounded and role-specific.
2. Suggested subagents:
   - `perception_analyst`
   - `dialogue_planner`
   - `memory_curator`
   - `safety_reviewer`
   - `tool_result_summarizer`
3. Make hooks deterministic and auditable:
   - `after_perception`
   - `before_reply`
   - `before_speak`
   - `after_turn`
   - `on_failure`
   - `before_memory_write`
4. Avoid arbitrary nested-agent sprawl.

### Step 5 — Make the local companion genuinely useful

Tasks:

1. Improve the always-on local companion loop.
2. Support practical daily flows:
   - ask/respond conversation
   - observe current scene
   - remind and follow up later
   - search memory
   - consult local files or calendars when available
3. Keep proactive behavior bounded and user-respectful.
4. Make trigger decisions visible.

### Step 6 — Improve operator and trace surfaces

Tasks:

1. Show active skill, subagent, and tool chain in the operator console.
2. Show why a fallback happened.
3. Show which capability was unavailable vs intentionally not used.
4. Make runs and checkpoints easy to inspect and export.

## Suggested file targets

- `src/embodied_stack/brain/agent_os/`
  - `runtime.py`
  - `registry.py`
  - `lifecycle.py`
  - `hooks.py`
  - `permissions.py`
  - `checkpointing.py`
- `src/embodied_stack/brain/skill_library/`
  - stronger skill package layout
- `src/embodied_stack/brain/aci/` or equivalent
  - typed tool/result wrappers

## Definition of done

- ACI/tool boundaries are clearer and more uniform
- skills and subagents are easier to inspect and maintain
- run/checkpoint recovery is more explicit
- the local companion is more useful as a daily assistant
- operator traces tell a clear story about decisions, tools, and fallback

## Validation

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.demo.local_companion_checks
PYTHONPATH=src uv run python -m embodied_stack.demo.continuous_local_checks
```
