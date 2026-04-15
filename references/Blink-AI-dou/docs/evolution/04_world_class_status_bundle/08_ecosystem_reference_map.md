# Ecosystem Reference Map

This file explains exactly what Blink-AI should borrow from major advanced open projects.

## Agentic systems

### MCP
Borrow:
- stable typed tool boundaries
- host/client/server thinking
- versioned protocol design

Do not copy blindly:
- every external integration as a remote dependency

Blink-AI use:
- internal tool protocol and future MCP-compatible adapters

### LangGraph
Borrow:
- explicit state graphs
- durable execution
- checkpoints
- resumability

Blink-AI use:
- Agent OS runs and checkpointing

### Claude Code
Borrow:
- skills
- hooks
- specialized subagents
- reusable markdown instruction surfaces

Blink-AI use:
- skill library, hook engine, subagent roles, instruction files

### Letta
Borrow:
- memory as architecture
- persistent state discipline
- memory mutation/retrieval policy

Blink-AI use:
- layered memory subsystem

### OpenAI Agents SDK
Borrow:
- small primitive set
- typed tools
- sessions
- tracing

Blink-AI use:
- minimal but disciplined agent runtime core

## Robotics and embodied AI

### LeRobot
Borrow:
- hardware-agnostic dataset thinking
- standard episode/dataset format mindset
- practical robotics tooling taste

Blink-AI use:
- episode schema and export design

### Open X-Embodiment / RT-X
Borrow:
- embodiment-normalized data mindset
- cross-embodiment abstraction discipline

Blink-AI use:
- semantic actions and normalized episode export

### ALOHA / ACT
Borrow:
- teacher-mode mindset
- demonstration capture importance
- low-cost real-data pragmatism

Blink-AI use:
- teacher mode and preference/demonstration collection

### OpenVLA / Octo / openpi
Borrow:
- clean boundary between reasoning/observation and action policy
- future planner/plugin design

Blink-AI use:
- future learned-policy interface, not immediate dependency

### MuJoCo / Isaac Lab / Habitat / ManiSkill / Genesis
Borrow:
- benchmark seriousness
- replay discipline
- simulation as infrastructure

Blink-AI use:
- replay harness and benchmark matrix first; heavier simulation later

## Hardware and servo ecosystem

### Feetech STS/SMS manuals
Borrow:
- keep hardware control cleanly below semantic actions
- support unique IDs, read/write, sync write/read, calibration, safety, and health feedback

Blink-AI use:
- serial bridge, bring-up tool, semantic compiler target

## Practical summary

Blink-AI should become:

- **Claude Code + LangGraph + Letta** for embodied local intelligence runtime,
- **MCP-like** for typed tools,
- **LeRobot/Open-X-minded** for data format and future learning,
- **ALOHA-minded** for teacher-mode data collection,
- **MuJoCo/Isaac/Habitat-minded** for evaluation discipline,
- **Feetech-safe** at the hardware boundary.
