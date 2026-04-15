# Stage E — Action Episode Flywheel and Evaluation

## Objective

Turn action execution into a durable data and quality flywheel.

## Deliverables

### 1. Action artifact bundle
Introduce a sidecar export such as:

```text
blink_action_bundle/v1
```

This avoids forcing an immediate incompatible redesign of existing `blink_episode/v2` and `blink_research_bundle/v1`.

The action bundle should include:

- source session/run ids
- requested action / workflow
- approval events
- connector calls
- browser artifacts
- execution states
- failures and retries
- final outcome
- user or operator feedback
- teacher annotations if present

### 2. Episode linkage
Existing episode bundles should reference related action bundles where present.

### 3. Replay harness
Add replay support against:
- stub connectors
- dry-run connectors
- deterministic browser fixtures
- workflow fixtures

### 4. Benchmark families
Create new eval families for:

- approval correctness
- idempotency
- workflow resume correctness
- browser artifact completeness
- connector safety policy
- proactive action restraint
- action trace completeness

### 5. Teacher mode for action quality
Allow reviewers to annotate:
- wrong action choice
- right plan, wrong timing
- right action, wrong explanation
- should have required approval
- unnecessary action
- missing follow-up

### 6. Research bridge alignment
The Stage 5 research bridge should be extended carefully:
- action bundles can be replayed
- planner comparisons can score action proposals vs outcomes
- data split hygiene must respect effectful workflows

## Implementation order

1. action bundle schema
2. bundle export writer
3. replay harness for action bundles
4. deterministic fixtures
5. benchmark suite
6. teacher annotation surfaces

## Validation

Add tests for:

- bundle schema validity
- bundle/episode linkage
- deterministic replay over stub connectors
- benchmark score generation
- approval trace completeness
- teacher annotation persistence

## Success criteria

Stage E is done when action work is no longer ephemeral and can drive evaluation, regression testing, and future planning research.
