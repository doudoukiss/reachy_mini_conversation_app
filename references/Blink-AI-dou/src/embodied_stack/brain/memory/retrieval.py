from __future__ import annotations

from collections.abc import Iterable

from embodied_stack.shared.contracts._common import MemoryLayer, MemoryRetrievalBackend
from embodied_stack.shared.contracts.brain import (
    MemoryRetrievalCandidateRecord,
    MemoryRetrievalRecord,
    ToolInvocationRecord,
    TypedToolCallRecord,
)


def build_retrieval_records_from_tool_invocations(
    *,
    query_text: str | None,
    session_id: str | None,
    user_id: str | None,
    trace_id: str | None,
    run_id: str | None,
    tool_invocations: Iterable[ToolInvocationRecord],
) -> list[MemoryRetrievalRecord]:
    records: list[MemoryRetrievalRecord] = []
    for tool in tool_invocations:
        metadata = dict(tool.metadata or {})
        backend = _backend_for_tool_name(tool.tool_name)
        if backend is None:
            continue
        records.append(
            MemoryRetrievalRecord(
                query_text=query_text or str(metadata.get("query_text") or ""),
                backend=backend,
                backend_detail=str(metadata.get("retrieval_backend_detail") or metadata.get("knowledge_source") or tool.tool_name),
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                run_id=run_id,
                selected_candidates=_candidates_from_metadata(metadata, selected=True),
                rejected_candidates=_candidates_from_metadata(metadata, selected=False),
                miss_reason=_miss_reason_from_metadata(metadata),
                used_in_reply=tool.matched,
                latency_ms=_float_or_none(metadata.get("latency_ms")),
                notes=list(tool.notes),
            )
        )
    return records


def build_retrieval_records_from_typed_tool_calls(
    *,
    session_id: str | None,
    user_id: str | None,
    trace_id: str | None,
    run_id: str | None,
    typed_tool_calls: Iterable[TypedToolCallRecord],
) -> list[MemoryRetrievalRecord]:
    records: list[MemoryRetrievalRecord] = []
    for call in typed_tool_calls:
        if call.tool_name != "search_memory":
            continue
        payload = dict(call.output_payload or {})
        raw_records = payload.get("retrievals")
        if isinstance(raw_records, list):
            for item in raw_records:
                if not isinstance(item, dict):
                    continue
                record = MemoryRetrievalRecord.model_validate(item)
                record.session_id = session_id or record.session_id
                record.user_id = user_id or record.user_id
                record.trace_id = trace_id or record.trace_id
                record.run_id = run_id or record.run_id
                records.append(record)
            continue

        query_text = str(call.input_payload.get("query") or "")
        records.extend(
            _fallback_records_from_search_memory_payload(
                query_text=query_text,
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                run_id=run_id,
                payload=payload,
                call=call,
            )
        )
    return records


