from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import ValidationError

from embodied_stack.shared.models import (
    IncidentReasonCategory,
    IncidentUrgency,
    VenueFallbackInstruction,
    VenueFallbackScenario,
    VenueOperationsSnapshot,
    VenueScheduleWindow,
)


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "get",
    "hello",
    "help",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "please",
    "repeat",
    "show",
    "tell",
    "that",
    "the",
    "there",
    "to",
    "we",
    "what",
    "when",
    "where",
    "which",
    "with",
    "you",
    "your",
}


@dataclass
class VenueFAQEntry:
    entry_id: str
    question: str
    answer: str
    aliases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_ref: str = ""


@dataclass
class VenueEventEntry:
    event_id: str
    title: str
    start_at: datetime
    end_at: datetime | None = None
    location_key: str | None = None
    location_label: str | None = None
    summary: str = ""
    aliases: list[str] = field(default_factory=list)
    source_ref: str = ""


@dataclass
class VenueLocationEntry:
    location_key: str
    title: str
    floor: str
    directions: str
    aliases: list[str] = field(default_factory=list)
    visible_signage: list[str] = field(default_factory=list)
    nearby_landmarks: list[str] = field(default_factory=list)
    source_ref: str = ""


@dataclass
class VenueStaffContact:
    contact_key: str
    name: str
    role: str
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    aliases: list[str] = field(default_factory=list)
    source_ref: str = ""


@dataclass
class VenueDocument:
    doc_id: str
    title: str
    text: str
    source_ref: str = ""


@dataclass
class VenueLookupResult:
    answer_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    memory_updates: dict[str, str] = field(default_factory=dict)


