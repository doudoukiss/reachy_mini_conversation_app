from __future__ import annotations

from typing import Iterable

from embodied_stack.shared.models import ReadinessCheck, ServiceReadinessResponse

READINESS_DIMENSIONS = ("process", "usable", "media", "best_experience")


def readiness_dimension_ok(checks: Iterable[ReadinessCheck], dimension: str) -> bool:
    relevant = [item for item in checks if dimension in item.required_for]
    if not relevant:
        return True
    return all(item.ok for item in relevant)


def derive_readiness_status(
    *,
    process_ok: bool,
    usable_ok: bool,
    media_ok: bool,
    best_experience_ok: bool,
) -> str:
    if not process_ok or not usable_ok:
        return "blocked"
    if media_ok and best_experience_ok:
        return "ready"
    if not media_ok:
        return "media_degraded"
    return "best_experience_degraded"


def build_service_readiness_response(
    *,
    service: str,
    runtime_profile: str | None,
    checks: list[ReadinessCheck],
) -> ServiceReadinessResponse:
    process_ok = readiness_dimension_ok(checks, "process")
    usable_ok = readiness_dimension_ok(checks, "usable")
    media_ok = readiness_dimension_ok(checks, "media")
    best_experience_ok = readiness_dimension_ok(checks, "best_experience")
    return ServiceReadinessResponse(
        service=service,
        runtime_profile=runtime_profile,
        checks=checks,
        process_ok=process_ok,
        usable_ok=usable_ok,
        media_ok=media_ok,
        best_experience_ok=best_experience_ok,
        status=derive_readiness_status(
            process_ok=process_ok,
            usable_ok=usable_ok,
            media_ok=media_ok,
            best_experience_ok=best_experience_ok,
        ),
    )


__all__ = [
    "READINESS_DIMENSIONS",
    "build_service_readiness_response",
    "derive_readiness_status",
    "readiness_dimension_ok",
]
