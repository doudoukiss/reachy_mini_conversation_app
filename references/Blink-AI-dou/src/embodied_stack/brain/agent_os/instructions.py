from __future__ import annotations

from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.shared.models import InstructionLayerRecord, SessionRecord, UserMemoryRecord

from .models import LoadedInstruction


class InstructionBundleLoader:
    FILES = {
        "identity": "IDENTITY.md",
        "site_policy": "SITE_POLICY.md",
        "body_policy": "BODY_POLICY.md",
    }

    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings

    def load(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
    ) -> list[LoadedInstruction]:
        documents = [self._load_static(name, file_name) for name, file_name in self.FILES.items()]
        documents.append(self._render_user_memory(session=session, user_memory=user_memory))
        return [item for item in documents if item is not None]

    def _load_static(self, name: str, file_name: str) -> LoadedInstruction | None:
        path = Path(self.settings.brain_instruction_dir) / file_name
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8").strip()
        return LoadedInstruction(
            record=InstructionLayerRecord(
                name=name,
                source_ref=str(path),
                dynamic=False,
                summary=self._summary(content),
            ),
            content=content,
        )

    def _render_user_memory(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
    ) -> LoadedInstruction:
        if user_memory is None:
            content = (
                "# User Memory\n\n"
                "No durable user memory is available for this session yet.\n"
                f"Session summary: {session.conversation_summary or 'No conversation summary yet.'}"
            )
            source_ref = f"generated:user_memory:{session.session_id}:anonymous"
        else:
            fact_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(user_memory.facts.items())) or "- none"
            preference_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(user_memory.preferences.items())) or "- none"
            interest_lines = "\n".join(f"- {item}" for item in user_memory.interests) or "- none"
            relationship_profile = user_memory.relationship_profile
            tone_lines = "\n".join(f"- {item}" for item in relationship_profile.tone_preferences) or "- none"
            boundary_lines = "\n".join(f"- {item}" for item in relationship_profile.interaction_boundaries) or "- none"
            continuity_lines = "\n".join(f"- {item}" for item in relationship_profile.continuity_preferences) or "- none"
            content = (
                "# User Memory\n\n"
                f"User ID: {user_memory.user_id}\n"
                f"Display name: {user_memory.display_name or 'unknown'}\n"
                f"Visit count: {user_memory.visit_count}\n"
                f"Last session: {user_memory.last_session_id or session.session_id}\n"
                f"Preferred response mode: {(user_memory.preferred_response_mode.value if user_memory.preferred_response_mode else 'unknown')}\n\n"
                "Facts:\n"
                f"{fact_lines}\n\n"
                "Preferences:\n"
                f"{preference_lines}\n\n"
                "Relationship profile:\n"
                f"- greeting_preference: {relationship_profile.greeting_preference or 'none'}\n"
                f"- planning_style: {relationship_profile.planning_style or 'none'}\n"
                "Tone preferences:\n"
                f"{tone_lines}\n\n"
                "Interaction boundaries:\n"
                f"{boundary_lines}\n\n"
                "Continuity preferences:\n"
                f"{continuity_lines}\n\n"
                "Interests:\n"
                f"{interest_lines}\n"
            )
            source_ref = f"generated:user_memory:{user_memory.user_id}"

        return LoadedInstruction(
            record=InstructionLayerRecord(
                name="user_memory",
                source_ref=source_ref,
                dynamic=True,
                summary=self._summary(content),
            ),
            content=content,
        )

    def _summary(self, content: str) -> str:
        normalized = " ".join(content.split())
        return normalized[:160] + ("..." if len(normalized) > 160 else "")
