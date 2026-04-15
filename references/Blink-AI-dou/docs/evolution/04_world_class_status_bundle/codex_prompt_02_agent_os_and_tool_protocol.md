Read:
- README.md
- 00_north_star_and_design_principles.md
- 02_stage1_agent_os_and_tool_protocol.md
- 08_ecosystem_reference_map.md

Then inspect the current `brain/agent_os`, `brain/tools`, orchestration, and shared contracts before editing.

Goal:
Refactor Blink-AI into a more explicit Agent Operating System with skills, hooks, subagents, typed tools, checkpoints, and traces.

Build:
1. A formal skill registry with metadata.
2. Explicit subagent roles and bounded responsibilities.
3. A lifecycle hook engine with deterministic execution points.
4. A typed internal tool protocol:
   - schema-validated inputs/outputs
   - permission/safety metadata
   - effect classification
5. Checkpoint and recovery support for runs.
6. Better trace capture and inspection for:
   - active skill
   - active subagent
   - tool calls
   - fallbacks
   - recovery transitions
7. Clear separation between:
   - session
   - run
   - skill
   - tool
   - trace
   - checkpoint
8. A small first-party skill library for key local-companion behaviors.
9. Tests and docs.

Constraints:
- Do not create framework bloat.
- Keep abstractions minimal but explicit.
- Preserve existing user-facing behavior unless the new structure intentionally improves it.
- Keep the system local-first.
- Keep body commands semantic, not raw.

Definition of done:
- Active skills are explicit and inspectable.
- Tool calls are schema-validated and typed.
- Subagent selection is visible in traces.
- Runs can be checkpointed and replayed.
- The new structure makes later work easier rather than harder.

Validation:
- uv run pytest
- inspect trace output from a real or fixture-backed local session
- verify replay/checkpoint behavior on at least one multi-step interaction

At the end, return:
- files changed
- new runtime concepts introduced
- how the tool protocol works
- how to inspect skills, hooks, and checkpoints