def _fallback_records_from_search_memory_payload(
    *,
    query_text: str,
    session_id: str | None,
    user_id: str | None,
    trace_id: str | None,
    run_id: str | None,
    payload: dict[str, object],
    call: TypedToolCallRecord,
) -> list[MemoryRetrievalRecord]:
    records: list[MemoryRetrievalRecord] = []
    if payload.get("profile_summary") or payload.get("remembered_facts") or payload.get("remembered_preferences"):
        records.append(
            MemoryRetrievalRecord(
                query_text=query_text,
                backend=MemoryRetrievalBackend.PROFILE_SCAN,
                backend_detail="search_memory_output",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                run_id=run_id,
                selected_candidates=[
                    MemoryRetrievalCandidateRecord(
                        memory_id=user_id,
                        layer=MemoryLayer.PROFILE,
                        summary=str(payload.get("profile_summary") or "profile_memory"),
                        reason="profile_summary_present",
                    )
                ],
                used_in_reply=call.success,
                notes=list(call.notes),
            )
        )
    episodic_hits = payload.get("episodic_hits")
    if isinstance(episodic_hits, list):
        records.append(
            MemoryRetrievalRecord(
                query_text=query_text,
                backend=MemoryRetrievalBackend.EPISODIC_KEYWORD,
                backend_detail="search_memory_output",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                run_id=run_id,
                selected_candidates=[
                    MemoryRetrievalCandidateRecord(
                        memory_id=str(item.get("memory_id")) if isinstance(item, dict) and item.get("memory_id") else None,
                        layer=MemoryLayer.EPISODIC,
                        summary=str(item.get("summary") or ""),
                        reason=str(item.get("ranking_reason") or "episodic_hit"),
                        score=_float_or_none(item.get("ranking_score")) if isinstance(item, dict) else None,
                        source_refs=[str(item.get("source_ref"))] if isinstance(item, dict) and item.get("source_ref") else [],
                        session_id=str(item.get("session_id")) if isinstance(item, dict) and item.get("session_id") else None,
                    )
                    for item in episodic_hits
                    if isinstance(item, dict)
                ],
                miss_reason=None if episodic_hits else "no_episodic_match",
                used_in_reply=call.success,
                notes=list(call.notes),
            )
        )
    semantic_hits = payload.get("semantic_hits")
    if isinstance(semantic_hits, list):
        records.append(
            MemoryRetrievalRecord(
                query_text=query_text,
                backend=MemoryRetrievalBackend.SEMANTIC_VECTOR,
                backend_detail="search_memory_output",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                run_id=run_id,
                selected_candidates=[
                    MemoryRetrievalCandidateRecord(
                        memory_id=str(item.get("memory_id")) if isinstance(item, dict) and item.get("memory_id") else None,
                        layer=MemoryLayer.SEMANTIC,
                        summary=str(item.get("summary") or ""),
                        reason=str(item.get("ranking_reason") or "semantic_hit"),
                        score=_float_or_none(item.get("ranking_score")) if isinstance(item, dict) else None,
                        source_refs=[str(item.get("source_ref"))] if isinstance(item, dict) and item.get("source_ref") else [],
                        session_id=str(item.get("session_id")) if isinstance(item, dict) and item.get("session_id") else None,
                    )
                    for item in semantic_hits
                    if isinstance(item, dict)
                ],
                miss_reason=None if semantic_hits else "no_semantic_match",
                used_in_reply=call.success,
                notes=list(call.notes),
            )
        )
    relationship_hits = payload.get("relationship_hits")
    if isinstance(relationship_hits, list):
        records.append(
            MemoryRetrievalRecord(
                query_text=query_text,
                backend=MemoryRetrievalBackend.RELATIONSHIP_RUNTIME,
                backend_detail="search_memory_output",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                run_id=run_id,
                selected_candidates=[
                    MemoryRetrievalCandidateRecord(
                        memory_id=str(item.get("memory_id")) if isinstance(item, dict) and item.get("memory_id") else None,
                        layer=MemoryLayer.RELATIONSHIP,
                        summary=str(item.get("summary") or ""),
                        reason=str(item.get("ranking_reason") or "relationship_hit"),
                        score=_float_or_none(item.get("ranking_score")) if isinstance(item, dict) else None,
                        source_refs=[str(item.get("source_ref"))] if isinstance(item, dict) and item.get("source_ref") else [],
                    )
                    for item in relationship_hits
                    if isinstance(item, dict)
                ],
                miss_reason=None if relationship_hits else "no_relationship_match",
                used_in_reply=call.success,
                notes=list(call.notes),
            )
        )
    procedural_hits = payload.get("procedural_hits")
    if isinstance(procedural_hits, list):
        records.append(
            MemoryRetrievalRecord(
                query_text=query_text,
                backend=MemoryRetrievalBackend.PROCEDURAL_MATCH,
                backend_detail="search_memory_output",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                run_id=run_id,
                selected_candidates=[
                    MemoryRetrievalCandidateRecord(
                        memory_id=str(item.get("memory_id")) if isinstance(item, dict) and item.get("memory_id") else None,
                        layer=MemoryLayer.PROCEDURAL,
                        summary=str(item.get("summary") or ""),
                        reason=str(item.get("ranking_reason") or "procedural_hit"),
                        score=_float_or_none(item.get("ranking_score")) if isinstance(item, dict) else None,
                        source_refs=[str(item.get("source_ref"))] if isinstance(item, dict) and item.get("source_ref") else [],
                        session_id=str(item.get("session_id")) if isinstance(item, dict) and item.get("session_id") else None,
                    )
                    for item in procedural_hits
                    if isinstance(item, dict)
                ],
                miss_reason=None if procedural_hits else "no_procedural_match",
                used_in_reply=call.success,
                notes=list(call.notes),
            )
        )
    perception_facts = payload.get("perception_facts")
    if isinstance(perception_facts, list) and perception_facts:
        records.append(
            MemoryRetrievalRecord(
                query_text=query_text,
                backend=MemoryRetrievalBackend.PERCEPTION_CONTEXT,
                backend_detail="search_memory_output",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                run_id=run_id,
                selected_candidates=[
                    MemoryRetrievalCandidateRecord(
                        memory_id=str(item.get("fact_id")) if isinstance(item, dict) and item.get("fact_id") else None,
                        summary=str(item.get("summary") or item.get("value") or item.get("fact_type") or ""),
                        reason="perception_fact",
                        score=_float_or_none(item.get("confidence")) if isinstance(item, dict) else None,
                        source_refs=[str(item.get("source_ref"))] if isinstance(item, dict) and item.get("source_ref") else [],
                    )
                    for item in perception_facts
                    if isinstance(item, dict)
                ],
                used_in_reply=call.success,
                notes=list(call.notes),
            )
        )
    return records


