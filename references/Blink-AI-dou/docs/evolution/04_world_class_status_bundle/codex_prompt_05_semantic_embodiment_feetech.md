Read:
- README.md
- 00_north_star_and_design_principles.md
- 05_stage4_semantic_embodiment_and_feetech_bridge.md
- 08_ecosystem_reference_map.md

Then inspect the current body package, compiler, profile, calibration, and serial modules before editing.

Goal:
Complete Blink-AI’s semantic embodiment layer and prepare the Feetech bridge so the intelligence stack is future-proof when the servo board and power path return.

Build:
1. A richer semantic body action catalog.
2. A cleaner expression/gesture/animation library.
3. Better virtual-body preview coverage for semantic actions.
4. Stronger body compilation:
   - semantic action -> calibrated motor intents
   - bounds checking
   - coupled axis handling
   - safe idle and recovery
5. Better calibration tooling and profile persistence.
6. A stronger Feetech serial driver surface:
   - protocol encode/decode
   - dry-run
   - fixture replay
   - live serial abstraction
   - sync write/read support
   - health/state polling
7. A bring-up/inspection tool for future hardware return.
8. Tests and docs.

Constraints:
- Do not let the planner access raw servo protocol details.
- Keep virtual and live modes behind the same interface.
- Keep safety and bounded motion central.
- The current no-power phase must remain productive through virtual and dry-run modes.

Definition of done:
- Semantic actions are rich enough for expressive social behavior.
- Virtual-body preview is a serious development target, not an afterthought.
- Serial paths are prepared without forcing live hardware.
- Calibration and safety are explicit and testable.

Validation:
- uv run pytest
- exercise the virtual body with semantic actions
- run dry-run or fixture-based serial tests
- inspect emitted motor intents for range and coupling correctness

At the end, return:
- files changed
- new semantic action families
- serial/bring-up capabilities added
- how safety is enforced
