# Stage B — Tool Gateway and Connector Runtime

## Objective

Turn the action substrate into a real connector platform.

## Why this stage exists

Right now Blink-AI has many useful concepts but no single system for connector capability, health, configuration, and execution.
A world-class assistant needs a governed gateway.

## Deliverables

### 1. Connector interface
Create a base connector protocol:

- connector id
- human label
- capability tags
- supported actions
- risk class mapping
- health snapshot
- configuration status
- dry-run support
- execute / preview entrypoints

### 2. Connector registry
A registry that:
- loads enabled connectors
- publishes health
- exposes capability discovery to the console
- lets the action plane resolve the right executor

### 3. First connector set

#### Reminders connector
- create reminder
- list reminders
- mark reminder done
- dry-run preview for reminder writes

#### Notes connector
- append note
- create note
- list/search notes
- optional note tagging

#### Local files connector
- read from an approved workspace root
- create export bundles
- stage files for review
- forbid arbitrary filesystem traversal outside allowed roots

#### Calendar connector
Start bounded:
- query current local/venue calendar data
- draft an event
- save as pending proposal or local artifact
- optionally enable later system-calendar writes behind approval

#### MCP-compatible adapter
- not a full dependency on external servers at Stage B
- define the internal adapter interface now
- allow future external skill servers to plug in without redesign

### 4. Connector health model
Expose per-connector status:
- supported
- configured
- degraded
- unavailable
- last error
- last successful action
- dry-run only

### 5. Console integration
Add a connector panel to `/console` showing:
- available connectors
- action support
- health/configuration
- recent action history
- pending approvals

### 6. CLI integration
Extend local companion and/or appliance CLI with:
- connector status command
- approval list command
- action history command
- replay last action command

## Implementation order

1. base connector interface
2. registry + health publication
3. reminders connector
4. notes connector
5. local files connector
6. calendar connector
7. console and CLI status surfaces
8. future-proof MCP adapter shape

## Validation

Add tests for:

- registry discovery
- connector health reporting
- workspace-root safety for files
- reminder/note lifecycle
- calendar draft preview path
- console serialization for connector health

## Success criteria

Stage B is done when Blink-AI has a real connector gateway that can already perform a few useful local actions safely and transparently.
