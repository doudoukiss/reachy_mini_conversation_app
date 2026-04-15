# World-Class Target and Design Rules

## Target

Blink-AI should become a **world-class local embodied companion OS with a safe action plane**.

That means the system can:

- converse naturally
- perceive and ground itself in the local environment
- remember and retrieve useful context
- express attention and intent through semantic body actions
- perform bounded digital work safely and transparently
- export every important run as evidence, replay, and training-ready data

## Design rules

### 1. Actions are first-class contracts
Every effectful step must be represented as a typed action request and typed action result.
No invisible side effects.

### 2. Approval is a runtime concept, not a prompt trick
The model may request actions.
The runtime decides whether they are:
- immediately allowed
- preview-only
- blocked
- pending approval

### 3. Connectors expose capability, health, and risk
Every connector must publish:
- what it can do
- what it is currently configured to do
- what risk class each action belongs to
- whether it is degraded or unavailable

### 4. Workflows are resumable and idempotent
A workflow can pause for approval, survive a restart, and resume without duplicating irreversible actions.

### 5. Browser and computer-use are bounded
Do not start with generic unconstrained UI automation.
Start with:
- navigation
- snapshot / extraction
- operator-visible preview
- operator-approved click/type/submit paths

### 6. Body semantics remain above raw hardware
Action planning may say:
- “I am checking your calendar”
- “I’m opening the event page”
- “I saved that as a reminder”

The body layer may express:
- listening
- thinking
- confirming
- safe idle

But action execution must not depend on direct raw-servo control.

### 7. Every effectful run becomes a data asset
Action runs must be exportable and replayable with enough structure for:
- regression testing
- workflow analysis
- teacher review
- future fine-tuning or planning research

### 8. Local-first by default
The first-class path should work on the local Mac runtime.
Cloud services and future remote executors are optional enhancements.

### 9. Operator trust beats automation theater
The UI must make it obvious:
- what the system wants to do
- what it actually did
- what failed
- what requires human confirmation
- what was skipped for safety

### 10. Maintain architectural split
- Mac brain / appliance owns reasoning, workflows, approvals, UI, traces, and local execution policies
- edge remains deterministic and simple
- future embodied action reuse happens through the same typed action layer, not ad hoc code paths
