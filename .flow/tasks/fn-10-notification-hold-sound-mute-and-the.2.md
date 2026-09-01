---
satisfies: [R2, R3, R6, R7]
---
# fn-10-notification-hold-sound-mute-and-the.2 Hold push to the shell and bus capture into held.jsonl

## Description
Implement the hold half of `ds/hold.py`: `sender_keys(expanded)`, `effective_hold(config, on_space, locked)`, `push(keys, on)` reading `silencedSenders` and writing `setSilencedSenders` with the plugin's keys added or removed while preserving hand-added keys, `notification_hold` state on/off/unavailable with one notice. Implement the capture: a `busctl --user monitor --json=short --match ...` subprocess with backoff restarts, per-line parse of `payload.data`, sender matching (app_name, or Chromium origin at the start of the body), append to `held.jsonl` with clipping and the 64 KiB cap, counts for `state.json.held`. Wire into the listener: push on transitions, reload, start, and clean exit; `distractions senders`.

**Files:** `ds/hold.py`, `ds/listener.py`, `distractions`, `tests/test_hold.py`.

## Acceptance
- Push adds and removes only the plugin's keys; hand-added keys survive both directions.
- A missing IPC method yields `notification_hold: unavailable` and one notice; capture continues.
- Recorded busctl lines for a native app and a Chromium web app are attributed correctly; an unmatched Notify is ignored.
- `held.jsonl` clipping and cap hold; `state.json.held` counts match.
- Clean listener exit removes the keys; a start with effective hold pushes them.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
