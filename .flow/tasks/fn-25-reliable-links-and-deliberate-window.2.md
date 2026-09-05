---
satisfies: [R3, R4, R5]
---
# fn-25-reliable-links-and-deliberate-window.2 Preserve foreign windows and offer deliberate migration

## Description
Replace automatic adoption launch/close with containment plus one bounded address-keyed migration offer. Add standalone CLI migrate action that rechecks the address/product and asks before launching a replacement, explaining state cannot transfer. Cancellation/failure preserves original; success also leaves original for user to close. No listener or main-menu changes.

**Files:** ds/hypr.py, distractions, tests/test_hypr.py, tests/test_listener.py
**Touches:** ds/hypr.py, distractions, tests/test_hypr.py, tests/test_listener.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_hypr tests.test_launch tests.test_listener

## Acceptance
- Satisfy parent R3-R5 for startup/reload/repeated events, snap-back/release, vanished address, cancellation and failed launch.
- Notification action binds original window address and revalidates identity; no automatic closure or network exemption.
- Update adoption-specific listener expectations only; preserve all scheduling tests.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
