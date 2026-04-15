# 04 — Runtime Architecture for the Always-On Local Companion

## Recommended architecture

```text
[ User in front of Mac / future robot ]
                |
                v
[ Continuous Interaction Supervisor ]
  - turn state
  - interruption
  - cooldowns
  - proactive eligibility
                |
      -------------------------
      |                       |
      v                       v
[ Voice Runtime ]       [ Scene Observer ]
  - mic capture         - cheap continuous watcher
  - STT                 - change detection
  - TTS                 - person/presence state
  - cancel              - scene trigger generation
      |                       |
      -----------     ---------
                v     v
          [ Trigger Engine ]
          - greet / wait / remind / observe / stay silent
                |
                v
            [ Agent Runtime ]
  - skills
  - hooks
  - typed tools
  - memory retrieval
  - safety review
  - embodied action plan
                |
      -------------------------
      |                       |
      v                       v
[ Local Memory Loop ]   [ Semantic Body Layer ]
  - session summary     - expression / gaze / gesture
  - semantic memory     - virtual body now
  - profile memory      - serial body later
  - retrieval quality
```

## Key design choice: two-tier perception

Do **not** run the multimodal LLM constantly on every frame.

Use two layers:

### Layer 1 — Cheap continuous watcher

Purpose:

- detect motion / presence changes
- detect whether a face is present
- estimate whether attention is toward the device
- detect whether the scene changed enough to justify a semantic refresh

Possible implementation directions:

- OpenCV-based change detection
- MediaPipe face / landmark tracking
- lightweight frame-difference + periodic landmark estimation

### Layer 2 — Heavy semantic scene interpretation

Purpose:

- generate scene summary
- extract visible text when needed
- identify relevant objects / anchors
- answer explicit scene questions

Use the local multimodal model only when:

- the cheap watcher says the scene changed
- the user asks a visual question
- the trigger engine needs grounding for a proactive action
- the current scene facts are stale

## Continuous voice loop design

The local companion should not depend on one-shot request flow alone.

Recommended voice states:

- `idle`
- `arming`
- `listening`
- `transcribing`
- `thinking`
- `speaking`
- `interrupted`
- `cooldown`
- `degraded_typed`

Important behaviors:

- user interruption should stop speech cleanly
- short acknowledgements should not start a full new turn unnecessarily
- silence should end listening without hanging forever
- typed input should remain available at all times

## Trigger engine responsibilities

The trigger engine decides whether Blink-AI should say something at all.

Inputs:

- scene events
- user speech activity
- session context
- memory / reminders
- current cooldowns
- quiet mode / operator overrides
- recent proactive history

Outputs:

- `speak_now`
- `wait`
- `observe_only`
- `refresh_scene`
- `remind`
- `ask_follow_up`
- `safe_idle`

## Memory loop responsibilities

The local memory loop should promote important information into the right layer.

### Episodic memory

Store compact summaries of sessions and major turns.

### Semantic memory

Store reusable facts that matter beyond a single turn.

### Profile memory

Store stable user preferences and durable personal context.

### Fresh perception facts

Store scene facts with timestamps and freshness boundaries.

## Claude-Code-style lesson to preserve

The existing Agent-OS work in the repo is already moving in the right direction.
The next phase should strengthen it by making the local companion loop operate through:

- explicit skills
- explicit hooks
- strict typed tools
- inspectable planning state
- persistent instruction files
- runtime specialization without monolithic prompts

## Body policy for this milestone

The body remains a semantic target only.

That means:

- virtual body is first-class
- bodyless mode is first-class
- serial body is optional and future-ready
- trigger / dialogue / memory logic must not depend on powered servos being present