@dataclass
class VenueKnowledge:
    site_name: str = "Demo Community Center"
    timezone: str | None = None
    summary: str | None = None
    hours_summary: str | None = None
    operations: VenueOperationsSnapshot = field(default_factory=VenueOperationsSnapshot)
    faqs: list[VenueFAQEntry] = field(default_factory=list)
    events: list[VenueEventEntry] = field(default_factory=list)
    locations: dict[str, VenueLocationEntry] = field(default_factory=dict)
    staff_contacts: list[VenueStaffContact] = field(default_factory=list)
    documents: list[VenueDocument] = field(default_factory=list)
    loaded_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    content_dir: str | None = None
    site_source_ref: str | None = None

    @classmethod
    def from_directory(cls, content_dir: str | Path | None) -> VenueKnowledge:
        knowledge = cls(content_dir=str(content_dir) if content_dir else None)
        if content_dir is None:
            knowledge.warnings.append("venue_content_dir_missing")
            return knowledge

        root = Path(content_dir)
        if not root.exists():
            knowledge.warnings.append(f"venue_content_dir_not_found:{root}")
            return knowledge

        fatal_errors: list[str] = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative_ref = str(path.relative_to(root))
            suffix = path.suffix.lower()
            try:
                if suffix in {".yaml", ".yml", ".json"}:
                    payload = _load_structured_file(path)
                    knowledge._ingest_structured(path, relative_ref, payload)
                elif suffix == ".csv":
                    knowledge._ingest_csv(path, relative_ref)
                elif suffix == ".txt":
                    knowledge._ingest_text(path, relative_ref)
                elif suffix == ".md":
                    knowledge._ingest_markdown(path, relative_ref)
                elif suffix == ".ics":
                    knowledge._ingest_ics(path, relative_ref)
                else:
                    continue
                knowledge.loaded_files.append(relative_ref)
            except Exception as exc:  # pragma: no cover - defensive safety path
                message = f"ingest_failed:{relative_ref}:{exc}"
                if path.stem.lower() in {"site", "venue", "metadata"}:
                    fatal_errors.append(message)
                else:
                    knowledge.warnings.append(message)

        knowledge._normalize_event_timezones()
        knowledge.events.sort(key=lambda item: item.start_at)
        validation_errors = knowledge._validate_operations_references()
        if validation_errors:
            fatal_errors.extend(validation_errors)
        if fatal_errors:
            raise ValueError("; ".join(fatal_errors))
        return knowledge

    def overview(self) -> str:
        parts = [f"Site: {self.site_name}."]
        if self.summary:
            parts.append(self.summary)
        if self.hours_summary:
            parts.append(f"Hours: {self.hours_summary}.")
        operations_summary = self.operations_overview()
        if operations_summary:
            parts.append(operations_summary)
        parts.append(
            f"Imported venue pack has {len(self.locations)} locations, {len(self.events)} events, {len(self.faqs)} FAQs, and {len(self.staff_contacts)} staff contacts."
        )
        if self.warnings:
            parts.append(f"Warnings: {', '.join(self.warnings[:3])}.")
        return " ".join(parts)

    def operations_overview(self) -> str:
        parts: list[str] = []
        quiet_count = len(self.operations.quiet_hours)
        if quiet_count:
            parts.append(f"Quiet-hours windows configured: {quiet_count}.")
        if self.operations.proactive_greeting_policy.enabled:
            parts.append("Auto-greet is enabled.")
        else:
            parts.append("Auto-greet is disabled.")
        if self.operations.announcement_policy.proactive_suggestions:
            parts.append(
                f"Bounded proactive suggestions: {len(self.operations.announcement_policy.proactive_suggestions)}."
            )
        if self.operations.accessibility_notes:
            parts.append(f"Accessibility notes: {len(self.operations.accessibility_notes)}.")
        return " ".join(parts)

    def fallback_instruction(self, scenario: VenueFallbackScenario) -> VenueFallbackInstruction | None:
        return next((item for item in self.operations.fallback_instructions if item.scenario == scenario), None)

    def escalation_rule_for_text(self, text: str) -> dict[str, str] | None:
        lowered = text.lower().strip()
        for rule in self.operations.escalation_policy_overrides.keyword_rules:
            if any(keyword in lowered for keyword in rule.match_any):
                result = {
                    "reason_category": rule.reason_category.value,
                    "urgency": rule.urgency.value,
                }
                if rule.staff_contact_key:
                    result["staff_contact_key"] = rule.staff_contact_key
                if rule.note:
                    result["policy_note"] = rule.note
                return result
        return None

    def default_staff_contact_key_for(self, reason_category: IncidentReasonCategory) -> str | None:
        overrides = self.operations.escalation_policy_overrides
        if reason_category == IncidentReasonCategory.ACCESSIBILITY and overrides.accessibility_staff_contact_key:
            return overrides.accessibility_staff_contact_key
        return overrides.default_staff_contact_key

    def lookup_faq(self, query: str) -> VenueLookupResult | None:
        best = self._best_faq_match(query)
        if best is not None:
            return VenueLookupResult(
                answer_text=best.answer,
                metadata={"source_refs": [best.source_ref], "faq_key": best.entry_id, "site_name": self.site_name},
                notes=[f"venue_faq_match:{best.entry_id}"],
                memory_updates={"last_topic": best.entry_id},
            )

        if _looks_like_wayfinding_query(query):
            return None

        doc_match = self._best_document_match(query)
        if doc_match is None:
            return None

        return VenueLookupResult(
            answer_text=doc_match[1],
            metadata={"source_refs": [doc_match[0].source_ref], "doc_id": doc_match[0].doc_id, "site_name": self.site_name},
            notes=[f"venue_doc_match:{doc_match[0].doc_id}"],
            memory_updates={"last_topic": "venue_info"},
        )

    def lookup_events(self, query: str, *, last_event_id: str | None = None) -> VenueLookupResult | None:
        lowered = query.lower().strip()
        if not self.events:
            return None

        if any(keyword in lowered for keyword in ("events", "schedule", "this week", "happening", "calendar")):
            selected = self.events[:4]
            summary = ", ".join(
                f"{item.title} on {item.start_at.strftime('%A, %B %-d')} at {item.start_at.strftime('%-I:%M %p')}"
                for item in selected
            )
            return VenueLookupResult(
                answer_text=f"This week at the community center: {summary}.",
                metadata={"event_ids": [item.event_id for item in selected], "source_refs": sorted({item.source_ref for item in selected})},
                notes=["venue_events_summary"],
                memory_updates={"last_topic": "events", "last_event_id": selected[0].event_id},
            )

        named_matches = [event for event in self.events if _score_text_match(lowered, [event.title, *event.aliases]) >= 2]
        if named_matches and any(keyword in lowered for keyword in ("time", "start", "when")):
            event = named_matches[0]
            location_text = event.location_label or "the listed venue space"
            return VenueLookupResult(
                answer_text=(
                    f"{event.title} starts on {event.start_at.strftime('%A, %B %-d')} at "
                    f"{event.start_at.strftime('%-I:%M %p')} in {location_text}."
                ),
                metadata={"event_id": event.event_id, "source_refs": [event.source_ref], "location_key": event.location_key},
                notes=[f"venue_event_match:{event.event_id}"],
                memory_updates={"last_topic": "events", "last_event_id": event.event_id},
            )

        if last_event_id and any(keyword in lowered for keyword in ("what time", "when does that start", "when is that", "where is that")):
            event = next((item for item in self.events if item.event_id == last_event_id), None)
            if event is not None:
                location_text = event.location_label or "the listed venue space"
                return VenueLookupResult(
                    answer_text=(
                        f"{event.title} starts on {event.start_at.strftime('%A, %B %-d')} at "
                        f"{event.start_at.strftime('%-I:%M %p')} in {location_text}."
                    ),
                    metadata={"event_id": event.event_id, "source_refs": [event.source_ref], "location_key": event.location_key},
                    notes=["venue_event_memory_followup"],
                    memory_updates={"last_topic": "events", "last_event_id": event.event_id},
                )

        return None

    def lookup_location(
        self,
        query: str,
        *,
        last_location_key: str | None = None,
        visible_labels: list[str],
        attention_target: str | None,
    ) -> VenueLookupResult | None:
        lowered = query.lower().strip()
        matches = self._matching_locations(lowered)

        if not matches and last_location_key and any(
            phrase in lowered for phrase in ("where is it", "how do i get there", "repeat that", "repeat how to get there", "where was that")
        ):
            follow_up = self.locations.get(last_location_key)
            if follow_up is None:
                return None
            return self._location_result(
                follow_up,
                note="venue_location_memory_followup",
                visible_labels=visible_labels,
                attention_target=attention_target,
            )

        if not matches:
            return None

        top_score = matches[0][0]
        top_locations = [item for score, item in matches if score == top_score]
        if len(top_locations) > 1 and len({item.directions for item in top_locations}) > 1:
            titles = ", ".join(item.title for item in top_locations[:2])
            return VenueLookupResult(
                answer_text=(
                    f"I have conflicting venue directions for {titles}. "
                    "I can keep the session visible for staff or repeat the nearest confirmed sign."
                ),
                metadata={"source_refs": sorted({item.source_ref for item in top_locations}), "conflict": True},
                notes=["venue_location_conflict"],
                memory_updates={"last_topic": "wayfinding_conflict"},
            )

        return self._location_result(
            top_locations[0],
            note=f"venue_location_match:{top_locations[0].location_key}",
            visible_labels=visible_labels,
            attention_target=attention_target,
        )

    def lookup_staff_contact(self, query: str) -> VenueLookupResult | None:
        lowered = query.lower().strip()
        if not self.staff_contacts:
            return None

        scored = [
            (_score_text_match(lowered, [contact.name, contact.role, *(contact.aliases or []), contact.notes or ""]), contact)
            for contact in self.staff_contacts
        ]
        scored = [item for item in scored if item[0] >= 2]
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        contact = scored[0][1]
        contact_bits = [contact.role]
        if contact.phone:
            contact_bits.append(contact.phone)
        if contact.email:
            contact_bits.append(contact.email)
        return VenueLookupResult(
            answer_text=(
                f"I can route this to {contact.name}, {contact.role}. "
                f"The best contact I have is {' | '.join(contact_bits)}."
            ),
            metadata={"source_refs": [contact.source_ref], "contact_key": contact.contact_key},
            notes=[f"venue_staff_match:{contact.contact_key}"],
            memory_updates={"last_topic": "operator_handoff", "operator_escalation": "requested"},
        )

    def _validate_operations_references(self) -> list[str]:
        errors: list[str] = []
        if self.operations.site_name == "Unknown Site":
            self.operations.site_name = self.site_name
        if self.operations.timezone is None:
            self.operations.timezone = self.timezone
        if not self.hours_summary and self.operations.opening_hours:
            self.hours_summary = _hours_summary_from_windows(self.operations.opening_hours)

        contact_keys = {item.contact_key for item in self.staff_contacts}
        location_keys = set(self.locations)

        overrides = self.operations.escalation_policy_overrides
        for contact_key in (
            overrides.default_staff_contact_key,
            overrides.accessibility_staff_contact_key,
        ):
            if contact_key and contact_key not in contact_keys:
                errors.append(f"invalid_operations_staff_contact:{contact_key}")

        for rule in overrides.keyword_rules:
            if rule.staff_contact_key and rule.staff_contact_key not in contact_keys:
                errors.append(f"invalid_operations_staff_contact:{rule.staff_contact_key}")

        for instruction in self.operations.fallback_instructions:
            if not instruction.visitor_message.strip():
                errors.append(f"invalid_fallback_instruction:{instruction.scenario.value}")

        for window in self.operations.closing_windows:
            if not any(day in opening.days for opening in self.operations.opening_hours for day in window.days):
                errors.append(f"closing_window_without_opening_hours:{window.label or ','.join(window.days)}")

        if "front_desk" not in location_keys and self.operations.announcement_policy.closing_prompt_text:
            self.warnings.append("closing_prompt_has_no_front_desk_reference")

        return errors

    def _normalize_event_timezones(self) -> None:
        timezone_name = self.operations.timezone or self.timezone
        if not timezone_name:
            return
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            self.warnings.append(f"invalid_timezone:{timezone_name}")
            return
        normalized: list[VenueEventEntry] = []
        for event in self.events:
            start_at = event.start_at if event.start_at.tzinfo else event.start_at.replace(tzinfo=tz)
            end_at = event.end_at if event.end_at is None or event.end_at.tzinfo else event.end_at.replace(tzinfo=tz)
            normalized.append(
                VenueEventEntry(
                    event_id=event.event_id,
                    title=event.title,
                    start_at=start_at,
                    end_at=end_at,
                    location_key=event.location_key,
                    location_label=event.location_label,
                    summary=event.summary,
                    aliases=list(event.aliases),
                    source_ref=event.source_ref,
                )
            )
        self.events = normalized

    def _best_faq_match(self, query: str) -> VenueFAQEntry | None:
        scored = [
            (_score_text_match(query, [item.question, *item.aliases, *item.tags, item.entry_id]), item)
            for item in self.faqs
        ]
        scored = [item for item in scored if item[0] >= 2]
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _matching_locations(self, query: str) -> list[tuple[int, VenueLocationEntry]]:
        scored = [
            (
                _score_text_match(
                    query,
                    [item.title, item.location_key.replace("_", " "), *item.aliases, *item.visible_signage, *item.nearby_landmarks],
                ),
                item,
            )
            for item in self.locations.values()
        ]
        scored = [item for item in scored if item[0] >= 2]
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _best_document_match(self, query: str) -> tuple[VenueDocument, str] | None:
        scored = [
            (_score_text_match(query, [item.title, item.text]), item)
            for item in self.documents
        ]
        scored = [item for item in scored if item[0] >= 2]
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        doc = scored[0][1]
        return doc, _excerpt_for_query(doc.text, query)

    def _location_result(
        self,
        location: VenueLocationEntry,
        *,
        note: str,
        visible_labels: list[str],
        attention_target: str | None,
    ) -> VenueLookupResult:
        display_title = location.title.title() if location.title.islower() else location.title
        grounding = _best_visible_grounding(
            location=location,
            visible_labels=visible_labels,
            attention_target=attention_target,
        )
        answer = f"The {display_title} is on the {location.floor}. {location.directions}"
        notes = [note]
        metadata = {"location_key": location.location_key, "source_refs": [location.source_ref], "site_name": self.site_name}

        if grounding is not None:
            answer = f"I can currently ground {grounding}. {answer}"
            metadata["perception_grounding"] = grounding
            notes.append("perception_grounded_wayfinding")

        return VenueLookupResult(
            answer_text=answer,
            metadata=metadata,
            notes=notes,
            memory_updates={"last_topic": "wayfinding", "last_location": location.location_key},
        )

    def _ingest_structured(self, path: Path, relative_ref: str, payload: Any) -> None:
        stem = path.stem.lower()
        if stem in {"site", "venue", "metadata"} and isinstance(payload, dict):
            self.site_name = str(payload.get("site_name") or payload.get("name") or self.site_name)
            self.summary = str(payload.get("summary") or self.summary) if payload.get("summary") else self.summary
            self.hours_summary = str(payload.get("hours_summary") or self.hours_summary) if payload.get("hours_summary") else self.hours_summary
            self.timezone = str(payload.get("timezone") or self.timezone) if payload.get("timezone") else self.timezone
            self.site_source_ref = relative_ref
            self.operations = _build_operations_snapshot(
                payload=payload.get("operations"),
                site_name=self.site_name,
                timezone=self.timezone,
                source_ref=relative_ref,
            )
            return

        if "faq" in stem:
            self.faqs.extend(_structured_faq_entries(payload, relative_ref))
            return

        if any(token in stem for token in ("event", "schedule", "calendar")):
            self.events.extend(_structured_event_entries(payload, relative_ref))
            return

        if any(token in stem for token in ("room", "location")):
            for item in _structured_location_entries(payload, relative_ref):
                self.locations[item.location_key] = item
            return

        if any(token in stem for token in ("staff", "contact")):
            self.staff_contacts.extend(_structured_staff_entries(payload, relative_ref))
            return

    def _ingest_csv(self, path: Path, relative_ref: str) -> None:
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)

        stem = path.stem.lower()
        if any(token in stem for token in ("event", "schedule", "calendar")):
            self.events.extend(_structured_event_entries(rows, relative_ref))
            return

        if any(token in stem for token in ("room", "location")):
            for item in _structured_location_entries(rows, relative_ref):
                self.locations[item.location_key] = item

    def _ingest_text(self, path: Path, relative_ref: str) -> None:
        text = path.read_text(encoding="utf-8")
        stem = path.stem.lower()
        if any(token in stem for token in ("room", "location")):
            for item in _pipe_delimited_locations(text, relative_ref):
                self.locations[item.location_key] = item
            return

        if any(token in stem for token in ("staff", "contact")):
            self.staff_contacts.extend(_pipe_delimited_staff(text, relative_ref))
            return

        self.documents.append(
            VenueDocument(
                doc_id=_slugify(path.stem),
                title=path.stem.replace("_", " ").title(),
                text=text.strip(),
                source_ref=relative_ref,
            )
        )

    def _ingest_markdown(self, path: Path, relative_ref: str) -> None:
        text = path.read_text(encoding="utf-8")
        title = _markdown_title(text) or path.stem.replace("_", " ").title()
        self.documents.append(
            VenueDocument(
                doc_id=_slugify(path.stem),
                title=title,
                text=_strip_markdown(text),
                source_ref=relative_ref,
            )
        )

    def _ingest_ics(self, path: Path, relative_ref: str) -> None:
        self.events.extend(_parse_ics_events(path.read_text(encoding="utf-8"), relative_ref))


