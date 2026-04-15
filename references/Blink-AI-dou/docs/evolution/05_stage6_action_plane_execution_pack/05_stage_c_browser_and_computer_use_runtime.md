# Stage C — Browser and Computer-Use Runtime

## Objective

Replace the current honest `browser_task` unsupported placeholder with a real bounded browser runtime.

## Scope

Start with browser use, not full arbitrary OS control.

That means:

- open / navigate to a URL
- capture page title, visible text, and screenshot
- find likely targets
- perform bounded click/type actions only with explicit approval where needed
- export artifacts for every run

## Principles

### 1. Read-first
Initial browser capability should be strongest for:
- navigation
- extraction
- observation
- screenshot evidence

### 2. Human-visible preview
Before effectful steps, show:
- page summary
- candidate next actions
- screenshot
- target selectors or labels where practical

### 3. Bounded write actions
Do not begin with unrestricted form filling.
Start with:
- click a visible control
- type into a specified field
- submit a bounded form
- all behind approval and trace capture

### 4. No hidden browser magic
Record:
- URL
- page title
- screenshot path
- extracted visible text
- step list
- any typed inputs
- execution outcome

## Suggested implementation

Use a desktop-hosted browser automation layer, likely Playwright-backed, wrapped behind:

```text
src/embodied_stack/action_plane/connectors/browser.py
```

Suggested objects:

- `BrowserSession`
- `BrowserActionPreview`
- `BrowserActionArtifact`
- `BrowserRuntimeHealth`
- `BrowserExecutionPolicy`

## Step progression

### Phase 1
- `open_url`
- `capture_snapshot`
- `extract_visible_text`
- `summarize_page`

### Phase 2
- `find_click_targets`
- `click_target`
- `type_text`
- `submit_form`

### Phase 3
- bounded task recipes
  - open calendar page
  - read community event schedule
  - draft a follow-up form
  - fetch a public info page

## Console surfaces

Add a browser tab showing:
- current session
- current page title / URL
- latest screenshot
- pending action preview
- approval controls
- last browser action result

## Validation

Add tests for:

- unsupported browser runtime still degrades honestly when not configured
- snapshot-only mode
- preview generation
- approval gating for click/type/submit
- artifact writing and replay
- deterministic stub browser for CI

## Success criteria

Stage C is done when `browser_task` is no longer just a placeholder and Blink-AI can safely perform bounded browser work with visible previews and artifacts.
