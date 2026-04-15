Read:
- README.md
- 00_north_star_and_design_principles.md
- 04_stage3_memory_episode_flywheel_teacher_mode.md
- 08_ecosystem_reference_map.md

Then inspect current memory, grounded memory, demo/export, and operator-console code.

Goal:
Turn Blink-AI’s memory and export path into a serious flywheel: layered memory, structured episodes, teacher-mode feedback, and benchmark coverage.

Build:
1. Explicit memory layers:
   - profile
   - episodic
   - semantic
   - world
2. Memory policies:
   - write policy
   - promotion policy
   - correction/deletion path
   - provenance visibility
3. A standardized episode schema for real local sessions and replayed runs.
4. Teacher mode:
   - mark reply good/bad
   - correct scene interpretation
   - annotate memory importance
   - annotate body behavior quality
   - mark session outcome
5. Better benchmark/eval coverage across:
   - memory
   - scene grounding
   - proactive behavior
   - degraded behavior
   - body-expression alignment
6. Docs and tests.

Constraints:
- Do not reduce memory to one big vector store.
- Keep export artifacts inspectable and versioned.
- Keep the system useful for daily use, not just research export.
- Preserve privacy-aware local-first behavior.

Definition of done:
- Memory layers are explicit and inspectable.
- Important sessions export into useful episodes.
- Teacher annotations are attached to episodes.
- Benchmarks cover product behavior, not just API shape.

Validation:
- uv run pytest
- run a real or fixture-backed session
- export an episode and inspect its structure
- verify teacher annotations persist and appear in the exported artifact

At the end, return:
- files changed
- new schemas introduced
- how memory layering works
- how teacher mode is used