def _load_structured_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _build_operations_snapshot(
    *,
    payload: Any,
    site_name: str,
    timezone: str | None,
    source_ref: str,
) -> VenueOperationsSnapshot:
    if payload in (None, {}):
        return VenueOperationsSnapshot(site_name=site_name, timezone=timezone, source_ref=source_ref)
    if not isinstance(payload, dict):
        raise ValueError("operations must be a mapping")
    try:
        snapshot = VenueOperationsSnapshot.model_validate(
            {
                **payload,
                "site_name": site_name,
                "timezone": timezone,
                "source_ref": source_ref,
            }
        )
    except ValidationError as exc:
        raise ValueError(f"invalid site operations config: {exc}") from exc
    return snapshot


def _hours_summary_from_windows(windows: list[VenueScheduleWindow]) -> str:
    if not windows:
        return ""
    parts: list[str] = []
    for window in windows:
        day_label = ", ".join(day.title() for day in window.days)
        parts.append(
            f"{day_label} from {window.start_local.strftime('%-I:%M %p')} to {window.end_local.strftime('%-I:%M %p')}"
        )
    return "; ".join(parts)


def _looks_like_wayfinding_query(query: str) -> bool:
    lowered = query.lower().strip()
    return any(
        phrase in lowered
        for phrase in (
            "where is",
            "where are",
            "how do i get",
            "directions",
            "find the",
            "find ",
            "way to",
        )
    )


