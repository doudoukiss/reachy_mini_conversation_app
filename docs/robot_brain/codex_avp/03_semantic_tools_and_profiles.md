# Codex AVP prompt 03 — replace default tools with semantic tools

Implement the semantic tool layer.

## Goal

Stop making the default profile depend on Reachy-specific tools and move to a semantic robot-brain tool vocabulary.

## Create these files

- `src/reachy_mini_conversation_app/tools/observe_scene.py`
- `src/reachy_mini_conversation_app/tools/report_robot_status.py`
- `src/reachy_mini_conversation_app/tools/orient_attention.py`
- `src/reachy_mini_conversation_app/tools/set_attention_mode.py`
- `src/reachy_mini_conversation_app/tools/set_expression_state.py`
- `src/reachy_mini_conversation_app/tools/perform_motif.py`
- `src/reachy_mini_conversation_app/tools/stop_behavior.py`
- `src/reachy_mini_conversation_app/tools/go_neutral.py`
- `profiles/robot_brain_default/instructions.txt`
- `profiles/robot_brain_default/tools.txt`

## Modify these files

- `src/reachy_mini_conversation_app/prompts.py`
- `src/reachy_mini_conversation_app/tools/move_head.py`
- `src/reachy_mini_conversation_app/tools/head_tracking.py`
- `src/reachy_mini_conversation_app/tools/play_emotion.py`
- `src/reachy_mini_conversation_app/tools/dance.py`
- `profiles/default/tools.txt` only if you intentionally want to switch the default profile immediately

## Required implementation details

### 1. Semantic tools

Each new tool must call `robot_runtime` with typed semantic actions, not Reachy SDK calls.

### 2. Capability-aware descriptions

The new tools should derive their allowed values or descriptive text from the robot capability catalog where practical.

At minimum:

- `set_expression_state` should mention the currently available persistent states
- `perform_motif` should mention the currently available motifs
- `set_attention_mode` should mention available attention modes

### 3. Compatibility wrappers

Keep the current legacy tools, but make them wrappers around semantic actions where possible.

Examples:

- `move_head` -> `orient_attention`
- `head_tracking` -> `set_attention_mode(face_tracking/disabled)`

For Reachy-only legacy tools like `dance`, return a clear unsupported result when the current backend is not Reachy.

### 4. New production profile

Create `profiles/robot_brain_default/` with instructions that:

- describe the robot as a semantic-action system
- avoid hard-coded Reachy affordances
- explicitly mention mock/preview/live execution modes
- tell the model to prefer semantic actions over improvised motion descriptions

### 5. Prompt augmentation

Update prompt/session assembly so the model receives a concise runtime capability summary on session start or prompt assembly.

## Tests to add

- semantic tool execution against `MockRobotAdapter`
- capability-aware description tests
- compatibility wrapper tests
- profile loading test for `robot_brain_default`

## Acceptance criteria

- the app has a clean semantic tool set
- the new profile can run entirely in mock mode
- legacy tools no longer force the architecture to stay Reachy-specific
