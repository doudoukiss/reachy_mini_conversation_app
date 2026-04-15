# Stage A — Action Protocol and Safety Foundation

## Objective

Create the deterministic, typed foundation that all later effectful actions must pass through.

## Deliverables

### 1. Action contracts
Add shared Pydantic models for:

- action intent
- request payload
- preview payload
- approval requirement
- approval state
- execution status
- result artifacts
- connector descriptor
- workflow run state

### 2. Risk model
Introduce a stable risk model independent of the language model.

Suggested classes:

- `read_only`
- `low_risk_local_write`
- `operator_sensitive_write`
- `external_side_effect`
- `irreversible_or_high_risk`

### 3. Approval policy engine
Build a deterministic service that evaluates:

- requested action type
- connector policy
- current context mode
- whether the runtime is bodyless / virtual / serial
- whether the action is local-only or external
- whether the action is user-initiated or proactive

Possible decisions:

- `allow`
- `preview_only`
- `require_approval`
- `reject`

### 4. Idempotency and deduplication
Every action execution must have:
- stable `action_id`
- `request_hash`
- `run_id`
- idempotency key
- retry policy

This prevents duplicate side effects after resume/restart.

### 5. Approval store
Persist approvals and pending requests under the runtime directory.

Suggested files:

```text
runtime/actions/pending_approvals.json
runtime/actions/execution_log.json
runtime/actions/connector_health.json
```

### 6. Agent OS integration
Update the typed tool invocation path so effectful tools no longer directly perform side effects.
Instead they should:
- construct an action request
- send it through the action-plane policy
- receive a preview / pending approval / execution result

### 7. Observability
Every action request must emit:
- trace event
- action status change
- approval decision
- execution result
- error classification

## Implementation order

1. add shared contracts
2. add `action_plane/models.py`
3. add approval/policy service
4. add execution store
5. integrate with one or two effectful tools first:
   - `write_memory`
   - `body_command`
6. keep old behavior behind compatibility wrappers while the new path stabilizes

## Validation

Add tests for:

- schema validity
- approval policy decisions
- duplicate request suppression
- restart-safe resume of pending approvals
- typed tool integration with preview and blocked states

## Success criteria

Stage A is done when the repo has a real action substrate even before browser or workflow execution is added.
