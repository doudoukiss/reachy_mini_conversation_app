from __future__ import annotations

from embodied_stack.shared.models import DesktopDeviceHealth, DesktopDeviceKind, EdgeAdapterState

DEVICE_REASON_OK = "ok"
DEVICE_REASON_PERMISSION_DENIED = "permission_denied"
DEVICE_REASON_PERMISSION_REQUIRED = "permission_required"
DEVICE_REASON_DEVICE_MISSING = "device_missing"
DEVICE_REASON_DEVICE_BUSY = "device_busy"
DEVICE_REASON_FALLBACK_ACTIVE = "fallback_active"
DEVICE_REASON_UNSUPPORTED_ROUTING = "unsupported_routing"


def build_device_health(
    *,
    device_id: str,
    kind: DesktopDeviceKind,
    state: EdgeAdapterState,
    backend: str,
    available: bool,
    required: bool,
    detail: str | None,
    configured_label: str | None = None,
    selected_label: str | None = None,
    reason_code: str = DEVICE_REASON_OK,
    selection_note: str | None = None,
    fallback_active: bool = False,
) -> DesktopDeviceHealth:
    return DesktopDeviceHealth(
        device_id=device_id,
        kind=kind,
        state=state,
        backend=backend,
        available=available,
        required=required,
        detail=detail,
        configured_label=configured_label,
        selected_label=selected_label,
        reason_code=reason_code,
        selection_note=selection_note,
        fallback_active=fallback_active,
    )


def device_reason_code_for_error(
    classification: str | None,
    *,
    fallback_active: bool = False,
    unsupported_routing: bool = False,
) -> str:
    lowered = (classification or "").strip().lower()
    if unsupported_routing:
        return DEVICE_REASON_UNSUPPORTED_ROUTING
    if fallback_active:
        return DEVICE_REASON_FALLBACK_ACTIVE
    if "permission_denied" in lowered or "authorization_failed" in lowered:
        return DEVICE_REASON_PERMISSION_DENIED
    if "permission_required" in lowered or "authorization_required" in lowered:
        return DEVICE_REASON_PERMISSION_REQUIRED
    if "busy" in lowered:
        return DEVICE_REASON_DEVICE_BUSY
    if "missing" in lowered or "not_found" in lowered or "unavailable" in lowered:
        return DEVICE_REASON_DEVICE_MISSING
    return DEVICE_REASON_DEVICE_MISSING


__all__ = [
    "DEVICE_REASON_DEVICE_BUSY",
    "DEVICE_REASON_DEVICE_MISSING",
    "DEVICE_REASON_FALLBACK_ACTIVE",
    "DEVICE_REASON_OK",
    "DEVICE_REASON_PERMISSION_DENIED",
    "DEVICE_REASON_PERMISSION_REQUIRED",
    "DEVICE_REASON_UNSUPPORTED_ROUTING",
    "build_device_health",
    "device_reason_code_for_error",
]
