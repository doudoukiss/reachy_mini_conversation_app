from __future__ import annotations

from embodied_stack.shared.models import CompanionBehaviorCategory

from .types import SkillSpec


OBSERVE_AND_COMMENT: tuple[SkillSpec, ...] = (
    SkillSpec(
        name="observe_and_comment",
        playbook_name="observe_and_comment",
        route_variant="observe_and_comment",
        behavior_category=CompanionBehaviorCategory.OBSERVE_AND_COMMENT,
        description="Careful commentary based only on current perception facts.",
        purpose="Describe the current scene without overstating visual certainty.",
        required_tools=("capture_scene", "world_model_runtime", "device_health_snapshot", "system_health"),
        allowed_tools=("capture_scene", "world_model_runtime", "device_health_snapshot", "system_health", "body_preview"),
        forbidden_claims=("I recognize who you are",),
        success_criteria=("mention only structured scene facts", "surface uncertainty"),
        entry_conditions=("A visual or scene-reading question was asked.",),
        exit_conditions=("The scene answer is explicitly grounded or explicitly degraded.",),
        body_style_hints=("listen_attentively", "measured"),
        memory_rules=("Do not promote transient visual observations into durable memory by default.",),
        evaluation_rubric=("Visual honesty", "Specificity", "Uncertainty handling"),
    ),
)
