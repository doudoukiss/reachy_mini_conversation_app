# Latency and Model Strategy

## Product requirement

If Blink-AI is supposed to feel like a companion or friend, conversation latency matters more than local-model purity.

A slow local loop destroys the product.
A slightly less local but fluid loop preserves the product.

## Decision

The flagship product mode should be:

## **Hybrid companion runtime**

Meaning:
- use the fastest reliable path for conversational turns
- keep memory, orchestration, and product logic local
- keep local-only mode as an important fallback and privacy option
- do not force the flagship experience to be limited by the slowest local configuration

## Recommended runtime tiers

### Tier 1 — `companion_live`
Default daily mode.
- cloud or fastest high-quality text reasoning backend
- local embeddings
- local memory store
- local STT/TTS when good enough
- local scene watcher with selective heavy analysis
- local action policy and approvals

### Tier 2 — `companion_private_local`
Strong local-first mode.
- local text model
- local embeddings
- local STT/TTS
- slower but private
- honest latency indicators

### Tier 3 — `offline_safe`
Guaranteed degraded mode.
- typed input
- deterministic retrieval
- rule-based fallback
- minimal local scene support

## Why this matters

The repo currently treats `m4_pro_companion` as the canonical local preset.
That is useful, but it should not be confused with the best possible **product mode**.

The best product mode is whatever makes Blink-AI feel alive and fluid.

## Technical changes to make

### 1. Stop treating one large multimodal local model as the default answer to every turn
Split the loop:
- conversational text path
- heavy vision path
- embeddings path
- STT path
- TTS path

### 2. Add explicit latency budgeting
Track and expose:
- STT latency
- reasoning latency
- TTS start latency
- end-to-end turn latency
- model cold-start vs warm-start

### 3. Warm local models intentionally
Use runtime prewarm and residency management.

### 4. Avoid heavy vision on every turn
Use a two-tier watcher:
- cheap observer always on
- expensive scene interpretation only when triggered or stale

### 5. Make the model router product-aware
The router should choose for:
- fluid conversation
- not just maximum locality

## Acceptance standard

Blink-AI should support a default mode where ordinary conversation feels fluid enough that the user wants to keep talking.
