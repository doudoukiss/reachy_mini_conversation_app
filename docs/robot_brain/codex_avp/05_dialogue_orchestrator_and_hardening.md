# Codex AVP prompt 05 — extract shared dialogue orchestration and harden the production path

Implement the maintainability and production-hardening pass.

## Goal

Reduce backend drift and add production controls around the robot-brain path.

## Create these files

- `src/reachy_mini_conversation_app/dialogue/__init__.py`
- `src/reachy_mini_conversation_app/dialogue/backend.py`
- `src/reachy_mini_conversation_app/dialogue/events.py`
- `src/reachy_mini_conversation_app/dialogue/orchestrator.py`

## Modify these files

- `src/reachy_mini_conversation_app/openai_realtime.py`
- `src/reachy_mini_conversation_app/gemini_live.py`
- your local Llama backend file, if present in the branch
- `src/reachy_mini_conversation_app/tools/core_tools.py`
- `src/reachy_mini_conversation_app/config.py`

## Required implementation details

### 1. Shared orchestration layer

Extract backend-neutral logic out of backend-specific handlers:

- tool-result reinjection
- idle behavior trigger policy
- transcript publication
- capability-aware context injection
- profile/personality application
- action-result narration

Leave backend-specific files responsible for transport/session semantics only.

### 2. External tool lockdown

Add a production-safe config option that disables arbitrary external tool loading unless explicitly enabled.

### 3. Mode and status grounding

Ensure the dialogue layer consistently tells the model and the user:

- current backend
- current robot backend
- execution mode (`mock`, `preview`, `live`)
- degraded or blocked health state where relevant

### 4. Structured logging

Add structured or at least consistently keyed logs for:

- tool invocation
- action execution
- adapter results
- degraded health
- blocked live action
- cancellation

### 5. Keep behavior incremental

Do not attempt to rewrite the entire realtime stack at once.
Introduce orchestration in a way that both OpenAI and Gemini can share it with minimal regression risk.

## Tests to add

- shared orchestrator tests
- backend adapter hook tests
- disabled external tools test
- mode/context grounding tests

## Acceptance criteria

- backend-specific files are thinner
- core interaction policy is shared
- production mode can fence external tools
- mock mode remains the default and easiest path
