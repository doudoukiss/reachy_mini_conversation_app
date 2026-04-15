Read:
- README.md
- 00_north_star_and_design_principles.md
- 03_stage2_perception_world_model_social_runtime.md
- 08_ecosystem_reference_map.md

Then inspect the current perception, world-model, executive, desktop runtime, and multimodal modules.

Goal:
Upgrade Blink-AI into a continuously perceiving, socially aware local embodied runtime.

Build:
1. A two-tier perception pipeline:
   - cheap continuous observer
   - triggered richer scene analysis
2. A structured perception event stream.
3. Better world-model storage for:
   - participants
   - attention target
   - engagement
   - anchors
   - visible text
   - freshness/confidence/provenance
4. Better social runtime logic for:
   - greeting suppression
   - new-arrival handling
   - likely-speaker attention
   - disengagement-aware shortening
   - honest limited-awareness behavior
5. UI visibility for latest scene facts and confidence.
6. Replay/test coverage.

Constraints:
- Do not stuff raw multimodal model text directly into the world model without normalization.
- Keep the cheap observer cheap and frequent.
- Only run heavier analysis when it is actually justified.
- Preserve degraded behavior when camera input is absent.

Definition of done:
- Blink-AI maintains a useful rolling perception state.
- Social behavior is meaningfully driven by explicit state.
- The world model separates fresh vs stale facts.
- Scene-grounded dialogue uses normalized facts.
- Tests and replay checks pass.

Validation:
- uv run pytest
- run at least one live or fixture-based scene interaction
- confirm the operator/UI surfaces show perception freshness and confidence

At the end, return:
- files changed
- new perception event types
- world-model changes
- what is continuous vs on-demand
