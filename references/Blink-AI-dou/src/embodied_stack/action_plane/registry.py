from __future__ import annotations

from embodied_stack.action_plane.connectors import ActionConnector, build_builtin_connectors
from embodied_stack.action_plane.models import ActionToolRoute
from embodied_stack.config import Settings
from embodied_stack.shared.contracts.action import ConnectorDescriptorRecord


DEFAULT_ACTION_ROUTES = (
    ActionToolRoute(tool_name="write_memory", connector_id="memory_local", action_name="write_memory"),
    ActionToolRoute(tool_name="promote_memory", connector_id="memory_local", action_name="promote_memory"),
    ActionToolRoute(tool_name="request_operator_help", connector_id="incident_local", action_name="request_operator_help"),
    ActionToolRoute(tool_name="log_incident", connector_id="incident_local", action_name="log_incident"),
    ActionToolRoute(tool_name="browser_task", connector_id="browser_runtime", action_name="browser_task"),
    ActionToolRoute(tool_name="create_reminder", connector_id="reminders_local", action_name="create_reminder"),
    ActionToolRoute(tool_name="list_reminders", connector_id="reminders_local", action_name="list_reminders"),
    ActionToolRoute(tool_name="mark_reminder_done", connector_id="reminders_local", action_name="mark_reminder_done"),
    ActionToolRoute(tool_name="create_note", connector_id="notes_local", action_name="create_note"),
    ActionToolRoute(tool_name="append_note", connector_id="notes_local", action_name="append_note"),
    ActionToolRoute(tool_name="search_notes", connector_id="notes_local", action_name="search_notes"),
    ActionToolRoute(tool_name="read_local_file", connector_id="local_files", action_name="read_local_file"),
    ActionToolRoute(tool_name="stage_local_file", connector_id="local_files", action_name="stage_local_file"),
    ActionToolRoute(tool_name="export_local_bundle", connector_id="local_files", action_name="export_local_bundle"),
    ActionToolRoute(tool_name="query_calendar", connector_id="calendar_local", action_name="query_calendar"),
    ActionToolRoute(tool_name="draft_calendar_event", connector_id="calendar_local", action_name="draft_calendar_event"),
)


class ActionRegistry:
    def __init__(self, *, settings: Settings | None = None, connectors: list[ActionConnector] | None = None) -> None:
        connector_items = connectors or build_builtin_connectors(settings=settings)
        self._connectors = {
            item.descriptor.connector_id: item
            for item in connector_items
        }
        self._descriptors = {
            connector_id: connector.descriptor
            for connector_id, connector in self._connectors.items()
        }
        self._routes = {item.tool_name: item for item in DEFAULT_ACTION_ROUTES}

    def list_connectors(self) -> list[ConnectorDescriptorRecord]:
        return [item.model_copy(deep=True) for item in self._descriptors.values()]

    def get_connector(self, connector_id: str) -> ConnectorDescriptorRecord | None:
        descriptor = self._descriptors.get(connector_id)
        return descriptor.model_copy(deep=True) if descriptor is not None else None

    def get_connector_runtime(self, connector_id: str) -> ActionConnector | None:
        return self._connectors.get(connector_id)

    def route_for_tool(self, tool_name: str) -> ActionToolRoute | None:
        route = self._routes.get(tool_name)
        if route is None:
            return None
        return ActionToolRoute(
            tool_name=route.tool_name,
            connector_id=route.connector_id,
            action_name=route.action_name,
        )

    def routed_tool_names(self) -> set[str]:
        return set(self._routes)


__all__ = [
    "ActionRegistry",
    "DEFAULT_ACTION_ROUTES",
]
