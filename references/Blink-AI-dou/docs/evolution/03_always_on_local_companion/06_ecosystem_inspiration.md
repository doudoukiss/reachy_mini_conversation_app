# 06 — Ecosystem Inspiration

This file is intentionally practical.
It lists the ecosystems most relevant to the **next** Blink-AI milestone, not the most glamorous robotics projects overall.

## Most relevant right now

### 1. Ollama

Use as inspiration for:

- local model serving
- tool calling
- structured responses
- model warm / unload policy
- local text + image reasoning under one API

Blink-AI should treat Ollama as the local model substrate, not just as an optional backend.

### 2. whisper.cpp

Use as inspiration for:

- Apple-Silicon-friendly local STT
- controlled local streaming / chunking
- lower-latency voice experimentation

This is especially relevant if the current Apple Speech path remains too conservative for the always-on loop.

### 3. Piper

Use as inspiration for:

- stronger private local TTS
- optional upgrade path beyond `say`

Keep `say` as the simple default if it is sufficient; Piper can be the next tier.

### 4. MediaPipe

Use as inspiration for:

- cheap real-time presence and landmark tracking
- fast visual pre-processing before expensive LLM calls

This is the best direction for the lightweight perception tier.

### 5. LeRobot

Use as inspiration for:

- hardware-agnostic robotics interfaces
- dataset thinking
- later data flywheel design

Not because Blink-AI needs to become LeRobot now, but because it reinforces good boundaries between runtime logic, embodiment, and future learning.

## Important but later

### OpenVLA / openpi / robomimic

Study these for:

- action representations
- robotics dataset design
- generalist embodied policies
- future training or fine-tuning ideas

Do **not** make them the center of this milestone.
The current milestone is about making Blink-AI a stronger local embodied companion, not about training a new robot policy.

### Isaac Lab / MuJoCo

Important later for:

- simulation
- training
- embodied benchmarks
- future hardware or control work

Again: valuable, but not the immediate bottleneck.

## Claude-Code-style design lessons to keep

The most useful lessons are architectural, not branding-driven:

- persistent instructions / memory files
- clear skill boundaries
- lifecycle hooks
- specialist roles / subagents
- strict tool schemas
- inspectable execution traces

Blink-AI already has much of this shape.
The next step is to make those ideas power a live local companion loop, not just a request/response planner.
