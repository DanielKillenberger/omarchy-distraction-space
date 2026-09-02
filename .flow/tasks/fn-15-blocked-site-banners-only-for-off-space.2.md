---
satisfies: [R4, R5]
---
# fn-15-blocked-site-banners-only-for-off-space.2 Hold push logging to the state log and tick retry while unavailable

## Description
`hold._log` and `summary._log` write timestamped lines to `state_path("log")` like `hypr._log` does; neither writes to stderr any more (the launcher discards it, which hid the start-time push failure and every summary command failure). `push` logs verb, key, and error on failure. The listener retries `sync_hold(force=True)` on each periodic tick while `hold_ipc` is `unavailable`; the notice stays one-time. Tests in tests/test_hold.py, tests/test_listener.py, and tests/test_summary.py (a failing or timing-out command leaves a state-log line).

**Touches:** ds/hold.py, ds/summary.py, ds/listener.py, tests/test_hold.py, tests/test_listener.py, tests/test_summary.py
## Acceptance
R4 of the parent spec holds with tests: a failing shell at start recovers on a later tick without a second notice, and the failure is in the state log.

## Done summary
`hold._log` and `summary._log` now append timestamped `hold: ` / `summary: ` lines to `state_path("log")` the way `hypr._log` does, so the launcher's discarded stderr no longer hides the start-time `silencedSenders` failure or a failing summary command. `_Ctx.sync_hold` retries the push once per `PERIOD` (30 s) while `notification_hold` is `unavailable`, stamped by `hold_failed_at`; the "Notification hold unavailable" notice stays one-time through the existing `hold_noted` flag, and `tick()` is unchanged.

Implementer: Grok (grok-4.6) through the grok CLI bridge, one pass, prompt at `.flow/tmp/grok-prompt.md`, log at `.flow/tmp/grok-run1.log`. Grok's edits stayed inside the six Touches files and matched the prompt's design; the host's only correction was wrapping a 149-character docstring in `ds/listener.py`. No second corrective pass was needed.

Tests (R4/R5): `tests/test_hold.py` - the fake `omarchy-shell` reads `DS_SHELL_MISSING` as a marker-file path (the `DS_BUS_EXIT` pattern) so a test can heal it mid-run; new `test_unavailable_shell_recovers_on_a_later_tick_with_one_notice` starts with the method missing, asserts one notice and a `hold: silencedSenders: Function not found.` state-log line, removes the marker, and sees `notification_hold: on` with the keys pushed and still exactly one notice (child `PERIOD` shortened to 1 s through a sitecustomize, as `Sandbox.batch_deadline_env` does); `test_push_missing_method...` asserts the log line; `test_busctl_exit_restarts_with_backoff` reads the restart lines from the state log instead of stderr (the two assertions kept, one made more specific). `tests/test_listener.py` - new in-process `HoldRetryTests` pins the cadence: no re-push below `PERIOD`, a re-push at `PERIOD` with no second notice, convergence once `push` returns `on`. `tests/test_summary.py` - the failure table asserts a `summary: ` state-log line for exit 1, timeout, and a missing command, and none for empty/off.

Baseline: green (226 tests at f610f37, `suite_rc=0`). Verify at HEAD: `flowctl gate classify` FULL (ds/hold.py); full suite `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` 228 tests, `suite_rc=0`, log `.flow/tmp/suite-final.log`. No lint/format gates configured. Commit range f610f37..58ef49c (one commit).

Follow-up noted, not built: `hold._log` and `summary._log` duplicate `hypr._log`'s six lines; a shared `state.log()` helper would remove the triplication but `ds/state.py` and `ds/hypr.py` were outside this task's Touches (a peer worker owns hypr.py this wave).

stage: impl-review - ran (model: claude-opus-5 via host backend, read-only subagent; SHIP, 3 non-blocking P3 findings, 2 pre-existing notes)
stage: plan-sync - skipped(config: planSync.enabled != true)
stage: wave-join - ran (merged onto the spec branch at c108692, no collision; integrated suite 239 tests OK)
## Evidence
- Commits: 58ef49cedfd98ea3e63972da61d59ca5537d9de8
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests > .flow/tmp/suite.log 2>&1, PATH=/usr/bin:$PATH python3 -m unittest tests.test_hold tests.test_summary tests.test_listener.HoldRetryTests > .flow/tmp/grok-focused.log 2>&1, python3 -m unittest discover -s tests
- PRs: