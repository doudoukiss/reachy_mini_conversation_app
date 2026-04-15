# Stage 6 Architecture — Personal Action Plane and Workflow Runtime

## Goal

Add a new system layer that sits between Agent OS reasoning and real effectful execution.

```text
[ User / Operator ]
        |
        v
[ Blink-AI appliance + console ]
        |
        v
[ Agent OS ]
  - skills
  - subagents
  - trace + checkpoints
  - typed tool requests
        |
        v
[ Action Plane ]
  - policy / approvals
  - connector registry
  - action execution store
  - workflow runtime
  - action audit + evidence
        |
        +--------------------+
        |                    |
        v                    v
[ Local connectors ]   [ Browser runtime ]
  - reminders          - navigation
  - notes              - screenshot / DOM snapshot
  - local files        - bounded click / type / submit
  - calendar           - approval-gated actions
  - future MCP         - future computer-use expansion
        |
        v
[ Optional semantic body feedback ]
  - listening
  - thinking
  - acknowledging
  - safe idle
```

## Major subsystems

### A. Action protocol
Shared contracts for:
- action request
- action proposal
- approval requirement
- approval decision
- action execution record
- action artifact
- workflow definition
- workflow run
- workflow checkpoint

### B. Connector gateway
A registry that owns:
- discovery
- health
- configuration
- capability tags
- action execution entrypoints
- risk metadata

### C. Approval and policy service
A deterministic policy layer that decides whether an action is:
- allowed immediately
- preview-only
- queued for approval
- blocked

### D. Browser / computer-use runtime
A desktop-hosted runtime for bounded browser actions with:
- screenshot artifacts
- DOM/text extraction artifacts
- operator previews
- per-step traces

### E. Workflow runtime
A bounded multi-step executor with:
- step states
- pause/resume
- retries
- rate limits
- timeouts
- approval boundaries
- artifact capture

### F. Action evidence and replay
All action runs should produce structured artifacts that can be replayed against:
- stub connectors
- dry-run connectors
- local connectors
- benchmark fixtures

## Suggested package structure

Introduce a new top-level package:

```text
src/embodied_stack/action_plane/
  __init__.py
  models.py
  policy.py
  approvals.py
  gateway.py
  registry.py
  execution_store.py
  workflow.py
  artifacts.py
  replay.py
  health.py
  connectors/
    __init__.py
    base.py
    reminders.py
    notes.py
    local_files.py
    calendar.py
    browser.py
    mcp.py
```

## Shared-contract additions

Add a new shared contract module:

```text
src/embodied_stack/shared/contracts/action.py
```

Suggested core models:

- `ActionRiskClass`
- `ActionApprovalPolicy`
- `ActionRequestRecord`
- `ActionProposalRecord`
- `ActionApprovalRecord`
- `ActionExecutionRecord`
- `ActionArtifactRecord`
- `ConnectorDescriptorRecord`
- `ConnectorHealthRecord`
- `WorkflowStepRecord`
- `WorkflowRunRecord`

## Compatibility strategy

Do not redesign the whole repo around Stage 6.

Instead:

- keep the Agent OS as the planner/orchestration layer
- keep `brain/agent_os/tools.py` as the front door for tool invocation
- route effectful action tools through the new action-plane layer
- add action-plane status to the console and CLI
- keep export/replay style aligned with existing episode and research surfaces

## First-class initial connectors

Start with bounded local connectors:

1. reminders
2. notes
3. local files / workspace
4. calendar lookup and simple event drafting
5. browser navigation and extraction
6. future MCP connector adapter

Do not start with arbitrary shell execution or unconstrained system control.
