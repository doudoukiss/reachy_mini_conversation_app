# 02 — Frontier ecosystem and repo map

This file ranks the external ecosystem by **immediate relevance** to Blink-AI in its current stage.

## Principle

The most relevant frontier repos are **not** the most viral humanoid demos.

For Blink-AI right now, the highest-ROI repositories are the ones that help with:

- real-time multimodal perception
- local model execution on Apple Silicon
- structured memory / retrieval
- robot data packaging
- generalized tool use
- later embodiment transfer

## Tier 1 — Must-study now

### LeRobot
Use for:
- robotics dataset structure
- reusable training/eval thinking
- future "bring your own hardware" integration shape
- future transition from demo episodes to learning data

Why it matters:
- It is the clearest open educational robotics stack for turning real robot interactions into reusable datasets and learning pipelines.

### Open X-Embodiment / RT-X
Use for:
- mental model of cross-embodiment data
- why data standardization matters more than flashy demos
- how embodiment differences should be abstracted

Why it matters:
- It teaches the long-term lesson that robot intelligence improves when data and embodiment interfaces are normalized.

### OpenVLA
Use for:
- language/vision/action unification ideas
- policy interface design
- action-space abstraction thinking

Why it matters:
- Not because Blink-AI should use OpenVLA now, but because it clarifies how modern embodied systems connect perception and action.

### Octo
Use for:
- clean generalist policy abstraction
- flexible observation/action thinking
- future fine-tuning mental model

### openpi
Use for:
- frontier open-weight robotics thinking
- action representation ideas
- reference point for what "serious" embodied foundation-model infrastructure looks like

### MediaPipe
Use for:
- real-time face, pose, hand, and landmark pipelines
- practical on-device perception components
- lightweight streaming perception on a laptop

Why it matters:
- Probably the fastest path to better live perception on the Mac.

### OpenCV
Use for:
- device capture
- frame transforms
- classical fallback perception
- image preprocessing
- debugging camera paths

Why it matters:
- It is still the boring backbone that makes many real systems actually work.

### MLX + MLX LM + MLX Whisper
Use for:
- Apple Silicon-native local inference
- local LLMs
- local STT
- experimentation with model profiles on the M4 Pro

Why it matters:
- This is the most directly relevant local intelligence ecosystem for the user’s hardware.

## Tier 2 — Strong inspiration, but not the first implementation dependency

### robomimic
Use for:
- learning from demonstrations mindset
- modular offline robot learning
- data/eval rigor

### Diffusion Policy
Use for:
- modern policy representation thinking
- understanding why action generation is a different problem from text generation

### ALOHA / Mobile ALOHA / ACT
Use for:
- teleoperation/data-collection flywheel ideas
- future data collection if Blink-AI later gains manipulators or richer physical control

### SmolVLA
Use for:
- consumer-hardware-friendly VLA thinking
- what a compact robotics model stack looks like

## Tier 3 — Later, hardware-heavier, or infrastructure-heavy

### Isaac Lab
Use for:
- sim-to-real workflows
- large-scale robot learning architecture
- future training workflows

Do not make it the default local development path now.

### Isaac ROS
Use for:
- future Jetson-side perception and ROS integration
- later low-latency edge modules

Do not make it the center of the current product.

### Habitat 3.0 / Habitat Lab
Use for:
- embodied evaluation at environment scale
- thinking about richer spatial environments
- future navigation or egocentric assistant work

### ManiSkill
Use for:
- manipulation learning and benchmark thinking
- simulation at scale

## Company-led frontier systems to study conceptually

### Gemini Robotics
Study for:
- embodied reasoning
- physical-agent framing
- perception + reasoning + tool use stack shape

### NVIDIA GR00T
Study for:
- system-level integration
- sim + real data + policy workflows
- humanoid frontier direction

### Figure Helix / similar company-led systems
Study for:
- what end-to-end embodied product ambition looks like
- why world models, data, and control abstractions matter

Do not use these as immediate implementation targets.

## Blink-AI-specific conclusion

For Blink-AI now, the best external combination is:

- MLX / MLX LM / MLX Whisper
- MediaPipe
- OpenCV
- LeRobot
- Embedding-based RAG tooling
- optional Ollama / llama.cpp compatibility
- future-facing inspiration from OpenVLA / Octo / openpi

That stack fits the current robot reality:
- expressive social head
- laptop-first intelligence
- no powered body for now
- need for live natural interaction rather than robot locomotion or dexterous manipulation
