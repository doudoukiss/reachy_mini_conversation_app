from __future__ import annotations

from typing import Any

from ._common import BaseModel
from ._common import *
from . import action, body, brain, demo, edge, episode, operator, perception, research
from .action import *
from .body import *
from .brain import *
from .demo import *
from .edge import *
from .episode import *
from .operator import *
from .perception import *
from .research import *
from . import _common

__all__ = [
    *_common.__all__,
    *action.__all__,
    *edge.__all__,
    *body.__all__,
    *brain.__all__,
    *perception.__all__,
    *demo.__all__,
    *episode.__all__,
    *operator.__all__,
    *research.__all__,
]


def _rebuild_models() -> None:
    namespaces: dict[str, Any] = {}
    for module in (action, edge, body, brain, perception, demo, episode, operator, research):
        namespaces.update(module.__dict__)
    for module in (action, edge, body, brain, perception, demo, episode, operator, research):
        for value in module.__dict__.values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseModel)
                and value.__module__.startswith("embodied_stack.shared.contracts.")
            ):
                value.model_rebuild(_types_namespace=namespaces)


_rebuild_models()
