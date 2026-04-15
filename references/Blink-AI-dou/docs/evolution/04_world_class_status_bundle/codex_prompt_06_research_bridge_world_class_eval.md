Read:
- README.md
- 00_north_star_and_design_principles.md
- 06_stage5_research_bridge_and_world_class_eval.md
- 07_repo_change_map_and_execution_order.md
- 08_ecosystem_reference_map.md

Then inspect export, replay, demo, benchmark, and orchestration boundaries before editing.

Goal:
Make Blink-AI ready for serious long-term evolution: planner-swappable, replayable, benchmarked, and able to export research-friendly data without losing product focus.

Build:
1. A clean planner/plugin interface.
2. Episode replay against alternative planners.
3. Stable, versioned export artifacts suitable for future robotics/agent research workflows.
4. A benchmark matrix covering:
   - product reliability
   - local appliance quality
   - memory quality
   - scene grounding
   - social timing
   - embodiment validity
   - replay determinism
5. Scripts and docs for running the benchmark matrix.
6. Clear boundaries for future integrations like LeRobot-like export or learned-policy experiments.

Constraints:
- Do not turn the repo into a research toy at the expense of product usability.
- Keep current local companion flows intact.
- Preserve local-first operation.
- Prefer replayable and inspectable infrastructure over speculative training code.

Definition of done:
- Planners are swappable behind a stable interface.
- Exported episodes are stable and versioned.
- Benchmark coverage is meaningfully broader and more serious.
- Future research work can attach without redesigning the runtime.

Validation:
- uv run pytest
- run replay against at least two planner configurations
- generate benchmark artifacts
- inspect export versioning and schema stability

At the end, return:
- files changed
- planner interface design
- new benchmark coverage
- future research attachment points
