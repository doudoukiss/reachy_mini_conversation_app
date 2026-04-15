# Stage 0 — Local Appliance Reliability

## Status

Baseline implemented.

The repo now has:

- `uv run blink-appliance` as the canonical macOS appliance entrypoint
- browser-first setup and operator console flow
- appliance profile persistence
- explicit device catalog and device-health reporting
- localhost bootstrap auth for appliance mode
- typed fallback and honest degraded runtime reporting

## What landed

- appliance launcher and runtime directory repair
- setup gating before `/console`
- browser-visible model, memory, fallback, and device state
- explicit mic, camera, and speaker selection/status
- `--doctor`, `--reset-runtime`, and browser-open controls
- local companion and desktop-local loops retained as secondary paths

## Remaining hardening work

- keep the no-browser recovery/operator path polished instead of letting it drift behind the browser path
- improve machine-specific permission diagnostics where macOS only exposes partial state
- continue making speaker-routing limitations explicit instead of implying full routing control
- keep startup and setup boring even when local models or media devices are unavailable

## Maintained acceptance truth

Stage 0 should now be read as a hardening stage, not a missing major feature:

- one-command appliance launch already exists
- terminal babysitting is no longer required for normal appliance use
- typed fallback already exists and must remain non-negotiable
- future work is reliability polish, not architectural rework
