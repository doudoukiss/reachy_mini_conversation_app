"""Helpers for working with capability catalogs."""

from __future__ import annotations

from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.robot_brain.contracts import CapabilityCatalog, RobotHealth, RobotState


def empty_capability_catalog(*, backend: str, robot_name: str, warning: str | None = None) -> CapabilityCatalog:
    """Create an empty capability catalog for unavailable or unconfigured backends."""
    warnings = [warning] if warning else []
    return CapabilityCatalog(
        robot_name=robot_name,
        backend=backend,
        modes_supported=[],
        warnings=warnings,
    )


def summarize_capabilities(catalog: CapabilityCatalog) -> str:
    """Return a concise human-readable capability summary."""
    parts: list[str] = [f"{catalog.robot_name} ({catalog.backend})"]
    if catalog.persistent_states:
        parts.append(f"states: {', '.join(catalog.persistent_states)}")
    if catalog.motifs:
        parts.append(f"motifs: {', '.join(catalog.motifs)}")
    if catalog.attention_modes:
        parts.append(f"attention: {', '.join(catalog.attention_modes)}")
    if catalog.warnings:
        parts.append(f"warnings: {', '.join(catalog.warnings)}")
    return " | ".join(parts)


def configured_capability_catalog(backend: str | None = None) -> CapabilityCatalog:
    """Return the configured semantic capability surface for the active backend.

    This is intentionally conservative and synchronous so prompts and tool specs
    can expose a meaningful catalog before any live adapter calls occur.
    """
    backend_name = (backend or config.ROBOT_BACKEND).strip().lower()

    if backend_name == "mock":
        return CapabilityCatalog(
            robot_name="mock-head",
            backend="mock",
            modes_supported=["mock"],
            structural_units=["head_turn", "neck_pitch", "neck_tilt"],
            expressive_units=["eye_yaw", "eye_pitch", "lids", "brows"],
            persistent_states=["neutral", "friendly", "listen_attentively", "thinking", "safe_idle"],
            motifs=["guarded_close_left", "guarded_close_right"],
            attention_modes=["manual", "face_tracking", "idle_scan", "disabled"],
            warnings=[],
        )

    if backend_name == "reachy":
        return CapabilityCatalog(
            robot_name="reachy-mini",
            backend="reachy",
            modes_supported=["mock", "preview", "live"],
            structural_units=["head_turn", "neck_pitch", "neck_tilt", "antennas"],
            expressive_units=["antennas"],
            persistent_states=[],
            motifs=[],
            attention_modes=["manual", "disabled", "face_tracking", "idle_scan"],
            warnings=[
                "set_expression_state may be rejected on Reachy until a semantic expression adapter is added.",
                "perform_motif may be rejected on Reachy until a semantic motif adapter is added.",
                "idle_scan may fall back to manual attention on Reachy.",
            ],
        )

    return empty_capability_catalog(
        backend=backend_name,
        robot_name=backend_name.replace("_", "-"),
        warning=f"{backend_name} capability catalog is not implemented yet.",
    )


def current_capability_catalog(robot_runtime: object | None = None) -> CapabilityCatalog:
    """Return the freshest available catalog without requiring async startup."""
    state_store = getattr(robot_runtime, "state_store", None)
    cached = getattr(state_store, "capabilities", None)
    if cached is not None:
        return cached
    return configured_capability_catalog()


def format_allowed_values(values: list[str]) -> str:
    """Format a compact allowed-values string for tool descriptions."""
    if not values:
        return "none available on this backend"
    return ", ".join(values)


def summarize_robot_context(
    catalog: CapabilityCatalog | None,
    *,
    health: RobotHealth | None = None,
    state: RobotState | None = None,
) -> str:
    """Build a compact capability and state summary for prompts or logs."""
    parts: list[str] = []
    if catalog is not None:
        parts.append(summarize_capabilities(catalog))
    if health is not None:
        parts.append(f"health: {health.overall} ({health.message})")
    if state is not None:
        state_bits: list[str] = [f"mode={state.mode}"]
        if state.persistent_state:
            state_bits.append(f"state={state.persistent_state}")
        if state.active_behavior:
            state_bits.append(f"behavior={state.active_behavior}")
        if state.attention_mode:
            state_bits.append(f"attention={state.attention_mode}")
        parts.append(", ".join(state_bits))
    return " | ".join(parts)


def build_prompt_capability_block(robot_runtime: object | None = None) -> str:
    """Build a concise capability block for prompt/session assembly."""
    catalog = current_capability_catalog(robot_runtime)
    lines = [
        "## RUNTIME CAPABILITY SUMMARY",
        f"Backend: {catalog.backend}",
        f"Execution mode: {config.ROBOT_EXECUTION_MODE}",
        f"Attention modes: {format_allowed_values(catalog.attention_modes)}",
        f"Persistent states: {format_allowed_values(catalog.persistent_states)}",
        f"Motifs: {format_allowed_values(catalog.motifs)}",
    ]
    if catalog.warnings:
        lines.append(f"Current limitations: {'; '.join(catalog.warnings)}")
    lines.append("Prefer semantic robot tools over improvised low-level motion descriptions.")
    return "\n".join(lines)
