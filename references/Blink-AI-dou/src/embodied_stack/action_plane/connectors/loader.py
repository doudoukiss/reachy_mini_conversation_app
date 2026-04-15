from __future__ import annotations

from pathlib import Path

from embodied_stack.action_plane.connectors.base import ActionConnector
from embodied_stack.action_plane.connectors.browser import BrowserRuntimeConnector
from embodied_stack.action_plane.connectors.builtin import (
    CalendarLocalConnector,
    IncidentLocalConnector,
    LocalFilesConnector,
    MCPAdapterConnector,
    MemoryLocalConnector,
    NotesLocalConnector,
    RemindersLocalConnector,
    build_default_connector_descriptors,
)
from embodied_stack.config import Settings


def build_builtin_connectors(*, settings: Settings | None = None) -> list[ActionConnector]:
    settings = settings or Settings()
    descriptors = {item.connector_id: item for item in build_default_connector_descriptors(settings=settings)}
    disabled = settings.action_plane_disabled_connectors if settings is not None else set()

    def _descriptor(connector_id: str):
        descriptor = descriptors[connector_id].model_copy(deep=True)
        if connector_id in disabled:
            descriptor.supported = False
            descriptor.configured = False
            descriptor.notes = [*descriptor.notes, "disabled_by_settings"]
        return descriptor

    local_roots = [Path(item) for item in settings.action_plane_local_file_roots_list]
    stage_dir = Path(settings.blink_action_plane_stage_dir)
    export_dir = Path(settings.blink_action_plane_export_dir)
    draft_dir = Path(settings.blink_action_plane_draft_dir)

    return [
        MemoryLocalConnector(_descriptor("memory_local")),
        IncidentLocalConnector(_descriptor("incident_local")),
        BrowserRuntimeConnector(_descriptor("browser_runtime"), settings=settings),
        RemindersLocalConnector(_descriptor("reminders_local")),
        NotesLocalConnector(_descriptor("notes_local")),
        LocalFilesConnector(
            _descriptor("local_files"),
            allowed_roots=local_roots,
            stage_dir=stage_dir,
            export_dir=export_dir,
        ),
        CalendarLocalConnector(_descriptor("calendar_local"), draft_dir=draft_dir),
        MCPAdapterConnector(_descriptor("mcp_adapter")),
    ]


__all__ = ["build_builtin_connectors"]
