# Stage 3 — Memory, Episode Flywheel, and Teacher Mode

## Status

Baseline implemented.

The repo now has:

- layered memory with policy and review metadata
- `blink_episode/v2`
- teacher annotations attached to episodes, traces, and memory workflows
- benchmark runner support built on exported artifacts

## What landed

- explicit profile, episodic, semantic, and world-state distinctions
- memory actions and reviews with provenance, reason codes, and tombstone/correction semantics
- operator memory review/correction/delete flows
- teacher-mode annotations persisted as first-class records
- reusable local episode bundles with memory actions, reviews, scene facts, and teacher data

## Remaining hardening work

- keep improving memory-promotion policy quality instead of letting the store become a loose catch-all
- continue building richer benchmark corpora from exported episodes instead of overloading pytest with scenario-only coverage
- improve review-debt visibility and teacher workflow ergonomics in the operator UI
- keep privacy-aware local-first export discipline as research-style artifacts expand

## Maintained acceptance truth

Stage 3 is no longer about adding a basic episode export.
It is about improving the quality of:

- memory policy
- teacher feedback
- benchmark coverage
- exported evidence usefulness
