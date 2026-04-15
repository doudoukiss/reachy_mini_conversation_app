# Tests And Acceptance Gates

## Purpose

This side-track should be polished, but it also has to stay maintainable.

The show must have automated tests and human acceptance gates so it does not silently drift as the main product evolves.

## Test philosophy

Test the show at four levels:

1. data integrity
2. runner behavior
3. proof correctness
4. live-motion discipline

## Automated tests

### 1. Asset integrity tests

**Recommended file**
- `tests/demo/test_performance_show.py`

**What to test**
- show asset loads
- all cue kinds are valid
- all referenced scene names exist
- all referenced body actions exist in the semantic library
- all expected substrings are non-empty
- chapter ordering is stable
- timing totals are within the ten-minute target window

**Acceptance**
- the show definition can be validated without launching the full runtime

---

### 2. Runner tests in stub mode

**What to test**
- the runner executes a dry run
- the runner executes a stub/bodyless run
- silent proof scenes still produce cue results
- narration cues preserve exact script text
- a degraded cue with `continue_on_error=true` does not abort the whole show

**Acceptance**
- the show can complete end to end in CI without hardware

---

### 3. API / CLI contract tests

**Recommended files**
- `tests/brain/test_performance_api.py`
- or extend `tests/brain/test_operator_console.py`
- `tests/desktop/test_cli.py` if appropriate

**What to test**
- performance-show catalog endpoint
- performance-show run endpoint
- performance-run summary retrieval
- CLI dry-run output
- CLI full run output in stub mode

**Acceptance**
- operator-visible entrypoints remain stable

---

### 4. Proof assertion tests

**What to test**
Use the silent proof cues and verify they still hit the intended substrings.

Examples:
- grounded sign chapter expects `Workshop Room`
- memory chapter expects `Alex`
- memory chapter expects `quiet route`
- concierge chapter expects `6:00 PM`
- oversight chapter expects an incident or escalation record
- safe-fallback chapter expects safe idle visibility

**Acceptance**
- the show keeps proving the same investor claims even if internal implementations evolve

---

### 5. Motion safety tests

**Recommended files**
- `tests/body/test_performance_motion_profile.py`
- or extend existing body / serial safety tests

**What to test**
- show cue action names stay within the approved live-safe palette
- no bench-only action enters the public live path by accident
- intensity values do not exceed V1 ceilings
- the show can still render in virtual preview mode

**Acceptance**
- unsafe action drift is caught in CI before rehearsal

## Human acceptance gates

Automation is necessary but not sufficient.  
The team should enforce these human gates before the show is declared investor-ready.

### Gate 1 — Readability
From across the room:
- the robot's motion is legible
- the screen chapter title is legible
- the current proof beat is understandable in under three seconds

### Gate 2 — Timing
The show completes in:
- minimum: `9:30`
- target: `10:00`
- maximum: `10:30`

### Gate 3 — Composure
The head never appears:
- jittery
- mechanically strained
- overactive
- or toy-like

### Gate 4 — Honesty
If a proof path degrades, the fallback line sounds honest and composed.
No chapter should sound like it is bluffing.

### Gate 5 — Operator clarity
A side operator can identify:
- current chapter
- degraded chapter
- safe-idle state
- artifact path
within a few seconds.

### Gate 6 — Export proof
At the end of every successful rehearsal:
- the session export exists
- the performance run summary exists
- the final artifact path is visible

## Required rehearsal matrix

Do not mark the show ready until all of these have been run:

### Rehearsal A — bodyless / stub
Purpose:
- validate script pacing and cue order

### Rehearsal B — virtual-body
Purpose:
- validate semantic motion rhythm without hardware risk

### Rehearsal C — live-head cue-by-cue
Purpose:
- validate each show cue independently

### Rehearsal D — full live-head run
Purpose:
- validate the full investor sequence

### Rehearsal E — degraded live run
Purpose:
- validate at least one fallback path in front of the team

## Release criteria

The deterministic investor show is ready when:

- all automated tests pass
- all cue references are valid
- the full show runs in stub mode
- the full show runs in virtual-body mode
- the live head passes cue-by-cue validation
- three full live rehearsals complete without unsafe intervention
- at least one degraded rehearsal confirms graceful continuation
- the artifact export is produced on every rehearsal

## Change management rule

Any future change to these areas should trigger show regression review:

- `src/embodied_stack/demo/investor_scenes.py`
- `src/embodied_stack/brain/operator/service.py`
- `src/embodied_stack/body/driver.py`
- `src/embodied_stack/body/compiler.py`
- semantic tuning files
- performance show asset files
- performance page UI

If those change, re-run at least:
- asset tests
- stub runner test
- virtual-body rehearsal
- one live cue smoke pass

That keeps the side-track healthy without letting it dominate the main roadmap.
