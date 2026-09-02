---
satisfies: [R4, R5]
---
# fn-15-blocked-site-banners-only-for-off-space.2 Hold push logging to the state log and tick retry while unavailable

## Description
hold._log writes timestamped lines to state_path("log") like hypr._log. push logs verb, key, and error on failure. The listener retries sync_hold(force=True) on each periodic tick while hold_ipc is unavailable; the notice stays one-time. Tests in tests/test_hold.py and tests/test_listener.py.

**Touches:** ds/hold.py, ds/listener.py, tests/test_hold.py, tests/test_listener.py

## Acceptance
R4 of the parent spec holds with tests: a failing shell at start recovers on a later tick without a second notice, and the failure is in the state log.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
