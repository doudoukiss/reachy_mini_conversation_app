# Pilot Site Content Packs

Blink-AI can load a local pilot-site pack from disk instead of relying only on seeded Python data.

A pilot-site pack now drives two things:

- venue knowledge
- venue operations policy

The default sample pack lives in:

- `pilot_site/demo_community_center/`
- `pilot_site/demo_library_branch/`

## Supported content formats

- `site.yaml` or `site.json`
  - site name
  - summary
  - timezone
  - hours summary
  - structured `operations` policy block
- FAQ files in `json`, `yaml`, or `yml`
  - `key`
  - `question`
  - `answer`
  - optional `aliases`
  - optional `tags`
- event schedules in `csv` or `json`
  - `event_id`
  - `title`
  - `start_at`
  - optional `end_at`
  - optional `location_key`
  - optional `location_label`
  - optional `summary`
  - optional `aliases`
- room or location lists in plain text or structured files
  - plain text uses pipe-delimited lines:
    - `location_key|title|floor|directions|aliases|visible_signage|nearby_landmarks`
- staff contacts in plain text or structured files
  - plain text uses pipe-delimited lines:
    - `contact_key|name|role|phone|email|notes|aliases`
- markdown docs
  - imported as searchable venue documents
- optional `.ics` calendar files
  - imported as additional event entries

## Recommended minimal pack

For a real pilot site, include at least:

1. `site.yaml`
2. one FAQ file
3. one event schedule file
4. one room or location file
5. one staff contact file

## Site Operations Schema

Put operational policy inside `site.yaml` under `operations:`.

Supported operational fields:

- `opening_hours`
  - list of day/time windows
- `quiet_hours`
  - list of day/time windows where proactive outreach should be suppressed
- `closing_windows`
  - list of day/time windows for closing behavior
- `proactive_greeting_policy`
  - `enabled`
  - `greeting_text`
  - `returning_greeting_text`
  - `cooldown_seconds`
  - `max_people_for_auto_greet`
  - `suppress_during_quiet_hours`
- `announcement_policy`
  - `enabled`
  - `opening_prompt_text`
  - `opening_prompt_window_minutes`
  - `closing_prompt_text`
  - `event_start_reminder_enabled`
  - `event_start_reminder_lead_minutes`
  - `event_start_reminder_text`
  - `proactive_suggestions`
  - `quiet_hours_suppressed`
- `escalation_policy_overrides`
  - `default_staff_contact_key`
  - `accessibility_staff_contact_key`
  - `keyword_rules`
    - `match_any`
    - `reason_category`
    - `urgency`
    - `staff_contact_key`
    - `note`
- `accessibility_notes`
- `fallback_instructions`
  - `scenario`
  - `visitor_message`
  - `operator_note`

## Example `site.yaml`

```yaml
site_name: Example Venue
timezone: America/Los_Angeles
summary: Example pilot site.
operations:
  opening_hours:
    - days: [monday, tuesday, wednesday, thursday, friday]
      start: "09:00"
      end: "17:00"
      label: weekday_shift
  quiet_hours:
    - days: [wednesday]
      start: "13:00"
      end: "14:00"
      label: quiet_block
  closing_windows:
    - days: [monday, tuesday, wednesday, thursday, friday]
      start: "16:30"
      end: "17:00"
      label: closeout
  proactive_greeting_policy:
    enabled: true
    greeting_text: Hello. I can help with rooms, events, or staff support.
    cooldown_seconds: 60
    max_people_for_auto_greet: 2
  announcement_policy:
    enabled: true
    closing_prompt_text: The venue is closing soon.
    event_start_reminder_enabled: true
    event_start_reminder_lead_minutes: 10
    proactive_suggestions:
      - I can help with directions or today's schedule.
  escalation_policy_overrides:
    default_staff_contact_key: front_desk
    accessibility_staff_contact_key: accessibility
    keyword_rules:
      - match_any: [lost item, found item]
        reason_category: lost_item
        urgency: normal
        staff_contact_key: front_desk
  accessibility_notes:
    - Offer the elevator route before stairs.
  fallback_instructions:
    - scenario: safe_idle
      visitor_message: I am paused in a safe idle state while staff checks the system.
```

## How To Add A New Site

1. Create a new folder under `pilot_site/`, for example `pilot_site/my_branch/`.
2. Add `site.yaml` with basic metadata plus the `operations` block.
3. Add at least one FAQ file, one event file, one room file, and one staff contact file.
4. Keep staff contact keys stable, because the operations pack references them directly.
5. Run `uv run pytest` to catch invalid policy or broken references early.

## What The Operations Pack Changes

Without code edits, a site pack can now change:

- when Blink-AI is open, quiet, or closing
- whether automatic greeting is aggressive or restrained
- which proactive prompts are used
- whether event reminders fire and how early
- which staff contacts are suggested for different escalation categories
- what Blink-AI says during degraded, safe-idle, after-hours, or operator-unavailable cases

## Why this exists

This keeps Blink-AI honest and operational:

- venue facts live in a site-owned content pack
- operational policy also lives in the site-owned content pack
- the brain can trace which file grounded a reply
- the same knowledge and operations path works with and without provider credentials
- pilot-site rollout becomes a content-ingestion task, not a code rewrite
