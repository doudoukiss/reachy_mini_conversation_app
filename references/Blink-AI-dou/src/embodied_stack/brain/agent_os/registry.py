from __future__ import annotations

from dataclasses import dataclass

from .hooks import HookRegistry
from .skills import SkillRegistry
from .subagents import SubagentRegistry
from .tools import AgentToolRegistry


@dataclass(frozen=True)
class AgentOSRegistry:
    skills: SkillRegistry
    hooks: HookRegistry
    tools: AgentToolRegistry
    subagents: SubagentRegistry


__all__ = [
    "AgentOSRegistry",
]
