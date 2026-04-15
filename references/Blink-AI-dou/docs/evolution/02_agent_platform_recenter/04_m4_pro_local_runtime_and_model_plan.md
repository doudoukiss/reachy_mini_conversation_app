# 04 — M4 Pro local runtime and model plan

This file is the implementation target for the local MacBook Pro M4 Pro with 24 GB unified memory.

## Design principle

Do not try to load the biggest possible model all the time.

The right approach is:
- small always-on services
- medium local models when needed
- cloud fallback for best-quality demo mode
- explicit profile switching
- lazy model loading where useful

## Recommended runtime profiles

### Profile A — `cloud_best`
Use when:
- investor demos
- highest-quality natural discussion
- best multimodal understanding
- lowest risk of unimpressive replies

Pipeline:
- local webcam capture
- local mic capture
- local STT or cloud speech path
- cloud reasoning / multimodal model
- local memory / retrieval / policy / body compiler
- local speaker playback
- virtual body or bodyless mode

### Profile B — `local_balanced`
Use when:
- everyday development
- local privacy
- moderate latency
- no reliance on cloud for the core loop

Pipeline:
- local webcam capture
- local STT
- local VLM or lightweight scene analyzer
- local text model
- local embeddings
- local TTS
- local world model and memory

### Profile C — `local_fast`
Use when:
- battery-sensitive or latency-sensitive testing
- quick iteration
- small-model behavior testing

Pipeline:
- local STT
- small local text model
- lightweight perception facts
- macOS `say` or a fast local TTS
- bodyless or virtual body

### Profile D — `offline_safe`
Use when:
- everything intelligent is unavailable
- demo fallback
- robustness testing

Pipeline:
- typed/manual fallback
- deterministic tools
- rule-based replies
- safe embodied fallback

## Recommended backend split

### Speech-to-text
Preferred:
- Apple-Silicon-friendly local STT first
- streaming or chunked transcription
- fallback to typed input when unavailable

### Text reasoning
Preferred shape:
- local model router supporting at least:
  - MLX backend
  - Ollama backend
  - cloud backend
  - deterministic fallback backend

### Vision understanding
Preferred shape:
- two-layer approach

Layer 1:
- always-on lightweight perception
- faces / presence / pose / coarse attention / visible text candidates / scene motion

Layer 2:
- on-demand semantic frame analysis
- use a local VLM or cloud multimodal model only when needed

### Embeddings / retrieval
Preferred:
- local embedding model
- small enough to stay resident
- used for:
  - venue docs
  - user memory
  - episode summaries
  - operator notes
  - research snippets

### Text-to-speech
Short term:
- macOS `say` is acceptable
- it is already available, low friction, and good enough for development

Upgrade path:
- local neural TTS backend
- optional streaming audio output
- configurable voice identity

## Model guidance for this hardware

### Good fits now
- small-to-medium local text models
- small local vision-language models
- local embedding model
- local STT
- fast local TTS
- cloud best-quality option for demos

### Fits but should be used carefully
- larger 20B-ish local text reasoning models
- larger multimodal models loaded on demand, not always resident

### Not the right primary plan on this machine
- full frontier robot foundation models
- heavy simulation-first stacks as the default runtime
- large VLA training or serious fine-tuning pipelines

## Practical concurrency policy

Because 24 GB unified memory is shared by:
- the OS
- browser / editor / terminal
- webcam
- audio
- Python services
- embeddings
- LLM / VLM workers

Blink-AI should use explicit worker policy:

- one heavy reasoning model worker at a time
- one lightweight embedding worker resident
- one STT worker resident
- VLM loaded on demand or kept small
- TTS isolated from LLM memory pressure
- clear warm-start / unload logic

## Product judgement

The best local product on this machine is **not**:
"run the largest frontier multimodal model locally"

It is:
"run a well-orchestrated stack of local services and medium models with strong fallback"

That is enough for:
- natural discussion
- scene-grounded replies
- memory continuity
- useful daily interaction
- compelling demos
