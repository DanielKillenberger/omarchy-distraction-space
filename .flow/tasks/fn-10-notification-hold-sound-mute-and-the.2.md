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
Added `ds/hold.py`: sender keys from the expansion (catalog `senders` plus the PWA host parsed from the `pwa_class` pattern, hosts only for plain and custom hostname entries), `effective_hold`, `push()` that reads `silencedSenders` and writes `setSilencedSenders` with the plugin's keys added or removed while hand-added keys and their order survive, the shell patch's Chromium-origin matching rule, `held.jsonl` append with 4096-byte fields and the 64 KiB cap, `held_counts`, and a `Capture` that keeps `busctl --user monitor --json=short` alive with 1/4/16 s backoff and records attributed Notify lines while hold is on. The listener pushes at start, on reload, on every transition of effective hold or of the key set (keys that leave the list are retired from the shell), and on clean exit; a shell without the method yields `notification_hold: unavailable` with one notice while capture continues; `state.json` gains `hold`, `held`, `notification_hold`; `distractions senders` prints the keys. Tests: `tests/test_hold.py` (R2 push/hand-added/unavailable, R3 attribution/clipping/cap/unwritable/backoff, R6 start and exit, R7 launch errors), 204 tests green.

Follow-ups outside this task's files: `state.status()` (`distractions status --json`) does not yet expose the three new keys because `tests/test_status.py` pins the exact key set (task 4 territory). `tests/test_listener.py` ships no fake `omarchy-shell` or `busctl`, so its listener runs reach the real shell IPC (read-only today: the live shell answers "Function not found.") and monitor the real session bus; adding the two fakes from `tests/test_hold.py` to its setUp closes that. A hand-added key identical to a plugin key is removed when hold ends (indistinguishable by design).

stage: impl-review - ran [NEEDS_WORK -> SHIP, 2 rounds, cursor:gpt-5.6-sol-high]

stage: plan-sync - skipped(config: planSync.enabled != true)

## Evidence
- Commits: a1d3851d849e31c2eb0a5e052d37b243328da4c3, 9788bdcc7e50684b9c5309f938193c117e26afb6
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (204 tests OK; baseline: green via handoff, verified at 50a5b0aa by fn-10.1, 193 tests), PATH=/usr/bin:$PATH python3 -m unittest tests.test_hold (11 tests OK)
- PRs: