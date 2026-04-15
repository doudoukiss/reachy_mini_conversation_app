# Ecosystem Transfer Map — What Blink-AI Should Borrow

This file turns frontier lessons into concrete Blink-AI design guidance.

## 1. Agentic systems lessons

### MCP / tool-protocol ecosystems

Borrow:

- stable tool schemas
- strict host ↔ tool boundaries
- capability declaration instead of implicit assumptions
- versioned protocol thinking

Apply to Blink-AI as:

- typed internal tool envelopes
- explicit permission/effect metadata
- durable tool result records
- future MCP-compatible adapters where useful

Do **not** turn the repo into a protocol playground.
The product runtime still matters more than protocol purity.

### LangGraph / durable-state orchestration

Borrow:

- explicit state graphs
- resumability and checkpointing
- human intervention surfaces
- deterministic control structure around nondeterministic model behavior

Apply to Blink-AI as:

- stronger run lifecycle semantics
- pause/resume/abort at explicit boundaries
- durable hook execution records
- branch/retry visibility in traces

### Claude Code / skills, hooks, subagents

Borrow:

- project memory and persistent instructions
- skill files as reusable execution playbooks
- specialized subagents with bounded roles
- lifecycle hooks
- strong operator visibility

Apply to Blink-AI as:

- skill packages under `brain/skill_library`
- bounded subagents like `perception_analyst`, `dialogue_planner`, `memory_curator`, `safety_reviewer`
- hook surfaces such as `after_perception`, `before_reply`, `before_speak`, `after_turn`, `on_failure`

### Letta / memory-first architecture

Borrow:

- memory as a subsystem, not a prompt trick
- different memory classes with different policies
- persistent long-lived assistant identity

Apply to Blink-AI as:

- strict separation of profile, episodic, semantic, and world memory
- promotion/review/tombstone flows
- visible memory provenance and confidence

### Aider / SWE-agent / OpenHands / Browser Use

Borrow:

- environment interaction should be typed and inspectable
- agent/computer interface matters as much as model quality
- sandboxing and recovery need first-class treatment

Apply to Blink-AI as:

- treat webcam, mic, speaker, filesystem, browser, memory, and body commands as the Agent-Computer Interface
- keep result envelopes consistent
- keep operator auditability strong

## 2. Robotics and embodied-AI lessons

### LeRobot / Open X-Embodiment

Borrow:

- standardized episode/data thinking
- embodiment-agnostic dataset design
- modular hardware boundaries

Apply to Blink-AI as:

- every meaningful interaction becomes an episode asset
- export should stay schema-versioned and future-convertible
- semantic body actions should stay embodiment-agnostic

### ALOHA / ACT

Borrow:

- teacher demonstration is a serious asset
- high-quality supervision matters more than theoretical elegance

Apply to Blink-AI as:

- teacher mode for reply, memory, scene, and embodiment corrections
- preference and correction data captured from real use

### OpenVLA / Octo / openpi

Borrow:

- keep a clean planner or policy adapter boundary
- separate high-level reasoning from low-level action execution
- prepare for future learned policies without centering the current repo on training

Apply to Blink-AI as:

- planner adapters stay clean
- research bundle inputs/outputs are versioned
- learned-policy experiments remain optional attachments, not the core runtime

### MuJoCo / Isaac Lab / Habitat / ManiSkill

Borrow:

- benchmark discipline
- replay discipline
- simulator/fixture separation from live runtime
- measurement over hype

Apply to Blink-AI as:

- deterministic benchmark packs
- fixture-based perception/body tests
- strict replay metrics and divergence inspection

## 3. What to adopt now vs later

### Adopt now

- Agent OS discipline
- typed tool protocol
- structured memory layers
- teacher mode
- episode/data standardization
- benchmark/replay rigor
- semantic embodiment compiler

### Adapt later

- MCP server/client interoperability beyond current internal tool protocol
- Open X / LeRobot-style export bridges
- richer policy adapters
- live multi-host deployment spine

### Defer for now

- full VLA training stack as the main repo center
- full-body locomotion/manipulation ambition
- simulation-heavy research work that outruns the product/runtime needs

## 4. Design consequence

Blink-AI becomes world-advanced by combining:

- the **runtime discipline** of strong agent systems
- the **data/eval discipline** of strong embodied-AI systems
- a **semantic embodiment boundary** suited to the actual social-head hardware

That is the correct interpretation of “world-class” for this project.