def _structured_faq_entries(payload: Any, source_ref: str) -> list[VenueFAQEntry]:
    rows: list[dict[str, Any]]
    if isinstance(payload, dict) and "items" in payload:
        rows = list(payload["items"])
    elif isinstance(payload, list):
        rows = list(payload)
    else:
        rows = []
    return [
        VenueFAQEntry(
            entry_id=str(item.get("key") or item.get("entry_id") or _slugify(str(item.get("question") or "faq"))),
            question=str(item.get("question") or item.get("title") or item.get("key") or "Venue FAQ"),
            answer=str(item.get("answer") or item.get("text") or ""),
            aliases=_split_list(item.get("aliases")),
            tags=_split_list(item.get("tags")),
            source_ref=source_ref,
        )
        for item in rows
        if isinstance(item, dict) and item.get("answer")
    ]


def _structured_event_entries(payload: Any, source_ref: str) -> list[VenueEventEntry]:
    rows: list[dict[str, Any]]
    if isinstance(payload, dict) and "items" in payload:
        rows = list(payload["items"])
    elif isinstance(payload, list):
        rows = list(payload)
    else:
        rows = []

    events: list[VenueEventEntry] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        start_at = _parse_datetime_value(item.get("start_at") or item.get("start") or _combine_date_time(item))
        if start_at is None:
            continue
        events.append(
            VenueEventEntry(
                event_id=str(item.get("event_id") or item.get("uid") or _slugify(str(item.get("title") or "event"))),
                title=str(item.get("title") or item.get("summary") or "Venue Event"),
                start_at=start_at,
                end_at=_parse_datetime_value(item.get("end_at") or item.get("end")),
                location_key=str(item.get("location_key")) if item.get("location_key") else None,
                location_label=str(item.get("location_label") or item.get("location") or item.get("room")) if item.get("location_label") or item.get("location") or item.get("room") else None,
                summary=str(item.get("summary") or item.get("description") or ""),
                aliases=_split_list(item.get("aliases") or item.get("tags")),
                source_ref=source_ref,
            )
        )
    return events


