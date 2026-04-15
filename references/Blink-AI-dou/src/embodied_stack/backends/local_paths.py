from __future__ import annotations

import shutil
from pathlib import Path

from embodied_stack.config import Settings


_WHISPER_PREFERRED_MODEL_FILENAMES = (
    "ggml-base.en.bin",
    "ggml-small.en.bin",
    "ggml-tiny.en.bin",
)


def resolve_whisper_cpp_binary_path(settings: Settings) -> str | None:
    return settings.whisper_cpp_binary or shutil.which("whisper-cli") or shutil.which("main")


def resolve_whisper_cpp_model_path(
    settings: Settings,
    *,
    home_dir: Path | None = None,
    brew_prefix: Path | None = None,
) -> Path | None:
    explicit_path = (settings.whisper_cpp_model_path or "").strip()
    if explicit_path:
        return Path(explicit_path).expanduser()

    for candidate_dir in whisper_cpp_model_directories(home_dir=home_dir, brew_prefix=brew_prefix):
        discovered = _discover_whisper_model_in_directory(candidate_dir)
        if discovered is not None:
            return discovered
    return None


def whisper_cpp_model_directories(
    *,
    home_dir: Path | None = None,
    brew_prefix: Path | None = None,
) -> tuple[Path, ...]:
    home = home_dir or Path.home()
    prefix = brew_prefix or _default_homebrew_prefix()
    candidates = [
        home / ".cache" / "berserker" / "whisper-cpp",
        home / ".cache" / "whisper.cpp",
        prefix / "share" / "whisper.cpp" / "models",
        prefix / "share" / "whisper-cpp",
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        expanded = candidate.expanduser()
        if expanded in seen:
            continue
        seen.add(expanded)
        unique.append(expanded)
    return tuple(unique)


def _default_homebrew_prefix() -> Path:
    brew_path = shutil.which("brew")
    if brew_path:
        return Path(brew_path).resolve().parents[1]
    return Path("/opt/homebrew")


def _discover_whisper_model_in_directory(directory: Path) -> Path | None:
    if not directory.exists() or not directory.is_dir():
        return None

    for filename in _WHISPER_PREFERRED_MODEL_FILENAMES:
        candidate = directory / filename
        if candidate.exists():
            return candidate

    preferred_names = set(_WHISPER_PREFERRED_MODEL_FILENAMES)
    extras = sorted(
        candidate
        for candidate in directory.glob("ggml-*.bin")
        if candidate.is_file() and candidate.name not in preferred_names
    )
    return extras[0] if extras else None


__all__ = [
    "resolve_whisper_cpp_binary_path",
    "resolve_whisper_cpp_model_path",
    "whisper_cpp_model_directories",
]
