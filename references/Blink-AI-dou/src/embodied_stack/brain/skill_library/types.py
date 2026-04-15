from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.models import CompanionBehaviorCategory


@dataclass(frozen=True)
class SkillSpec:
    name: str
    playbook_name: str
    description: str
    purpose: str
    required_tools: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    behavior_category: CompanionBehaviorCategory | None = None
    route_variant: str | None = None
    banned_tools: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    entry_conditions: tuple[str, ...] = ()
    exit_conditions: tuple[str, ...] = ()
    body_style_hints: tuple[str, ...] = ()
    memory_rules: tuple[str, ...] = ()
    evaluation_rubric: tuple[str, ...] = ()
    version: str = "1.0"
    playbook_version: str = "2.0"
    aliases: tuple[str, ...] = ()