def _structured_location_entries(payload: Any, source_ref: str) -> list[VenueLocationEntry]:
    rows: list[dict[str, Any]]
    if isinstance(payload, dict) and "items" in payload:
        rows = list(payload["items"])
    elif isinstance(payload, list):
        rows = list(payload)
    else:
        rows = []
    return [
        VenueLocationEntry(
            location_key=str(item.get("location_key") or _slugify(str(item.get("title") or "location"))),
            title=str(item.get("title") or item.get("name") or "Venue Location"),
            floor=str(item.get("floor") or item.get("zone") or "the venue"),
            directions=str(item.get("directions") or ""),
            aliases=_split_list(item.get("aliases")),
            visible_signage=_split_list(item.get("visible_signage")),
            nearby_landmarks=_split_list(item.get("nearby_landmarks")),
            source_ref=source_ref,
        )
        for item in rows
        if isinstance(item, dict) and item.get("title")
    ]


def _structured_staff_entries(payload: Any, source_ref: str) -> list[VenueStaffContact]:
    rows: list[dict[str, Any]]
    if isinstance(payload, dict) and "items" in payload:
        rows = list(payload["items"])
    elif isinstance(payload, list):
        rows = list(payload)
    else:
        rows = []
    return [
        VenueStaffContact(
            contact_key=str(item.get("contact_key") or _slugify(str(item.get("name") or "contact"))),
            name=str(item.get("name") or "Venue Contact"),
            role=str(item.get("role") or "staff"),
            phone=str(item.get("phone")) if item.get("phone") else None,
            email=str(item.get("email")) if item.get("email") else None,
            notes=str(item.get("notes")) if item.get("notes") else None,
            aliases=_split_list(item.get("aliases")),
            source_ref=source_ref,
        )
        for item in rows
        if isinstance(item, dict) and item.get("name")
    ]


