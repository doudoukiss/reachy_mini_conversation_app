from __future__ import annotations

import hashlib

from embodied_stack.shared.contracts._common import ExportRedactionProfile, RedactionState, SensitiveContentFlag
from embodied_stack.shared.contracts.episode import EpisodeRecordV2


def collect_sensitive_content_flags(episode: EpisodeRecordV2) -> list[SensitiveContentFlag]:
    flags: list[SensitiveContentFlag] = []
    if any(session.operator_notes for session in episode.sessions):
        flags.append(SensitiveContentFlag.OPERATOR_NOTE)
    if any(session.session_memory for session in episode.sessions):
        flags.append(SensitiveContentFlag.SESSION_MEMORY)
    if episode.profile_memory:
        flags.append(SensitiveContentFlag.PROFILE_MEMORY)
    if any(annotation.note or annotation.better_reply_text or annotation.corrected_scene_summary for annotation in episode.teacher_annotations):
        flags.append(SensitiveContentFlag.TEACHER_FREEFORM)
    if any(session.user_id for session in episode.sessions) or any(trace.user_id for trace in episode.traces):
        flags.append(SensitiveContentFlag.USER_IDENTIFIER)
    if any(entry.turn.user_text or entry.turn.reply_text for entry in episode.transcript):
        flags.append(SensitiveContentFlag.TRANSCRIPT_TEXT)
    return flags


def apply_episode_redaction_profile(
    episode: EpisodeRecordV2,
    *,
    profile: ExportRedactionProfile,
) -> EpisodeRecordV2:
    redacted = episode.model_copy(deep=True)
    redacted.redaction_profile = profile
    redacted.sensitive_content_flags = collect_sensitive_content_flags(redacted)
    if profile == ExportRedactionProfile.LOCAL_FULL:
        return redacted

    if profile in {ExportRedactionProfile.LOCAL_OPERATOR, ExportRedactionProfile.RESEARCH_REDACTED}:
        _redact_operator_notes(redacted)
        _redact_session_memory(redacted)

    if profile == ExportRedactionProfile.RESEARCH_REDACTED:
        _pseudonymize_user_ids(redacted)
        _redact_profile_memory(redacted)
        _redact_teacher_freeform(redacted)

    return redacted


def _redact_operator_notes(episode: EpisodeRecordV2) -> None:
    if "operator_notes" not in episode.redactions_applied:
        episode.redactions_applied.append("operator_notes")
    for session in episode.sessions:
        for note in session.operator_notes:
            note.text = "[redacted]"
    if SensitiveContentFlag.OPERATOR_NOTE not in episode.sensitive_content_flags:
        episode.sensitive_content_flags.append(SensitiveContentFlag.OPERATOR_NOTE)


def _redact_session_memory(episode: EpisodeRecordV2) -> None:
    if "session_memory" not in episode.redactions_applied:
        episode.redactions_applied.append("session_memory")
    for session in episode.sessions:
        if session.session_memory:
            session.session_memory = {"redacted": "[redacted]"}
    if SensitiveContentFlag.SESSION_MEMORY not in episode.sensitive_content_flags:
        episode.sensitive_content_flags.append(SensitiveContentFlag.SESSION_MEMORY)


def _redact_profile_memory(episode: EpisodeRecordV2) -> None:
    if "profile_memory" not in episode.redactions_applied:
        episode.redactions_applied.append("profile_memory")
    for record in episode.profile_memory:
        record.display_name = None
        record.facts = {"redacted": "[redacted]"} if record.facts else {}
        record.preferences = {"redacted": "[redacted]"} if record.preferences else {}
        record.interests = ["[redacted]"] if record.interests else []
        record.redaction_state = RedactionState.REDACTED
        record.sensitive_content_flags = _merge_flags(record.sensitive_content_flags, [SensitiveContentFlag.PROFILE_MEMORY])
    if SensitiveContentFlag.PROFILE_MEMORY not in episode.sensitive_content_flags:
        episode.sensitive_content_flags.append(SensitiveContentFlag.PROFILE_MEMORY)


def _redact_teacher_freeform(episode: EpisodeRecordV2) -> None:
    if "teacher_freeform" not in episode.redactions_applied:
        episode.redactions_applied.append("teacher_freeform")
    for annotation in episode.teacher_annotations:
        if annotation.note is not None:
            annotation.note = "[redacted]"
        if annotation.better_reply_text is not None:
            annotation.better_reply_text = "[redacted]"
        if annotation.corrected_scene_summary is not None:
            annotation.corrected_scene_summary = "[redacted]"
        if annotation.reply_feedback is not None and annotation.reply_feedback.better_reply_text is not None:
            annotation.reply_feedback.better_reply_text = "[redacted]"
        if annotation.scene_feedback is not None and annotation.scene_feedback.corrected_scene_summary is not None:
            annotation.scene_feedback.corrected_scene_summary = "[redacted]"
        annotation.redaction_state = RedactionState.REDACTED
        annotation.sensitive_content_flags = _merge_flags(
            annotation.sensitive_content_flags,
            [SensitiveContentFlag.TEACHER_FREEFORM],
        )


def _pseudonymize_user_ids(episode: EpisodeRecordV2) -> None:
    mapping: dict[str, str] = {}

    def pseudonym(value: str | None) -> str | None:
        if not value:
            return value
        if value not in mapping:
            digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
            mapping[value] = f"user-{digest}"
        return mapping[value]

    for session in episode.sessions:
        session.user_id = pseudonym(session.user_id)
    for trace in episode.traces:
        trace.user_id = pseudonym(trace.user_id)
    for record in episode.profile_memory:
        record.user_id = pseudonym(record.user_id)
        record.redaction_state = RedactionState.REDACTED
        record.sensitive_content_flags = _merge_flags(
            record.sensitive_content_flags,
            [SensitiveContentFlag.USER_IDENTIFIER],
        )
    for record in episode.episodic_memory:
        record.user_id = pseudonym(record.user_id)
        record.redaction_state = RedactionState.REDACTED
    for record in episode.semantic_memory:
        record.user_id = pseudonym(record.user_id)
        record.redaction_state = RedactionState.REDACTED
    for annotation in episode.teacher_annotations:
        annotation.session_id = annotation.session_id
    if SensitiveContentFlag.USER_IDENTIFIER not in episode.sensitive_content_flags:
        episode.sensitive_content_flags.append(SensitiveContentFlag.USER_IDENTIFIER)


def _merge_flags(existing: list[SensitiveContentFlag], extra: list[SensitiveContentFlag]) -> list[SensitiveContentFlag]:
    merged = list(existing)
    for item in extra:
        if item not in merged:
            merged.append(item)
    return merged
