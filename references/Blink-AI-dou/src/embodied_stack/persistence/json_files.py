from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T")


def normalize_json_payload(payload: object) -> object:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, (datetime, date, time)):
        return payload.isoformat()
    if isinstance(payload, list):
        return [normalize_json_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return [normalize_json_payload(item) for item in payload]
    if isinstance(payload, dict):
        return {str(key): normalize_json_payload(value) for key, value in payload.items()}
    return payload


def write_text_atomic(path: str | Path, text: str, *, keep_backups: int = 0, encoding: str = "utf-8") -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding=encoding, dir=resolved.parent, delete=False) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    if keep_backups > 0 and resolved.exists():
        _rotate_backups(resolved, keep_backups)
    os.replace(temp_path, resolved)
    return resolved


def write_json_atomic(
    path: str | Path,
    payload: object,
    *,
    keep_backups: int = 0,
    indent: int = 2,
    encoding: str = "utf-8",
) -> Path:
    serialized = json.dumps(normalize_json_payload(payload), indent=indent)
    return write_text_atomic(path, serialized, keep_backups=keep_backups, encoding=encoding)


def quarantine_invalid_file(path: str | Path) -> Path | None:
    resolved = Path(path)
    if not resolved.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    quarantined = resolved.with_name(f"{resolved.name}.corrupt-{stamp}")
    os.replace(resolved, quarantined)
    return quarantined


def load_json_value_or_quarantine(path: str | Path, *, quarantine_invalid: bool = False) -> Any | None:
    resolved = Path(path)
    if not resolved.exists():
        return None
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        if quarantine_invalid:
            quarantine_invalid_file(resolved)
        return None


def load_json_model_or_quarantine(
    path: str | Path,
    model: type[T],
    *,
    quarantine_invalid: bool = False,
) -> T | None:
    resolved = Path(path)
    if not resolved.exists():
        return None
    try:
        payload = resolved.read_text(encoding="utf-8")
        if hasattr(model, "model_validate_json"):
            return model.model_validate_json(payload)
        return model(json.loads(payload))
    except (OSError, ValueError, TypeError, ValidationError):
        if quarantine_invalid:
            quarantine_invalid_file(resolved)
        return None


def _rotate_backups(path: Path, keep_backups: int) -> None:
    oldest = path.with_name(f"{path.name}.bak{keep_backups}")
    if oldest.exists():
        try:
            oldest.unlink()
        except FileNotFoundError:
            pass
    for index in range(keep_backups - 1, 0, -1):
        current = path.with_name(f"{path.name}.bak{index}")
        if current.exists():
            try:
                current.replace(path.with_name(f"{path.name}.bak{index + 1}"))
            except FileNotFoundError:
                continue
    try:
        path.replace(path.with_name(f"{path.name}.bak1"))
    except FileNotFoundError:
        return
