# Relationship Runtime

This document explains how Blink-AI handles bounded continuity for the local-first companion.

The relationship runtime is one subsystem inside the [character presence runtime](/Users/sonics/project/Blink-AI/docs/character_presence_runtime.md). It governs what continuity Blink-AI may store or surface while the broader `fast loop / slow loop` architecture handles presence, action timing, and expression.

The goal is useful continuity, not theatrical personality.

## Product stance

- Blink-AI should feel continuous across sessions.
- Blink-AI should not pretend to have hidden feelings, attachment, or human-like intimacy.
- Durable relationship memory should capture explicit preferences and open threads, not inferred vulnerability.
- Proactive behavior must stay bounded, respectful, and inspectable.

## Behavior categories

The companion runtime now treats these as explicit behavior categories instead of vague prompt tone:

- greeting / re-entry
- unresolved thread follow-up
- day planning
- observe-and-comment
- emotional tone bounds

These categories live in the first-party skill layer so routing is deterministic and visible in traces.

## Memory-layer model

Blink-AI now treats memory as five explicit layers with different write rules.

### Working memory

Working memory is the bounded live-turn layer.

It lives in active session state such as:

- the current conversation summary
- the current topic
- recent session-memory keys
- recent operator notes

It is useful for the current exchange, but it is not treated as durable relationship truth.

### Episodic memory

Episodic memory is the short-to-medium horizon continuity layer.

It includes:

- session compaction records
- reminders
- local notes
- session digests

This is still the main source for grounded recap and prior-session lookup.

### Semantic / profile memory

This is the durable personal-knowledge layer.

It includes:

- explicit names
- durable facts the user stated directly
- durable preferences
- reusable grounded summaries that survived policy checks

It should not contain:

- inferred emotional state
- vulnerability labels
- speculative attachment cues
- transient scene observations

### Relationship memory

Relationship memory is the bounded continuity runtime.

It now tracks:

- familiarity
- recurring topics
- promises and follow-ups
- open practical threads
- open emotional threads only when the user explicitly asked to revisit them
- preferred interaction style copied from explicit relationship preferences

Relationship memory is separate from profile memory on purpose. Profile memory stores stable facts and preferences. Relationship memory stores continuity state that can change, decay, resolve, or be deleted without pretending it is a permanent personality fact.

### Procedural memory

Procedural memory stores explicit working routines or interaction instructions such as:

- "for planning, give one step at a time"
- "when I ask for a recap, start with the open thread"

This layer is intentionally narrow. It is for reusable user-specific routines, not generic prompt stuffing.

## Governance rules

The memory runtime now applies explicit governance instead of treating every good retrieval candidate as durable memory.

- Do not auto-store everything. Session compaction stays bounded and semantic promotion is selective.
- Do not auto-store inferred vulnerability, diagnosis-like labels, or emotionally sensitive content unless the user explicitly requested a follow-up and the record stays in relationship memory.
- Do not promote transient scene observations into durable personal memory.
- Resolve explicit conflicts by preferring the newest explicit user correction over older implicit or derived memory.
- Let relationship threads decay. Open emotional threads stale faster than practical threads.
- Keep deletion obvious. Relationship and procedural records go through the same review, correction, tombstone, and action-log path as other memory layers.
- Keep retrieval context-aware. Profile and relationship context should appear when it helps the current turn, not on every turn.

## Relationship continuity rules

### Greeting / re-entry

- Returning-user greetings should be brief and practical.
- Stored names should be used sparingly, not on every turn.
- Re-entry should offer a useful next step such as resuming an open thread or planning the day.

### Unresolved thread follow-up

- Prefer the latest open reminder or session-digest follow-up.
- If no real open thread exists, say that plainly.
- Do not imply total recall.

### Day planning

- Use local reminders, recent digests, and local context first.
- Respect stored planning style when it was explicitly requested.
- Do not invent obligations outside the local runtime context.

### Observe-and-comment

- Treat observe-and-comment as current-scene grounding, not identity or relationship memory.
- Do not promote transient visual observations into durable user memory by default.

### Emotional tone bounds

- Honor explicit requests like brief, direct, calm, or less chatty.
- Do not convert an emotional moment into durable profile memory unless the user explicitly states a lasting preference.
- Do not answer distress with fake intimacy or dependency cues.

## Proactive behavior bounds

Blink-AI may surface follow-up behavior only when it is grounded in visible runtime state such as:

- open reminders
- session-digest follow-ups
- explicit shift/supervisor policy
- operator-visible workflow state

It should not:

- manufacture check-ins to create attachment
- repeatedly use the user's name for effect
- imply that it was thinking about the user when idle
- claim emotional persistence it does not have

## Inspectability

The relationship runtime should be visible through:

- working-memory state in `MemoryContextSnapshot.working_memory`
- `SkillActivationRecord.behavior_category`
- `UserMemoryRecord.relationship_profile`
- `RelationshipMemoryRecord`
- `MemoryStatus.relationship_continuity`
- terminal `/status`
- operator snapshot and `/console`
- reminders, notes, and session digests in local storage

## Contributor rule of thumb

When deciding whether to store or say something, prefer this ordering:

1. useful
2. explicit
3. inspectable
4. non-creepy

If a continuity idea fails any of those tests, it should probably stay out of durable memory and out of proactive behavior.
