Read README.md, docs/current_direction.md, docs/development_guide.md, src/embodied_stack/backends/, src/embodied_stack/desktop/profiles.py, src/embodied_stack/backends/profiles.py, src/embodied_stack/backends/router.py, and local companion CLI/runtime files first.

Then make Blink-AI's flagship product path a low-latency hybrid companion runtime instead of assuming one heavy local model is always the best default.

What to do:
1. Introduce a new default-oriented profile such as `companion_live` or an equivalent clearly named profile.
2. Make this profile optimize for fluid conversation, not maximum locality.
3. Keep local memory, orchestration, and product logic local.
4. Preserve `m4_pro_companion`, `local_balanced`, `local_fast`, and `offline_safe` as meaningful alternatives.
5. Expose latency telemetry for:
   - STT
   - reasoning
   - TTS start
   - end-to-end turn time
   - model cold start vs warm start if practical
6. Improve model residency management for Ollama-backed local profiles.
7. Make heavy vision use selective rather than default for every turn.
8. Update docs to explain when to use each profile.

Constraints:
- Do not remove local-only operation.
- Do not hardcode a single cloud vendor into unrelated layers.
- Keep routing deterministic and inspectable.
- Prefer a small number of clear profiles over many overlapping ones.

Definition of done:
- There is an explicit default-friendly companion profile optimized for real conversation.
- Users can understand which profile is for daily companion use.
- Local-only remains available and clearly described.
- Latency is inspectable.

Validation:
- uv run pytest
- focused local companion checks if present
- any new telemetry or status output should be visible in runtime status APIs or CLI

At the end, return:
- profiles added or changed
- default recommendation
- latency signals now available
- remaining bottlenecks
