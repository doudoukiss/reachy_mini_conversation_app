# Appliance Intelligence Testing

Use this path when the priority is browser-side inspection, operator workflows, or console-driven conversation testing.

For normal daily companion use, start with [companion_quickstart.md](/Users/sonics/project/Blink-AI/docs/companion_quickstart.md) and `uv run local-companion`.

## Fastest Way To Start

Use one of these two commands:

```bash
uv run blink-appliance --open-console
uv run local-companion --open-console
```

Choose based on what you want:

- `uv run blink-appliance --open-console`
  - browser-first
  - best when you mainly want `/console`
  - no token prompt in appliance mode
- `uv run local-companion --open-console`
  - terminal-first plus browser console
  - best when you want both the interactive terminal loop and `/console`

## Recommended command for browser-first inspection

```bash
uv run blink-appliance --open-console
```

Expected behavior:

- the browser opens [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)
- appliance mode does not ask for an operator token
- `/setup` appears first only if `runtime/appliance_profile.json` has not been confirmed yet
- the companion remains usable even if camera readiness is degraded

If the full operator console is noisy or unstable in your browser, use the lightweight intelligence-testing page instead:

- [http://127.0.0.1:8000/companion-test](http://127.0.0.1:8000/companion-test)
- it keeps only the direct text-turn path, runtime summary, and a simple transcript
- it is meant specifically for testing conversation quality without the heavier operator surface

## What To Open In The Browser

- Main operator console:
  - [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)
- Lightweight intelligence-testing page:
  - [http://127.0.0.1:8000/companion-test](http://127.0.0.1:8000/companion-test)

Use `/console` when you want the full operator surface.
Use `/companion-test` when you only want quick browser-side conversation testing.

## How To Use `/console`

After `blink-appliance` opens:

1. If `/setup` appears first, finish the one-time appliance profile save.
2. Open or return to `/console`.
3. Use these sections first:
   - `Live Conversation`
   - `Perception Inputs`
   - `Action Center`
   - `Local Companion Readiness`

Practical testing flow:

1. Type a normal question in `Live Conversation` and send it.
2. If testing vision, enable the camera in `Perception Inputs`.
3. Ask a camera-grounded question such as `what can you see from the camera`.
4. If testing voice:
   - set `Voice Mode` to `browser_live` for text replies
   - set `Voice Mode` to `browser_live_macos_say` for spoken replies
   - click `Start Mic`, speak, then click `Stop Mic + Send`
5. If an action needs approval, use `Action Center` to inspect and resolve it.

Useful console behaviors:

- `Disable Camera` turns the console camera off immediately.
- `Capture Snapshot` grabs one current frame without keeping the camera on.
- `Brain Live Status` starts collapsed and can be expanded only when needed.
- `Action Center` is where approvals, blocked workflows, recent failures, and replayable artifacts live.

## How To Use `local-companion`

If you start:

```bash
uv run local-companion --open-console
```

you get both:

- the terminal conversation loop
- the browser console from the same runtime

Useful terminal commands:

- `/help`
- `/status`
- `/camera`
- `/listen`
- `/interrupt`
- `/console`
- `/export`
- `/actions status`
- `/actions approvals`
- `/actions approve <action_id> [note]`
- `/actions reject <action_id> [note]`
- `/actions history [limit]`
- `/actions connectors`
- `/actions workflows`
- `/actions bundle <bundle_id>`
- `/quit`

Use plain text directly in the terminal to talk to the companion without a slash command.

## When to use token auth instead

Token auth is still for direct non-appliance service launches such as:

- `uv run uvicorn embodied_stack.desktop.app:app --reload`
- tethered or multi-process local stacks

In those paths, use `OPERATOR_AUTH_TOKEN` or `runtime/operator_auth.json`.

## Quick troubleshooting

- Blank or flashing login page:
  - open [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console) directly
  - refresh once
  - avoid stale cached `/appliance/bootstrap/...` links from older runs
- Port conflict:
  - stop the old localhost service first, then rerun `uv run blink-appliance`
- Backend unavailable:
  - if Ollama is down, appliance mode should still open, but text quality will degrade honestly
- Camera degraded:
  - not a blocker for testing language intelligence unless you are explicitly testing vision behavior
- Console feels overwhelming:
  - use `/companion-test` for the minimal intelligence-testing surface