def _backend_for_tool_name(tool_name: str) -> MemoryRetrievalBackend | None:
    return {
        "profile_memory_lookup": MemoryRetrievalBackend.PROFILE_SCAN,
        "prior_session_lookup": MemoryRetrievalBackend.EPISODIC_KEYWORD,
        "perception_fact_lookup": MemoryRetrievalBackend.PERCEPTION_CONTEXT,
        "recent_session_digest": MemoryRetrievalBackend.EPISODIC_KEYWORD,
        "local_notes": MemoryRetrievalBackend.EPISODIC_KEYWORD,
        "personal_reminders": MemoryRetrievalBackend.EPISODIC_KEYWORD,
        "relationship_runtime": MemoryRetrievalBackend.RELATIONSHIP_RUNTIME,
        "today_context": MemoryRetrievalBackend.WORLD_STATE,
    }.get(tool_name)


def _candidates_from_metadata(metadata: dict[str, object], *, selected: bool) -> list[MemoryRetrievalCandidateRecord]:
    key = "selected_candidates" if selected else "rejected_candidates"
    raw = metadata.get(key)
    if isinstance(raw, list):
        items: list[MemoryRetrievalCandidateRecord] = []
        for value in raw:
            if not isinstance(value, dict):
                continue
            layer = value.get("layer")
            items.append(
                MemoryRetrievalCandidateRecord(
                    memory_id=str(value.get("memory_id")) if value.get("memory_id") else None,
                    layer=MemoryLayer(layer) if layer in {item.value for item in MemoryLayer} else None,
                    summary=str(value.get("summary") or ""),
                    reason=str(value.get("reason") or ""),
                    score=_float_or_none(value.get("score")),
                    source_refs=[str(item) for item in value.get("source_refs", [])] if isinstance(value.get("source_refs"), list) else [],
                    session_id=str(value.get("session_id")) if value.get("session_id") else None,
                    trace_id=str(value.get("trace_id")) if value.get("trace_id") else None,
                )
            )
        if items:
            return items

    derived_summary = str(metadata.get("matched_summary") or metadata.get("answer_text") or "")
    derived_ref = str(metadata.get("memory_id") or metadata.get("source_ref") or "")
    if selected and derived_summary:
        layer = metadata.get("memory_layer")
        return [
            MemoryRetrievalCandidateRecord(
                memory_id=(derived_ref if derived_ref else None),
                layer=MemoryLayer(layer) if layer in {item.value for item in MemoryLayer} else None,
                summary=derived_summary,
                reason=str(metadata.get("retrieval_reason") or "matched_memory"),
                source_refs=[derived_ref] if derived_ref else [],
                session_id=str(metadata.get("session_id")) if metadata.get("session_id") else None,
                trace_id=str(metadata.get("trace_id")) if metadata.get("trace_id") else None,
            )
        ]
    return []


def _miss_reason_from_metadata(metadata: dict[str, object]) -> str | None:
    if metadata.get("missing_prior_session"):
        return "no_prior_session_match"
    if metadata.get("empty_profile"):
        return "no_profile_memory"
    if metadata.get("snapshot_stale"):
        return "stale_perception_context"
    if metadata.get("fresh") is False:
        return "no_fresh_memory_context"
    return str(metadata.get("miss_reason")) if metadata.get("miss_reason") else None


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
