Read `AGENTS.md`, `README.md`, `PLAN.md`, `docs/current_direction.md`, `docs/architecture.md`, and the new Stage 6A code first.

Then implement **Stage 6B — Tool Gateway and Connector Runtime**.

## Project context

Blink-AI now needs a real connector platform on top of the action substrate.

The goal is not to add random tools.
The goal is to add:
- capability discovery
- health/configuration visibility
- bounded execution through typed connectors
- an internal gateway that can later support MCP-style external skills without redesign

## What to build

1. Add a connector base interface and connector registry.
2. Add connector descriptors and health reporting.
3. Implement these connectors first:
   - reminders
   - notes
   - local files / workspace
   - calendar draft/query
4. Add an internal MCP-compatible adapter shape, even if the external bridge is still conservative or dry-run.
5. Surface connector health and capability metadata in:
   - runtime status
   - console APIs
   - CLI status output
6. Route action execution through the connector gateway where applicable.
7. Add tests for:
   - registry discovery
   - connector health publication
   - safe workspace-root handling
   - reminder/note/calendar behavior
   - connector degradation honesty

## Constraints

- No arbitrary unrestricted filesystem access.
- No hidden side effects.
- Keep connector boundaries small and typed.
- Do not require cloud services.
- Preserve existing venue knowledge and memory tools.

## Definition of done

- Blink-AI has a real connector gateway.
- At least three useful local connectors are live and tested.
- Connector status is operator-visible.
- The design is ready for future MCP-style expansion.

## Validation

Run:

```bash
uv run pytest
PYTHONPATH=src uv run python -m embodied_stack.sim.scenario_runner --dry-run
```

At the end, return:
- files changed
- connectors implemented
- connector health model
- new console/CLI surfaces
- remaining limitations
