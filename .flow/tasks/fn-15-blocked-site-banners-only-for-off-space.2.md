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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
