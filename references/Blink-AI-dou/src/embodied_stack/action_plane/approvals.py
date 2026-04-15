from __future__ import annotations

from pathlib import Path

from embodied_stack.action_plane.models import PendingApprovalEnvelope
from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.contracts.action import ActionApprovalRecord, ActionApprovalState
from embodied_stack.shared.contracts._common import utc_now


class ApprovalStore:
    def __init__(self, root_dir: str | Path) -> None:
        self._path = Path(root_dir) / "pending_approvals.json"
        self._envelope = self._load()

    def _load(self) -> PendingApprovalEnvelope:
        loaded = load_json_model_or_quarantine(self._path, PendingApprovalEnvelope, quarantine_invalid=True)
        return loaded if loaded is not None else PendingApprovalEnvelope()

    def _persist(self) -> None:
        write_json_atomic(self._path, self._envelope, keep_backups=2)

    def list_pending(self) -> list[ActionApprovalRecord]:
        return [item.model_copy(deep=True) for item in self._envelope.items]

    def pending_count(self) -> int:
        return len(self._envelope.items)

    def get_by_action_id(self, action_id: str) -> ActionApprovalRecord | None:
        for item in self._envelope.items:
            if item.action_id == action_id:
                return item.model_copy(deep=True)
        return None

    def get_by_idempotency_key(self, idempotency_key: str) -> ActionApprovalRecord | None:
        for item in self._envelope.items:
            if item.idempotency_key == idempotency_key:
                return item.model_copy(deep=True)
        return None

    def upsert(self, record: ActionApprovalRecord) -> ActionApprovalRecord:
        for index, item in enumerate(self._envelope.items):
            if item.action_id == record.action_id or item.idempotency_key == record.idempotency_key:
                updated = record.model_copy(update={"updated_at": utc_now()})
                self._envelope.items[index] = updated
                self._persist()
                return updated.model_copy(deep=True)
        created = record.model_copy(update={"updated_at": utc_now()})
        self._envelope.items.append(created)
        self._persist()
        return created.model_copy(deep=True)

    def remove(self, action_id: str) -> None:
        original = len(self._envelope.items)
        self._envelope.items = [item for item in self._envelope.items if item.action_id != action_id]
        if len(self._envelope.items) != original:
            self._persist()

    def mark_rejected(self, action_id: str, *, detail: str | None = None) -> ActionApprovalRecord | None:
        for index, item in enumerate(self._envelope.items):
            if item.action_id == action_id:
                updated = item.model_copy(
                    update={
                        "approval_state": ActionApprovalState.REJECTED,
                        "detail": detail or item.detail,
                        "updated_at": utc_now(),
                    }
                )
                self._envelope.items[index] = updated
                self._persist()
                return updated.model_copy(deep=True)
        return None

    def resolve(
        self,
        action_id: str,
        *,
        approval_state: ActionApprovalState,
        operator_note: str | None = None,
        detail: str | None = None,
        remove_after: bool = True,
    ) -> ActionApprovalRecord | None:
        for index, item in enumerate(self._envelope.items):
            if item.action_id != action_id:
                continue
            updated = item.model_copy(
                update={
                    "approval_state": approval_state,
                    "operator_note": operator_note if operator_note is not None else item.operator_note,
                    "detail": detail or item.detail,
                    "updated_at": utc_now(),
                }
            )
            if remove_after:
                del self._envelope.items[index]
                self._persist()
                return updated.model_copy(deep=True)
            self._envelope.items[index] = updated
            self._persist()
            return updated.model_copy(deep=True)
        return None

    def approve(self, action_id: str, *, operator_note: str | None = None) -> ActionApprovalRecord | None:
        return self.resolve(
            action_id,
            approval_state=ActionApprovalState.APPROVED,
            operator_note=operator_note,
            remove_after=True,
        )

    def reject(
        self,
        action_id: str,
        *,
        operator_note: str | None = None,
        detail: str | None = None,
    ) -> ActionApprovalRecord | None:
        return self.resolve(
            action_id,
            approval_state=ActionApprovalState.REJECTED,
            operator_note=operator_note,
            detail=detail,
            remove_after=True,
        )


__all__ = ["ApprovalStore"]
