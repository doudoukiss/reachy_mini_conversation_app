# Stage F — Operator UX and Productization

## Objective

Make Stage 6 feel like a product feature, not a hidden engineering subsystem.

## Deliverables

### 1. Console action center
Add a first-class action center in `/console` with:

- connector health
- pending approvals
- active workflow runs
- recent action history
- browser preview/artifact panel
- per-run failure details
- replay / inspect actions

### 2. Appliance integration
`uv run blink-appliance` should surface Stage 6 cleanly:
- setup checks for required local action capabilities
- honest degraded mode if browser runtime is missing
- zero hidden manual token steps
- one clear path to continue from approval prompts

### 3. Local companion integration
`uv run local-companion` should gain:
- workflow status command
- approval list / approve / reject commands
- action history command
- connector status command
- action preview explanations in replies

### 4. Recovery and crash safety
On restart, the runtime should:
- reload pending approvals
- reload resumable workflows
- refuse to replay irreversible side effects automatically
- mark uncertain runs for review instead of pretending success

### 5. Release discipline
Add runbooks and Make targets for:
- action-plane validation
- browser runtime smoke
- workflow replay smoke
- export bundle inspection

## Product-quality rules

- no hidden state transitions
- no silent side effects
- obvious pending approval state
- obvious connector degradation
- obvious action outcome
- bodyless mode remains first-class

## Validation

Add end-to-end checks for:
- start appliance
- request action
- preview generated
- approval recorded
- action executed
- action appears in console history
- action bundle exported

## Success criteria

Stage F is done when a non-technical operator can safely use Stage 6 features without living in the terminal.
