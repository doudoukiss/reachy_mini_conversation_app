from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from embodied_stack.action_plane.bundles import ActionBundleStore
from embodied_stack.action_plane.connectors import ConnectorActionError
from embodied_stack.action_plane.registry import ActionRegistry
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    ActionExecutionStatus,
    ActionInvocationOrigin,
    ActionReplayRecord,
    ActionReplayRequestRecord,
    ActionReplayStatus,
    ActionRequestRecord,
    ActionRiskClass,
)
from embodied_stack.shared.contracts._common import utc_now


@dataclass
class ActionReplayHarness:
    settings: Settings
    bundle_store: ActionBundleStore

    @classmethod
    def from_settings(cls, *, settings: Settings) -> "ActionReplayHarness":
        return cls(
            settings=settings,
            bundle_store=ActionBundleStore(settings.blink_action_plane_export_dir),
        )

    def replay_bundle(self, request: ActionReplayRequestRecord) -> ActionReplayRecord:
        bundle_id = request.bundle_id or (
            ActionBundleStore.bundle_id_for_action(request.action_id) if request.action_id else None
        )
        if not bundle_id:
            raise KeyError("bundle_id_required")
        detail = self.bundle_store.get_bundle_detail(bundle_id)
        if detail is None:
            raise KeyError(bundle_id)

        started_at = utc_now()
        blocked_action_ids: list[str] = []
        results: list[dict[str, object]] = []
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            runtime_settings = self.settings.model_copy(
                update={
                    "brain_store_path": str(root / "brain_store.json"),
                    "blink_action_plane_browser_backend": "stub",
                    "blink_action_plane_browser_storage_dir": str(root / "browser"),
                    "blink_action_plane_draft_dir": str(root / "drafts"),
                    "blink_action_plane_stage_dir": str(root / "staged"),
                    "blink_action_plane_export_dir": str(root / "exports"),
                    "blink_action_plane_local_file_roots": str(Path.cwd()),
                }
            )
            registry = ActionRegistry(settings=runtime_settings)
            memory_store = MemoryStore(root / "brain_store.json")
            session = memory_store.ensure_session(
                detail.manifest.session_id or "action-replay-session",
                user_id="action-replay-user",
            )
            runtime_context = SimpleNamespace(
                session=session,
                memory_store=memory_store,
                user_memory=None,
                knowledge_tools=KnowledgeToolbox(settings=runtime_settings, memory_store=memory_store),
            )

            for index, call in enumerate(detail.connector_calls, start=1):
                if call.status == ActionExecutionStatus.PENDING_APPROVAL and call.action_id not in request.approved_action_ids:
                    blocked_action_ids.append(call.action_id)
                    results.append(
                        {
                            "step_index": index,
                            "source_action_id": call.action_id,
                            "status": ActionReplayStatus.BLOCKED.value,
                            "detail": "approval_required_for_replay",
                        }
                    )
                    break
                connector = registry.get_connector_runtime(call.connector_id)
                if connector is None:
                    results.append(
                        {
                            "step_index": index,
                            "source_action_id": call.action_id,
                            "status": ActionReplayStatus.FAILED.value,
                            "detail": f"connector_unavailable:{call.connector_id}",
                        }
                    )
                    break
                replay_request = ActionRequestRecord(
                    action_id=f"replay_{call.action_id}",
                    request_hash=f"replay:{call.action_id}",
                    idempotency_key=f"replay:{uuid4().hex}:{call.action_id}",
                    tool_name=call.tool_name,
                    requested_tool_name=call.tool_name,
                    action_name=call.action_name,
                    requested_action_name=call.action_name,
                    connector_id=call.connector_id,
                    risk_class=call.risk_class or ActionRiskClass.READ_ONLY,
                    invocation_origin=ActionInvocationOrigin.OPERATOR_CONSOLE,
                    session_id=session.session_id,
                    run_id=detail.manifest.run_id,
                    workflow_run_id=detail.manifest.workflow_run_id,
                    workflow_step_id=call.workflow_step_id,
                    input_payload=dict(call.input_payload),
                )
                try:
                    replayed = connector.execute(
                        action_name=call.action_name,
                        request=replay_request,
                        runtime_context=runtime_context,
                    )
                    results.append(
                        {
                            "step_index": index,
                            "source_action_id": call.action_id,
                            "replay_action_id": replay_request.action_id,
                            "connector_id": call.connector_id,
                            "status": ActionExecutionStatus.EXECUTED.value,
                            "summary": replayed.summary,
                            "detail": replayed.detail,
                            "output_payload": replayed.output_payload,
                            "artifacts": [item.model_dump(mode="json") for item in replayed.artifacts],
                        }
                    )
                except ConnectorActionError as exc:
                    results.append(
                        {
                            "step_index": index,
                            "source_action_id": call.action_id,
                            "replay_action_id": replay_request.action_id,
                            "connector_id": call.connector_id,
                            "status": ActionReplayStatus.FAILED.value,
                            "error_code": exc.code,
                            "detail": exc.detail,
                        }
                    )
                    break

        failed = any(item.get("status") == ActionReplayStatus.FAILED.value for item in results)
        status = (
            ActionReplayStatus.BLOCKED
            if blocked_action_ids
            else (ActionReplayStatus.FAILED if failed else ActionReplayStatus.COMPLETED)
        )
        record = ActionReplayRecord(
            replay_id=f"action-replay-{uuid4().hex[:16]}",
            bundle_id=detail.manifest.bundle_id,
            root_kind=detail.manifest.root_kind,
            status=status,
            replayed_action_count=sum(1 for item in results if item.get("status") == ActionExecutionStatus.EXECUTED.value),
            blocked_action_ids=blocked_action_ids,
            notes=[
                f"source_root_kind={detail.manifest.root_kind.value}",
                f"connector_calls={len(detail.connector_calls)}",
            ],
            started_at=started_at,
            completed_at=utc_now(),
        )
        return self.bundle_store.save_replay(
            record,
            payloads={
                "source_bundle": detail.model_dump(mode="json"),
                "connector_calls": [item.model_dump(mode="json") for item in detail.connector_calls],
                "results": results,
            },
        )


__all__ = ["ActionReplayHarness"]
