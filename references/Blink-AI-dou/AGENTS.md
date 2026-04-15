# AGENTS.md

## Project overview

This repository is for a **terminal-first, local-first, character-presence companion OS with optional embodiment** built around:

- a **MacBook Pro / Mac-class desktop runtime** that currently runs the active AI and application logic
- a **Mac Studio** as the intended later higher-capacity host when needed
- a **Jetson Nano** on the optional robot body that handles simple on-device tasks, device I/O, and safety
- a **simulation-first workflow** so most product work can happen before hardware arrives

The current program goal is to turn Blink-AI into a **world-class local-first companion with character presence and optional embodiment** that already behaves like the brain of a future robot even when the body is absent.

The primary product is the AI presence living in the computer. The default product surface is the terminal-first local companion running on the Mac. The browser console, Action Center, and robot body remain supporting surfaces around that core loop.

Use [north_star.md](/Users/sonics/project/Blink-AI/docs/north_star.md) as the product-definition tie-breaker when docs drift.

An explicit near-term vertical mode and commercially believable proof point remains a **community concierge / guide deployment mode**, optionally embodied through the robot head.

## Non-negotiable architecture rules

1. **Preserve the split**
   - Desktop/Mac brain = language, memory, planning, knowledge, operator tooling, demo logic, and the default current embodiment runtime.
   - Jetson edge = future remote device drivers, sensor capture, actuator control, heartbeat, command ack, safety fallback.

2. **Do not hard-code business logic into the edge**
   - Edge code should be simple and deterministic.
   - High-level intelligence belongs in the brain.

3. **Use shared contracts**
   - Message schemas live in `src/embodied_stack/shared/`.
   - If a protocol changes, update `docs/protocol.md` and tests.

4. **Assume hardware is not present**
   - New features must be testable with the fake robot / simulated edge unless the task explicitly says otherwise.

5. **Safety beats cleverness**
   - Unsafe motion or unsupported movement commands must be rejected or degraded safely.
   - Network loss should always have a safe idle fallback.

6. **Investor demos must be honest**
   - Do not claim capabilities the code does not implement.
   - Make demos deterministic, polished, and observable.

7. **Deterministic shell around probabilistic reasoning**
   - Models may propose.
   - The runtime must select, validate, trace, checkpoint, and recover.

## What success looks like

When making changes, optimize for these outcomes:

- a strong terminal-first, local-first companion loop on the Mac
- a coherent character presence runtime built on a clear fast loop / slow loop split
- a believable investor demo
- a clean path from fake robot to real robot
- reusable software and data assets
- measurable evaluation and logging
- community use cases that sound commercially real

## Coding guidance

- Python 3.11+
- Prefer clear, boring code over clever abstractions.
- Keep modules small and composable.
- Add docstrings when the interface is not obvious.
- Use `pydantic` models for shared contracts.
- Add tests for protocol, safety, and API behavior.
- Avoid adding heavyweight infra unless it materially improves the roadmap.

## Repo structure

- `docs/` = product, architecture, demo, protocol
- `docs/evolution/` = preserved historical plans and design checkpoints
- `codex_prompts/` = large prompts for Codex
- `.agents/skills/` = reusable repo-local Codex skills
- `src/embodied_stack/brain/` = Mac-side runtime
- `src/embodied_stack/desktop/` = default local runtime entrypoint
- `src/embodied_stack/body/` = semantic embodiment and body-driver layer
- `src/embodied_stack/edge/` = optional Jetson-side or tethered runtime
- `src/embodied_stack/sim/` = fake robot and scenario runner
- `src/embodied_stack/shared/` = contracts and common types
- `tests/` = automated tests

## Validation commands

Run these after meaningful changes:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

If you add endpoints or services, also verify they still import cleanly.

## Change management rules

If you change any of these, update the related docs:

- shared protocol -> `docs/protocol.md`
- architecture split -> `docs/architecture.md`
- investor flow -> `docs/investor_demo.md`
- current direction / milestone sequencing -> `docs/current_direction.md` and `PLAN.md`

## Demo quality rules

For any demo-facing feature:

- include visible status / logs
- include a graceful fallback path
- make the scenario replayable
- avoid hidden manual steps when possible
- log the final outcome so it is obvious what succeeded

## Current priority order

1. Desktop companion quality and reliability
2. Character presence runtime
3. Agent OS and tool protocol hardening
4. Perception, world model, and social runtime
5. Memory, episode flywheel, and teacher mode
6. Semantic embodiment and Feetech bridge hardening
7. Research bridge, evals, and long-term embodiment transfer

## When uncertain

Default to whatever best supports:

- pre-hardware progress
- investor credibility
- future migration onto real robot hardware
