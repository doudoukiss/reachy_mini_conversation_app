# Human Acceptance

This is the practical 20 to 30 minute human acceptance pass for the current Blink-AI milestone.

Use it when you want to answer one honest question:

- does Blink-AI feel coherent enough for a real person to judge?

This guide is for the terminal-first product path. The browser console and optional character shell are part of the session, but they support the same companion runtime rather than replacing it.

## Start Here

Run the primary product surface with the secondary browser/operator surface available:

```bash
uv run local-companion --open-console
```

Keep these commands nearby during the whole session:

- `/help`
- `/status`
- `/actions status`
- `/actions approvals`
- `/interrupt`
- `/silence`
- `/silence off`
- `/quit`

Use these stop and reset rules:

- stop current speech: `/interrupt`
- stop proactive re-engagement: `/silence`
- re-enable initiative: `/silence off`
- stop the whole session: `/quit`
- start a clean new session: restart `uv run local-companion` with a new `--session-id`
- if the browser/operator surface is stuck: `uv run blink-appliance --reset-runtime`

## What The Tester Should Be Able To Tell

Before scoring the experience, confirm the tester can answer these without repo archaeology:

- what mode Blink-AI is in
- whether the terminal or browser is the primary surface right now
- whether Blink-AI is listening, thinking, speaking, waiting, degraded, or silenced
- whether an approval is pending and why
- how to stop speech, stop initiative, quit, and start fresh

## Session Checklist

Use this checklist in order. A full pass should take about 20 to 30 minutes.

- `startup`
  - Launch `uv run local-companion --open-console`.
  - Confirm the terminal clearly shows the active profile, context, audio mode, device state, and the `/help`, `/status`, `/console`, `/presence`, `/interrupt`, `/silence`, and `/quit` affordances.
  - Confirm the tester can identify the current mode from startup text alone.
- `terminal-first conversation`
  - Send 3 to 5 plain typed turns in the terminal.
  - Confirm replies feel like the same companion across turns, not stateless chat completions.
  - Confirm `/status` shows what Blink-AI is doing in a readable way.
- `console interaction`
  - Open `/console` if it did not open automatically.
  - Confirm the console reflects the same session, not a separate product identity.
  - Confirm the tester can find live runtime status, presence state, Action Center, and reset controls.
- `memory continuity`
  - Tell Blink-AI one explicit preference or fact.
  - Move to another topic for a few turns, then ask it to recall the earlier fact.
  - Confirm continuity is useful and bounded rather than creepy or overclaiming.
- `initiative behavior`
  - Leave a short pause after an open thread or reminder-worthy exchange.
  - Confirm initiative, if it happens, is sparse, grounded, and easy to silence.
  - Confirm `/silence` and `/silence off` behave clearly.
- `action approval behavior`
  - Trigger or inspect at least one approval path.
  - Confirm the tester can tell why Blink-AI asked for approval, what will happen if it is approved, and how to reject it.
  - Confirm terminal and console surfaces agree about approval state.
- `degraded mode clarity`
  - If camera, mic, speaker, or a model is degraded on this machine, confirm Blink-AI says so plainly.
  - Confirm the degraded path still leaves a usable typed terminal path when appropriate.
  - Confirm the tester can tell the difference between “slow”, “waiting”, and “degraded”.
- `shutdown and reset`
  - Stop an in-progress spoken reply with `/interrupt`.
  - Exit with `/quit`.
  - Restart with a fresh `--session-id` and confirm the tester can tell the session was reset intentionally.

## Scenario 1: Companion Chat Session

Use this to judge the baseline companion feel.

### Setup

- Start `uv run local-companion --open-console`
- Stay in the terminal for the first 10 minutes

### Script

1. Say: `I want to use Blink-AI as a daily terminal companion. Keep replies brief and practical.`
2. Say: `I'm planning a writing session later today.`
3. Say: `Before that, remind me that I prefer one concrete next step, not a long plan.`
4. Change topic briefly: `What can you help me with from the terminal-first path today?`
5. Return to the earlier thread: `What was my preferred planning style again?`
6. Pause for a moment and see whether Blink-AI re-engages tastefully.
7. Run `/status`.

### What Good Looks Like

- the conversation feels continuous
- the preference is recalled accurately or bounded honestly
- the initiative behavior is sparse and easy to understand
- `/status` confirms context, presence, initiative, and degraded state clearly

### Red Flags

- overfamiliar or fake-intimate language
- hidden personality drift
- no visible difference between idle, thinking, and degraded
- unclear silence or stop behavior

## Scenario 2: Helpful Task Session

Use this to judge practical usefulness plus approval clarity.

### Setup

- Keep the terminal primary
- Keep `/console` open as the secondary surface

### Script

1. Say: `Help me capture a short note and a reminder from this conversation.`
2. If Blink-AI suggests a reminder or note flow, follow it.
3. If an approval appears, inspect it in both places:
   - terminal: `/actions approvals`
   - browser: Action Center
4. Approve or reject it once.
5. Ask Blink-AI what happened next.
6. Run `/actions status`.

### What Good Looks Like

- Blink-AI stays conversational while the slow loop works
- if approval appears, the reason is understandable
- the Action Center and terminal agree about pending, approved, or rejected state
- the next step after approval or rejection is clear

### Red Flags

- approval appears with only an internal code and no human explanation
- the terminal makes the system feel dead while work is pending
- approval resolution is visible in one surface but ambiguous in the other

## Scenario 3: Interruption And Failure Session

Use this to judge failure honesty and recovery.

### Setup

- Use the same runtime
- If browser live voice is available on this machine, test it once
- If not, stay terminal-first and test interruption plus degraded reporting

### Script

1. Trigger one spoken or longer reply.
2. Interrupt it with `/interrupt` or browser barge-in.
3. If the machine already has a degraded device or permission state, surface it with `/status`.
4. If the browser console is open, confirm the live status and Action Center remain usable while degraded.
5. Use `/silence` and confirm initiative pauses.
6. Use `/silence off` and confirm it resumes.
7. Exit with `/quit`, then restart with a new `--session-id`.

### What Good Looks Like

- interruption is visible and does not wedge the runtime
- degraded state is explicit, not hidden behind silence
- typed use still works when richer paths are unavailable
- the tester knows how to stop, silence, quit, and restart cleanly

### Red Flags

- a failure makes Blink-AI feel dead instead of degraded
- the system keeps nudging after the tester asked it to be quiet
- reset behavior is unclear or feels state-corrupting

## Scoring Notes

Mark a session as acceptable only if all of these are true:

- the terminal-first path still feels like the hero surface
- the console helps rather than competing with the terminal
- memory continuity is useful and bounded
- initiative is tasteful or easy to silence
- approval behavior is understandable
- degraded behavior is honest
- stopping and resetting are obvious

If any of those fail, record the exact confusing line, unclear state, or missing instruction instead of summarizing it vaguely.
