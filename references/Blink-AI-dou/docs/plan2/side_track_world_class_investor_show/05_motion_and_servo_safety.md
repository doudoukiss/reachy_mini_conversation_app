# Motion And Servo Safety Plan

## Purpose

The live show should look **more expressive than the current default**, but it must never look reckless.

The right strategy is:

- stay on the semantic body surface
- use only live-safe actions in V1
- increase expressiveness through **conservative semantic tuning**
- validate every show cue on real hardware before public use

## Live-safe policy

### Allowed in the first public version
Use these semantic actions only:

**Expressions**
- `neutral`
- `friendly`
- `thinking`
- `concerned`
- `listen_attentively`
- `safe_idle`

**Gaze**
- `look_forward`
- `look_at_user`
- `look_left`
- `look_right`
- `look_up`
- `look_down_briefly`

**Gestures**
- `blink_soft`
- `nod_small`
- `tilt_curious`

**Animation**
- `recover_neutral`

### Not allowed live in V1 unless separately promoted by validation
Do not use these on the public live head in the first release:

- `micro_blink_loop`
- `scan_softly`
- `speak_listen_transition`

They are useful assets, but the repo currently classifies the more animation-like actions as not smoke-safe. Keep them off the live public path until the team explicitly validates them for show use.

## Intensity guidance

These are the recommended first-pass ceilings for the investor show tuning:

### Head / gaze
- normal show range: `0.42–0.62`
- hard ceiling for V1: `0.70`

### Brow-heavy expressions
- normal show range: `0.42–0.58`
- hard ceiling for V1: `0.62`

### Nods
- normal show range: `0.38–0.52`
- hard ceiling for V1: `0.58`

### Tilts
- normal show range: `0.30–0.40`
- hard ceiling for V1: `0.45`

### Safe idle
- hold steady, do not embellish
- use stillness as part of the communication

## Show-specific tuning philosophy

The investor show should feel:
- a little larger,
- a little cleaner,
- and a little more deliberate

It should **not** feel:
- faster,
- twitchier,
- or more complex.

The improvement should come from:
- slightly increased intensity on selected safe actions
- cleaner neutral recovery
- stronger friendly and attentive poses
- more reliable left/right gaze readability
- consistent brow symmetry

## Recommended show tuning file

Create:
- `runtime/body/semantic_tuning/robot_head_investor_show_v1.json`

This tuning file should be loaded only when the investor show is running.

### What to tune first
Tune in this order:

1. `friendly`
2. `listen_attentively`
3. `thinking`
4. `look_left`
5. `look_right`
6. `look_at_user`
7. `nod_small`
8. `tilt_curious`

### What not to tune first
Avoid starting with:
- lid coupling changes
- aggressive brow asymmetry
- large pitch / roll reweighting

Those can quickly make the head look unnatural or mechanically stressed.

## Teacher-review loop

Use the existing teacher-review path after every live observation block.

For each action:
- run the action
- observe visually
- record one of:
  - `keep`
  - `adjust`
  - `reject`
- if adjustment is needed, apply a small semantic tuning delta
- rerun the action
- stop when the action is clearly readable and mechanically calm

## Live validation order

### Phase 1 — Dry run
- verify the full cue list in dry-run mode
- confirm no unsupported action names are referenced

### Phase 2 — Virtual preview
- run the show in virtual-body mode
- confirm the visual rhythm and semantic ordering

### Phase 3 — Real-head cue validation
Validate every live cue individually using the serial path:
- write neutral
- run one show cue
- write neutral
- inspect readback and visible motion
- record teacher review

### Phase 4 — Short stitched rehearsal
Run only chapters 1 and 2 together, then 3 and 4, then 5 through 8.

### Phase 5 — Full dress rehearsal
Run the full ten-minute show end to end.

### Phase 6 — Repeatability check
Run the full show three times on separate starts.
Do not go public until all three runs are:
- visually acceptable
- mechanically calm
- free of unsafe drift
- free of emergency intervention

## Pre-show live motion checklist

Before every real investor meeting:

1. `serial-doctor`
2. `read-position`
3. `read-health`
4. `arm-live-motion`
5. `write-neutral`
6. smoke `friendly`
7. smoke `look_left`
8. smoke `look_right`
9. smoke `nod_small`
10. `write-neutral`

If any of these look wrong, stop and retune or fall back to preview-only.

## No-go conditions

Do not run the live robot if any of these are true:

- live calibration is missing or obviously stale
- neutral alignment is visibly off
- one brow is hanging low again
- lids move the wrong direction
- repeated cue drift accumulates
- read-health shows instability
- the arm gate is not clean
- transport is degraded before the show starts

If any no-go condition is hit, switch to:
- presentation surface + audio
- optional avatar / preview-only projection

That is a valid show. A mechanically risky live head is not.

## Recovery sequence

If the head behaves unexpectedly during rehearsal or show:

1. `write-neutral`
2. `safe-idle`
3. `disarm-live-motion`

Do not attempt clever mid-show recovery choreography.

The fallback story is stronger when it is simple.

## Motion aesthetics guidance

### Good investor-demo motion looks like
- confident
- sparse
- readable
- intentional
- well-timed to speech
- still when it matters

### Bad investor-demo motion looks like
- constant movement
- unnecessary blinking
- novelty winks
- over-tilting
- jitter while waiting for the next line
- emotional excess

The physical performance should feel closer to:
- a composed keynote speaker

Not:
- a toy character audition

## Recommended defaults for the first show pass

These are safe starting points for the first tuning pass:

- `friendly`: `0.56`
- `listen_attentively`: `0.54`
- `thinking`: `0.48`
- `look_left`: `0.60`
- `look_right`: `0.60`
- `look_forward`: `0.50`
- `look_at_user`: `0.52`
- `look_down_briefly`: `0.42`
- `nod_small`: `0.50`
- `tilt_curious`: `0.36`
- `blink_soft`: `0.40`

Treat these as starting values, not permanent truth.
