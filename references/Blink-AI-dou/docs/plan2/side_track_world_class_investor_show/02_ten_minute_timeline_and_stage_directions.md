# Ten-Minute Timeline And Stage Directions

## Show identity

- **Show name:** `investor_ten_minute_v1`
- **Primary session id:** `investor-show-main`
- **Default runtime target:** `desktop_serial_body`
- **Narration mode:** prewritten, local speech
- **Proof mode:** silent scene execution plus visible screen updates
- **Primary product framing:** local-first companion with optional embodiment

## Stage layout

### Physical layout
- Robot centered on table, slightly below audience eye line
- Main projector shows the performance surface or presence shell
- Operator monitor shows `/console`
- Speaker output routed to the robot-side audio path or nearest speaker under the table

### Screen policy
The main screen should show only what helps the audience:
- chapter title
- current proof beat
- one clean state visualization
- occasional artifact summary

The operator console should stay off the main screen except when escalation or safety is being proven.

## Motion policy for the live robot

Use only smoke-safe semantic actions for the live run unless a later validation pass explicitly promotes something else.

Live show palette:
- `friendly`
- `neutral`
- `thinking`
- `concerned`
- `listen_attentively`
- `safe_idle`
- `look_forward`
- `look_left`
- `look_right`
- `look_up`
- `look_down_briefly`
- `look_at_user`
- `blink_soft`
- `nod_small`
- `tilt_curious`
- `recover_neutral`

Avoid live use of bench-only animations in the first public version.

## Timing overview

| Time | Chapter | Purpose |
| --- | --- | --- |
| 0:00–1:00 | Opening reveal | establish presence and product thesis |
| 1:00–2:05 | Same mind, optional embodiment | show semantic embodiment, not servo puppetry |
| 2:05–3:20 | Grounded perception | prove current-scene grounding |
| 3:20–4:35 | Memory and continuity | prove useful continuity across turns |
| 4:35–5:50 | Useful concierge behavior | prove commercially believable utility |
| 5:50–7:05 | Operator oversight | prove real-world handoff discipline |
| 7:05–8:15 | Honest fallback and safe idle | prove trustworthy degradation |
| 8:15–10:00 | Evidence and closing thesis | prove replayability and land the company story |

---

## Chapter 1 — Opening Reveal
**Time:** 0:00–1:00  
**Investor inference:** This feels alive immediately, and it knows what it is.

### On-screen
- Title: `Blink-AI`
- Subtitle: `Local-first companion. Optional embodiment.`
- Small line: `Deterministic investor performance mode`

### Body cue sequence
1. `friendly` intensity `0.58`
2. `blink_soft` intensity `0.45`
3. `look_left` intensity `0.60`
4. `look_right` intensity `0.60`
5. `look_forward` intensity `0.55`
6. `nod_small` intensity `0.50`

### Runtime proof cues
- No heavy proof cue yet
- Optional: initialize presence surface and show current runtime profile summary

### Delivery notes
- Start with motion first, speech second
- Let the first blink and gaze sweep land before line one
- No rush

### Spoken beat
Robot introduces itself and frames the next ten minutes.

### Segment fallback
If motion is blocked:
- use avatar/presence shell only
- keep the same narration
- add a small caption: `robot projection preview-only`

---

## Chapter 2 — Same Mind, Optional Embodiment
**Time:** 1:00–2:05  
**Investor inference:** The body is downstream of the same companion runtime, not a separate product.

### On-screen
- Title: `One Companion, Multiple Projections`
- Chips:
  - `presence`
  - `memory`
  - `operator oversight`
  - `semantic embodiment`

### Body cue sequence
1. `listen_attentively` intensity `0.55`
2. `look_at_user` intensity `0.52`
3. `thinking` intensity `0.48`
4. `tilt_curious` intensity `0.36`
5. `recover_neutral` intensity `0.45`
6. `friendly` intensity `0.52`

### Runtime proof cues
- Show current character-presence shell state
- Show that the runtime is emitting semantic presence state and body projection status
- Optional side proof on operator monitor: `character_projection` state and body status

### Delivery notes
- This is the architecture chapter, but keep it human
- The line should make investors feel the product strategy is disciplined

### Spoken beat
Explain that the runtime chooses attention, listening, thinking, and safe idle, while the body layer safely compiles those into motion.

### Segment fallback
If body projection is blocked:
- explicitly show `preview-only` state on screen
- robot says the embodiment path is safety-gated and will not fake live motion

---

## Chapter 3 — Grounded Perception
**Time:** 2:05–3:20  
**Investor inference:** The system can answer from current evidence, not canned claims.

### On-screen
- Title: `Grounded Perception`
- Main panel: current fixture / scene snapshot
- Proof caption: `visible text and scene facts are traceable`

### Body cue sequence
1. `thinking` intensity `0.50`
2. `look_down_briefly` intensity `0.42`
3. `look_forward` intensity `0.50`
4. `nod_small` intensity `0.42`
5. `friendly` intensity `0.46`

### Runtime proof cues
Run the silent proof cue:
- `read_visible_sign_and_answer`
- `voice_mode=stub_demo`
- `speak_reply=false`

Expected proof:
- final reply includes `Workshop Room`
- grounding sources are populated
- perception snapshot exists

### Delivery notes
- Use an off-stage prompt or caption prompt first
- The robot's spoken line comes after the proof cue returns
- The audience should see the fixture and the grounded answer together

### Segment fallback
If the proof cue does not match:
- display actual runtime output
- robot says the visual path is degraded and it is staying with the verified output on screen

---

## Chapter 4 — Memory And Continuity
**Time:** 3:20–4:35  
**Investor inference:** This is not a stateless novelty; it can become a real ongoing product.

