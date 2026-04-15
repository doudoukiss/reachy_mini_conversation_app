# 06 — Repo change map

This file gives Codex a practical file-by-file strategy.

## Keep mostly intact

### `src/embodied_stack/body/`
Keep this package as the long-term embodiment boundary.

Preserve:
- profiles
- semantic compiler
- virtual preview
- serial protocol
- calibration tooling

Reason:
- this is already the correct adapter boundary for when the servo board returns.

### `src/embodied_stack/shared/`
Keep shared contracts, but extend carefully.

Reason:
- the protocol and typed contracts are a real asset.

### `pilot_site/`
Keep and expand.

Reason:
- site packs should become one of the core product assets.

## Refactor with care

### `src/embodied_stack/brain/`
The current `brain/` package should lose its monopoly over all intelligence behavior.

Keep:
- orchestrator concepts
- world model
- social executive
- shift supervisor
- venue knowledge
- operator flows

But split or relocate:
- model routing
- skill planning
- memory policies
- voice orchestration
- perception-grounded tool planning

## Add new packages

### `src/embodied_stack/intelligence/`
Suggested contents:
- `router.py`
- `profiles.py`
- `skills.py`
- `hooks.py`
- `subagents.py`
- `planner.py`
- `tool_registry.py`
- `policy_validator.py`
- `status.py`

### `src/embodied_stack/audio/`
Suggested contents:
- `capture.py`
- `vad.py`
- `transcription.py`
- `playback.py`
- `profiles.py`

### `src/embodied_stack/vision/`
Suggested contents:
- `camera.py`
- `sampler.py`
- `extractors.py`
- `scene_facts.py`
- `ocr.py`
- `profiles.py`

### `src/embodied_stack/memory2/` or extend `brain/memory*`
Suggested contents:
- `episodic.py`
- `semantic.py`
- `profile.py`
- `retrieval.py`
- `summaries.py`

### `src/embodied_stack/app/`
Suggested contents:
- a clean local desktop entrypoint
- lifecycle startup/shutdown
- device registry
- profile composition
- runtime dashboard data

## Demote in priority, do not delete

### `src/embodied_stack/edge/`
Keep it as:
- compatibility path
- future tethered deployment path
- future Jetson bridge

Do not let it dominate the near-term product direction.

## New config surfaces

Add or rationalize:
- `BLINK_MODE=cloud_best|local_balanced|local_fast|offline_safe`
- `BLINK_EMBODIMENT=bodyless|virtual_body|serial_body`
- `BLINK_STT_BACKEND=...`
- `BLINK_TTS_BACKEND=...`
- `BLINK_TEXT_BACKEND=...`
- `BLINK_VISION_BACKEND=...`
- `BLINK_EMBEDDING_BACKEND=...`
- `BLINK_CAMERA_DEVICE=...`
- `BLINK_MIC_DEVICE=...`

## Testing priorities

Add:
- native local conversation loop tests
- profile selection tests
- memory retrieval tests
- skill routing tests
- hook execution tests
- camera-grounding tests
- low-resource fallback tests

Keep:
- body compiler tests
- serial protocol tests
- operator console tests
- demo export tests
- world model tests

## Product rename suggestion for the phase

Internally refer to this phase as:

### `local_companion_runtime`

This keeps everyone focused on the actual goal.
