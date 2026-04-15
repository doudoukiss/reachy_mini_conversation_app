from __future__ import annotations

import json
import logging
from typing import Any


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    filtered = {key: value for key, value in fields.items() if value is not None}
    if not filtered:
        logger.log(level, message)
        return
    rendered = " ".join(f"{key}={_format_value(value)}" for key, value in sorted(filtered.items()))
    logger.log(level, "%s %s", message, rendered)


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value) if any(ch.isspace() for ch in value) or "=" in value else value
    return json.dumps(value, sort_keys=True, default=str)