### On-screen
- Title: `Continuity`
- Two cards:
  - `new information captured`
  - `later turn recalled`

### Body cue sequence
1. `friendly` intensity `0.54`
2. `look_at_user` intensity `0.50`
3. `blink_soft` intensity `0.40`
4. `listen_attentively` intensity `0.52`
5. `nod_small` intensity `0.44`

### Runtime proof cues
Run these silently in order:
1. `natural_discussion`
2. `companion_memory_follow_up`

Expected proof:
- user memory stores `Alex`
- preference stores `quiet route`
- follow-up reply mentions both

### Delivery notes
- The robot should sound warm, not sentimental
- This chapter is about usefulness and continuity, not fake intimacy

### Segment fallback
If memory recall does not match expectation:
- robot says the runtime captured the first turn but the recall path is degraded
- keep the memory card on screen with the actual stored fields

---

## Chapter 5 — Useful Concierge Behavior
**Time:** 4:35–5:50  
**Investor inference:** There is a believable commercial deployment wedge right now.

### On-screen
- Title: `Useful In Public`
- Subtitle: `community concierge / guide`
- Proof card: `grounded venue answer`

### Body cue sequence
1. `listen_attentively` intensity `0.50`
2. `thinking` intensity `0.46`
3. `look_left` intensity `0.42`
4. `look_forward` intensity `0.48`
5. `friendly` intensity `0.50`
6. `nod_small` intensity `0.45`

### Runtime proof cues
Use a direct silent text turn:
- `What time does the Robotics Workshop start?`

Expected proof:
- answer references `6:00 PM`
- answer references `Workshop Room` or equivalent location grounding

Optional secondary proof:
- show venue knowledge source card or grounded knowledge result

### Delivery notes
- This is the business chapter
- Keep the answer concrete and commercial, not abstract

### Segment fallback
If the exact event answer is not available:
- switch to `wayfinding_usefulness`
- keep the chapter framing the same: useful, grounded help in a venue context

---

## Chapter 6 — Operator Oversight
**Time:** 5:50–7:05  
**Investor inference:** This team understands real-world deployment and handoff, not just autonomy.

### On-screen
- Title: `Operator Oversight`
- Main panel: incident ticket card
- Visible fields:
  - ticket id
  - category
  - status
  - suggested staff contact
  - timeline

### Body cue sequence
1. `listen_attentively` intensity `0.54`
2. `concerned` intensity `0.42`
3. `look_at_user` intensity `0.48`
4. `nod_small` intensity `0.38`
5. `friendly` intensity `0.42`

### Runtime proof cues
Run silently:
- `escalate_after_confusion_or_accessibility_request`

Expected proof:
- incident ticket exists
- escalation or operator state is visible
- timeline / staff routing data is present

### Delivery notes
- This chapter should feel calm and competent
- It should not feel like a failure; it should feel like operational maturity

### Segment fallback
If the full accessibility route scene is noisy:
- use `operator_escalation`
- keep the same screen card and the same thesis

---

## Chapter 7 — Honest Fallback And Safe Idle
**Time:** 7:05–8:15  
**Investor inference:** The system degrades in a trustworthy way.

### On-screen
- Title: `Safe Fallback`
- Status card:
  - transport degraded
  - safe idle active
  - reason visible

### Body cue sequence
1. `look_forward` intensity `0.40`
2. `safe_idle` intensity `0.60`
3. hold still
4. after narration, `friendly` intensity `0.38`

### Runtime proof cues
Run silently:
- `safe_fallback_failure`

Expected proof:
- heartbeat shows degraded or safe fallback
- safe idle active
- body status reflects fallback path

### Delivery notes
- This chapter should become more still, not more dramatic
- The stillness itself is the proof

### Segment fallback
If safe-idle injection path does not apply:
- call explicit operator safe idle
- continue with the same narration

---

## Chapter 8 — Evidence, Replayability, And Close
**Time:** 8:15–10:00  
**Investor inference:** This is a measurable platform with a credible product strategy.

### On-screen
- Title: `Replayable Evidence`
- Show a compact artifact summary:
  - session id
  - trace count
  - grounding sources
  - incidents
  - command acknowledgements
  - artifact/export path

### Body cue sequence
1. `thinking` intensity `0.40`
2. `look_at_user` intensity `0.46`
3. `friendly` intensity `0.56`
4. `blink_soft` intensity `0.40`
5. `nod_small` intensity `0.52`
6. `recover_neutral` intensity `0.45`

### Runtime proof cues
At the end of the show:
- export the session episode or performance artifact bundle
- surface the artifact path on screen
- optionally snapshot a summary card for the operator

Expected proof:
- artifact bundle exists
- session export succeeds
- performance metadata is included

### Delivery notes
- This close should tie the demo back to the company story
- The final line should leave no confusion about the product direction

### Segment fallback
If export is slow:
- keep the screen on the in-memory summary
- say that the artifact bundle is being written locally and the summary already reflects the run

---

## Optional extensions for a later 12-minute cut

These should not be in the first public ten-minute version unless the core run is already excellent:

### Optional insert A — Two-person attention handoff
Use:
- `two_person_attention_handoff`

Investor inference:
- the system can manage public-space interaction more gracefully

### Optional insert B — Disengagement shortening
Use:
- `detect_disengagement_and_shorten_reply`

Investor inference:
- the social runtime is not monologue-prone

### Optional insert C — Operator correction after wrong interpretation
Use:
- `operator_correction_after_wrong_scene_interpretation`

Investor inference:
- the system supports correction and governance, not just first-pass autonomy