def _pipe_delimited_locations(text: str, source_ref: str) -> list[VenueLocationEntry]:
    items: list[VenueLocationEntry] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [item.strip() for item in stripped.split("|")]
        if len(parts) < 4:
            continue
        items.append(
            VenueLocationEntry(
                location_key=parts[0],
                title=parts[1],
                floor=parts[2],
                directions=parts[3],
                aliases=_split_list(parts[4] if len(parts) > 4 else ""),
                visible_signage=_split_list(parts[5] if len(parts) > 5 else ""),
                nearby_landmarks=_split_list(parts[6] if len(parts) > 6 else ""),
                source_ref=source_ref,
            )
        )
    return items


def _pipe_delimited_staff(text: str, source_ref: str) -> list[VenueStaffContact]:
    items: list[VenueStaffContact] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [item.strip() for item in stripped.split("|")]
        if len(parts) < 3:
            continue
        items.append(
            VenueStaffContact(
                contact_key=parts[0],
                name=parts[1],
                role=parts[2],
                phone=parts[3] if len(parts) > 3 and parts[3] else None,
                email=parts[4] if len(parts) > 4 and parts[4] else None,
                notes=parts[5] if len(parts) > 5 and parts[5] else None,
                aliases=_split_list(parts[6] if len(parts) > 6 else ""),
                source_ref=source_ref,
            )
        )
    return items


