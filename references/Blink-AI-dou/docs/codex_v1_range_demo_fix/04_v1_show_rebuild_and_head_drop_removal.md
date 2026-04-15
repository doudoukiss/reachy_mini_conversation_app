# 04. V1 show rebuild and head-drop removal

This plan updates the V1 show so the new opening range demo appears first, the abrupt head drops are removed, and the documented expressive cues become clearly visible.

## Goal

Rebuild the V1 show so it is more truthful, more legible, and more impressive on real hardware.

## Step-by-step design

### Step 1 — Insert the new opening range segment at the very beginning

Add a new first segment before `arrival`.

Recommended segment:

- `segment_id`: `motion_envelope`
- title: `Motion envelope`
- first cue: `body_range_demo`
- optional brief narration after the range reveal: one short line explaining that this is the physical motion envelope before the character performance starts

### Step 2 — Keep total show length at 600 seconds

The current tests expect a 600-second show.

Do **not** casually expand the total duration.

Instead reclaim time from:

- redundant arrival/close sweeps
- long pauses that do not prove anything new
- duplicate neutral holds

### Step 3 — Remove the opening hard head-down impression

The current opening uses `youthful_greeting` as the first motion cue.

After the frame scheduler is fixed, re-author the opening so the robot does **not** finish the very first expressive beat in a downward listening pose.

Required changes:

- rewrite `youthful_greeting` so it recovers to `friendly` or a near-level attentive pose rather than a visibly down-pitched `listen_attentively`
- keep `double_blink` inside it if desired, but the final pose should not read as a head drop

### Step 4 — Remove the second aggressive head-down beat

`soft_reengage` currently starts with a down glance and still ends in `listen_attentively`.

Rewrite it so the final recovery is level and socially open.

Recommended new ending:

- `focused_soft` or `friendly`
- at most a tiny negative pitch, not a visible drop

### Step 5 — Retune the down-leaning authoring primitives

Revisit these actions:

- `listen_attentively`
- `safe_idle`
- `look_down_briefly`
- `soft_reengage`
- `youthful_greeting`

Required direction:

- `listen_attentively`: reduce downward head pitch to a barely perceptible value, or make it eye-led rather than neck-led
- `safe_idle`: no visible droop
- `look_down_briefly`: primarily eye-pitch motion with only a tiny head assist
- `soft_reengage`: recover level
- `youthful_greeting`: recover warm and level

### Step 6 — Make the documented new expressions visible in the actual show

Do not rely only on motion tracks buried inside narration if the beat needs to be unmistakable.

At minimum:

- keep `double_blink` in the show as a visible signature beat
- ensure at least one `double_blink` happens in a cue window where investors can actually perceive it
- keep at least one of `playful_peek_left` or `playful_peek_right` clearly visible
- keep at least one visible `brow_raise_soft` or `curious_bright` moment

Recommended tactic:

- for the signature expressive motions, prefer explicit body cues or clearly spaced narration-linked beats rather than dense overlaps

### Step 7 — Rebalance emphasis after the range demo
n
Once the opening range demo already proves the mechanical envelope, the rest of the show should feel more characterful, not like a calibration reel.

Use the rest of the show to demonstrate:

- attention shifts
- direct engagement
- short expressive punctuations
- calm recovery
- honest fallback

### Step 8 — Update show validation rules

The performance show validation suite should now assert:

- the new first segment exists
- the range demo cue is present
- signature expressive actions are still included
- the total duration still matches the public show target

## Preferred motion policy after the rebuild

- opening range demo = physically bold, technical, explicit
- main character performance = expressive, clean, and readable
- no more surprise head-down drops that look like mechanical awkwardness

## Acceptance criteria

1. The first thing the robot does is the new range demo.
2. `youthful_greeting` no longer reads like a head drop.
3. `soft_reengage` no longer reads like a head drop.
4. `double_blink` is visibly perceivable in the real show.
5. The show still feels polished, not like a debug session.
