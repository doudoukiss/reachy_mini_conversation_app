from __future__ import annotations

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.perception import PerceptionService
from embodied_stack.config import Settings
from embodied_stack.shared.models import CommandBatch, PerceptionProviderMode, RobotEvent


def build_perception_service(
    *,
    settings: Settings,
    memory: MemoryStore,
    event_handler,
) -> PerceptionService:
    return PerceptionService(settings=settings, memory=memory, event_handler=event_handler)


def resolve_default_perception_mode(settings: Settings) -> PerceptionProviderMode:
    configured = settings.perception_default_provider
    if configured in PerceptionProviderMode._value2member_map_:
        return PerceptionProviderMode(configured)
    return PerceptionProviderMode.STUB

__all__ = ["PerceptionService", "build_perception_service", "resolve_default_perception_mode"]