def _parse_ics_events(text: str, source_ref: str) -> list[VenueEventEntry]:
    lines = _unfold_ics_lines(text.splitlines())
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                blocks.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        raw_key, value = line.split(":", 1)
        key = raw_key.split(";", 1)[0]
        current[key] = value.strip()

    events: list[VenueEventEntry] = []
    for item in blocks:
        start_at = _parse_datetime_value(item.get("DTSTART"))
        if start_at is None:
            continue
        events.append(
            VenueEventEntry(
                event_id=item.get("UID", _slugify(item.get("SUMMARY", "ics-event"))),
                title=item.get("SUMMARY", "Imported Calendar Event"),
                start_at=start_at,
                end_at=_parse_datetime_value(item.get("DTEND")),
                location_label=item.get("LOCATION"),
                summary=item.get("DESCRIPTION", ""),
                source_ref=source_ref,
            )
        )
    return events


def _unfold_ics_lines(lines: list[str]) -> list[str]:
    unfolded: list[str] = []
    for line in lines:
        if line.startswith(" ") and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line.strip())
    return unfolded


def _combine_date_time(item: dict[str, Any]) -> str | None:
    event_date = item.get("event_date")
    start_time = item.get("start_time")
    if not event_date or not start_time:
        return None
    return f"{event_date}T{start_time}"


def _parse_datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        return datetime.strptime(text, "%Y%m%d")
    if re.fullmatch(r"\d{8}T\d{6}Z?", text):
        fmt = "%Y%m%dT%H%M%S" + ("Z" if text.endswith("Z") else "")
        if text.endswith("Z"):
            return datetime.strptime(text, "%Y%m%dT%H%M%SZ")
        return datetime.strptime(text, "%Y%m%dT%H%M%S")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _score_text_match(query: str, candidates: list[str]) -> int:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0
    best = 0
    query_text = " ".join(query_tokens)
    for candidate in candidates:
        candidate_text = str(candidate or "").lower().strip()
        if not candidate_text:
            continue
        if candidate_text in query or query in candidate_text:
            best = max(best, 10 + len(candidate_text.split()))
        candidate_tokens = _tokenize(candidate_text)
        overlap = len(query_tokens & candidate_tokens)
        best = max(best, overlap)
    return best


def _tokenize(text: str) -> set[str]:
    return {
        item
        for item in re.findall(r"[a-z0-9]+", text.lower())
        if len(item) > 1 and item not in STOPWORDS
    }


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in re.split(r"[,;/]", text) if item.strip()]


def _markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def _strip_markdown(text: str) -> str:
    cleaned = re.sub(r"`([^`]+)`", r"\1", text)
    cleaned = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", cleaned)
    cleaned = re.sub(r"[*_>#-]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _excerpt_for_query(text: str, query: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    query_tokens = _tokenize(query)
    best_sentence = ""
    best_score = 0
    for sentence in sentences:
        score = len(query_tokens & _tokenize(sentence))
        if score > best_score:
            best_score = score
            best_sentence = sentence.strip()
    return best_sentence or text[:220].strip()


def _best_visible_grounding(
    *,
    location: VenueLocationEntry,
    visible_labels: list[str],
    attention_target: str | None,
) -> str | None:
    candidates = [*(visible_labels or [])]
    if attention_target:
        candidates.append(attention_target)
    normalized = [item.strip() for item in candidates if item and item.strip()]
    for candidate in normalized:
        lowered = candidate.lower()
        if location.title.lower() in lowered:
            return f"the sign or label '{candidate}'"
        if any(sign.lower() in lowered or lowered in sign.lower() for sign in location.visible_signage):
            return f"the visible sign '{candidate}'"
        if any(landmark.lower() in lowered or lowered in landmark.lower() for landmark in location.nearby_landmarks):
            return f"the nearby landmark '{candidate}'"
    return None


def _slugify(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return lowered or "item"
