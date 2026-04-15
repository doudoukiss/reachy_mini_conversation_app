# 03 — Local Ollama Profile Plan

## Goal

Make the current local installation a first-class, documented, and test-covered Blink-AI runtime profile.

Installed local stack:

- Ollama
- `qwen3.5:9b`
- `embeddinggemma:300m`

## Why this matters

Right now the repo supports Ollama, but the code and docs still reflect older generic defaults.
That creates friction, ambiguity, and weaker local testing.

Blink-AI should now have one canonical local profile for this machine.

## Canonical profile

Recommended profile name:

- `m4_pro_companion`

Or, if you prefer to stay aligned with the current naming scheme:

- keep `local_companion` as the user-facing profile
- add a concrete implementation preset under it for the M4 Pro machine

## Default backend choices for this profile

### Text reasoning

- backend: `ollama_text`
- model: `qwen3.5:9b`

### Vision understanding

- backend: `ollama_vision`
- model: `qwen3.5:9b`

Use the same model for text and image-grounded reasoning first.
That keeps the system simpler and more coherent.

### Embeddings

- backend: `ollama_embed`
- model: `embeddinggemma:300m`

### STT

Short-term default:

- current native Apple Speech path if available

Optional new path during this milestone:

- `whisper_cpp_local`

### TTS

Short-term default:

- `macos_say`

Optional later path:

- `piper_local`

## Specific improvements needed in code

### 1. Add first-class model defaults

Current config defaults still point at older generic models.
Refactor settings, `.env.example`, docs, and profile resolution so the M4 Pro local path has a clean default configuration.

### 2. Upgrade Ollama text backend from simple generate-only mode

The current local text path should move toward:

- `/api/chat`
- structured message history
- optional tool calling
- structured JSON replies when requested
- explicit `keep_alive`
- optional thinking mode

### 3. Add Ollama runtime health and warm-state tracking

Operator/runtime snapshot should show:

- model installed
- model reachable
- model warm vs cold
- last response latency
- unload / reload behavior
- active backend per subsystem

### 4. Add local memory-pressure policy

Do not keep too many medium models hot at once.
Preferred behavior:

- keep text model warm
- load vision path on demand
- keep embeddings cheap and persistent
- unload unused heavy models deliberately

### 5. Separate runtime profile from hardware profile

The model profile should stay independent from:

- bodyless / virtual / serial body
- future Mac Studio deployment
- future servo bring-up

## Recommended environment contract

Proposed target env surface:

```bash
BLINK_MODEL_PROFILE=local_companion
BLINK_BACKEND_PROFILE=local_balanced
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TEXT_MODEL=qwen3.5:9b
OLLAMA_VISION_MODEL=qwen3.5:9b
OLLAMA_EMBEDDING_MODEL=embeddinggemma:300m
BLINK_STT_BACKEND=apple_speech_local
BLINK_TTS_BACKEND=macos_say
```

Optional new env surface to add:

```bash
OLLAMA_KEEP_ALIVE=-1
OLLAMA_TEXT_THINKING=medium
OLLAMA_TOOL_CALLING=true
BLINK_LOCAL_MODEL_PREWARM=true
BLINK_MEMORY_COMPACTION_ENABLED=true
```

## Acceptance criteria

- the repo has a documented and tested canonical M4 Pro local companion profile
- Ollama text and vision use the same installed model cleanly
- embeddings use `embeddinggemma:300m`
- runtime status makes it obvious which local models are active
- the system remains honest and usable when Ollama is unavailable
