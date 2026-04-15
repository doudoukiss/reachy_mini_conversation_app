# Codex AVP prompt 00 — master instructions

You are implementing the robot-brain refactor for `reachy_mini_conversation_app`.

Before writing code, read these documents in order:

1. `docs/robot_brain/reachy_to_robot_brain_assessment.md`
2. `docs/robot_brain/target_architecture.md`
3. `docs/robot_brain/capability_contract.md`
4. `docs/robot_brain/mock_first_implementation_plan.md`

## Mission

Refactor the app so it becomes a clean robot-brain shell with:

- robot-agnostic semantic action contracts
- a mock-first adapter
- a Reachy compatibility adapter
- a future embodied-stack/Jushen adapter
- semantic tools instead of direct robot-specific commands

## Non-negotiable constraints

- Do not require physical hardware during development.
- Do not move raw serial, servo, or calibration ownership into this repo.
- Do not remove the existing Reachy path in the first implementation pass.
- Keep changes incremental and testable.
- Prefer compatibility shims over flag-day rewrites.
- Do not expose raw joint counts, servo IDs, or transport details to the LLM.
- New action behavior must be implemented in mock mode first.

## Deliverable style

For each implementation pass:

1. make the smallest coherent set of code changes
2. add or update tests
3. run tests
4. summarize what changed, what remains, and any tradeoffs

Follow the remaining Codex prompts in numeric order.
