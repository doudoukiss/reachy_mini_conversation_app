from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from embodied_stack.shared.models import (
    ToolEffectClass,
    ToolLatencyClass,
    ToolPermissionClass,
    ToolSpecRecord,
)


ToolHandler = Callable[[BaseModel, Any], BaseModel]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    family: str
    category: str
    capability_name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: ToolHandler
    version: str = "1.0"
    permission_class: ToolPermissionClass = ToolPermissionClass.READ_ONLY
    latency_class: ToolLatencyClass = ToolLatencyClass.FAST
    effect_class: ToolEffectClass = ToolEffectClass.READ_ONLY
    confirmation_required: bool = False
    failure_modes: tuple[str, ...] = ()
    checkpoint_policy: str = "none"
    observability_policy: tuple[str, ...] = ("trace",)
    aliases: tuple[str, ...] = ()

    @property
    def requires_checkpoint(self) -> bool:
        return (
            self.checkpoint_policy != "none"
            or self.permission_class != ToolPermissionClass.READ_ONLY
            or self.effect_class != ToolEffectClass.READ_ONLY
        )

    def to_record(self) -> ToolSpecRecord:
        return ToolSpecRecord(
            name=self.name,
            version=self.version,
            family=self.family,
            capability_name=self.capability_name,
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
            permission_class=self.permission_class,
            latency_class=self.latency_class,
            effect_class=self.effect_class,
            confirmation_required=self.confirmation_required,
            failure_modes=list(self.failure_modes),
            checkpoint_policy=self.checkpoint_policy,
            observability_policy=list(self.observability_policy),
        )


__all__ = [
    "ToolHandler",
    "ToolSpec",
]
