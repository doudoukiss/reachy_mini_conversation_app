# Robot-brain migration bundle

This bundle is meant to be copied into the root of `reachy_mini_conversation_app`.

## Included files

- `docs/robot_brain/reachy_to_robot_brain_assessment.md`
  - feasibility, reusable pieces, unsuitable pieces, missing capabilities, and major risks
- `docs/robot_brain/target_architecture.md`
  - target system design, boundaries, data contracts, flow diagrams, and package layout
- `docs/robot_brain/capability_contract.md`
  - proposed capability/action/result contracts for mock mode and live body integration
- `docs/robot_brain/mock_first_implementation_plan.md`
  - phase-by-phase implementation and validation sequence
- `docs/robot_brain/codex_avp/00_master_prompt.md`
- `docs/robot_brain/codex_avp/01_domain_and_mock_runtime.md`
- `docs/robot_brain/codex_avp/02_reachy_adapter_refactor.md`
- `docs/robot_brain/codex_avp/03_semantic_tools_and_profiles.md`
- `docs/robot_brain/codex_avp/04_embodied_stack_jushen_adapter.md`
- `docs/robot_brain/codex_avp/05_dialogue_orchestrator_and_hardening.md`

## Recommended reading order

1. `reachy_to_robot_brain_assessment.md`
2. `target_architecture.md`
3. `capability_contract.md`
4. `mock_first_implementation_plan.md`
5. Codex AVP prompts in numeric order

## Intended implementation stance

Treat the current app as a conversation and interaction shell.
Do **not** turn it into a raw serial or servo owner.
Keep the real hardware runtime behind a semantic adapter boundary.
