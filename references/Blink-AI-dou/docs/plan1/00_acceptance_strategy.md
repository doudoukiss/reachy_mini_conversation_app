# Acceptance Strategy for Blink-AI

## Why acceptance needs its own phase
For Blink-AI, implementation completion is not the same thing as product completion.
The highest-risk failures are often not syntax or obvious logic bugs. They are:
- latency regressions
- broken runtime state transitions
- memory weirdness
- over-eager initiative
- degraded-mode confusion
- fragile desktop/runtime integration
- unsafe action behavior
- embodiment drift between semantic intent and output surface

The uploaded JARVIS notes are especially useful here: they argue that the hardest parts are not isolated features, but a tightly coupled system involving realtime interaction, world grounding, long-term memory, role consistency, initiative timing, and safety governance. They also recommend separating the fast loop from the slow loop and strongly emphasize validation, verification, and cautious rollout. fileciteturn17file0 fileciteturn17file1

## The acceptance philosophy
Acceptance should proceed in five layers:

1. **Inventory and harness**
   Confirm what exists, what is supposed to exist, and what is covered by tests.

2. **Automated regression sweep**
   Run all existing unit/integration/eval suites and close obvious regressions.

3. **Failure injection and soak**
   Verify the system behaves acceptably when models, tools, permissions, and devices fail.

4. **Human acceptance**
   Run real terminal-first and console-first sessions and evaluate quality as a user would.

5. **Release candidate gate**
   Check documentation, runbooks, logs, traces, and known limitations before merging.

## What counts as done
A milestone is done only when:
- the repo is green on the relevant automated suites
- critical flows are replayable and observable
- degraded modes are honest and predictable
- no P0/P1 bugs remain open
- docs and runbooks match reality
- a human acceptance pass says the system feels coherent
