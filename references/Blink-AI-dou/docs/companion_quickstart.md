# Companion Quickstart

This is the shortest path to using Blink-AI as a terminal-first personal companion.

## Daily-use command

```bash
uv run local-companion
```

That is the hero path.

It starts the same local runtime that owns memory, orchestration, perception, the Action Plane, and optional embodiment, but keeps the experience centered on the terminal.

## What to do first

After launch:

1. Type plain text directly to talk to Blink-AI.
2. Use `/listen` for one push-to-talk voice turn.
3. Use `/help` if you want the built-in command guide.
4. Use `/status` to inspect device health, latency, active profile, memory state, and model residency.
5. Use `/quit` to exit. The session exports automatically unless you started with `--no-export`.

## Commands worth remembering

- plain text
- `/listen`
- `/help`
- `/status`
- `/actions approvals`
- `/camera`
- `/open-mic on`
- `/open-mic off`
- `/interrupt`
- `/actions status`
- `/console`
- `/export`
- `/quit`

## Terminal vs browser

Use the terminal for daily conversation.

Use the browser only when you need operator surfaces such as:

- Action Center approvals
- workflow inspection
- restart-review items
- browser-task preview artifacts
- richer runtime inspection in `/console`

If you want that secondary surface from the same runtime, use:

```text
/console
```

Or launch with:

```bash
uv run local-companion --open-console
```

If you want a browser-first operator session instead of the terminal loop, use:

```bash
uv run blink-appliance
```

## Helpful flags

```bash
uv run local-companion --help
uv run local-companion --audio-mode open_mic
uv run local-companion --open-console
uv run local-companion --no-camera
uv run local-companion --no-speak
```

## Profile guidance

- default daily use: `companion_live`
- stronger all-local fallback: `m4_pro_companion`
- lower-memory local path: `local_fast`
- deterministic no-provider fallback: `offline_safe`

The default path keeps memory, orchestration, and product logic local while preferring lower-latency dialogue when configured.

## If something feels off

- Run `/status` first.
- Run `/actions approvals` if Blink-AI says a task is waiting on approval and you need to know why.
- Use `/interrupt` to stop the current spoken reply and `/silence` to pause proactive re-engagement.
- Use `/quit` to stop the current session cleanly.
- Start fresh with a new `--session-id` if you want a clean terminal session without resetting the whole runtime.
- If local devices or models look degraded, run `uv run local-companion-doctor`.
- If you need the browser operator surface, use `/console`.
- If you need certification-grade validation, run `uv run local-companion-certify`.
- If you need the full human acceptance walkthrough, use [human_acceptance.md](/Users/sonics/project/Blink-AI/docs/human_acceptance.md).
