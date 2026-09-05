---
satisfies: [R1, R2, R5, R6]
---
# fn-27-responsive-listener-and-efficient.1 Move reconciliation work off the listener event loop

## Description
Introduce bounded serialized side-effect work for firewall apply/flush, slice setup, and entry/cache reconciliation. Listener owns generation/order/result publication and refresh/reload waiter completion. Preserve setup/remove locks and no resurrection after removal. Publish cross-spec observed_at timestamps plus ping. Existing hold/notification work must remain functional; audit other synchronous checks for responsiveness.

**Files:** ds/listener.py, ds/net.py, ds/cgroup.py, ds/setup.py, tests/test_listener.py, tests/test_net.py
**Touches:** ds/listener.py, ds/net.py, ds/cgroup.py, ds/setup.py, tests/test_listener.py, tests/test_net.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_listener tests.test_net tests.test_setup

## Acceptance
- Parent R1/R2/R5/R6 covered by controlled stalls proving event, hold and lock progress before child completion.
- Subprocess deadlines terminate/reap children and bound shutdown; missing binaries/all OSError degrade without killing listener.
- No stale apply result overrides disable or current policy; callers wait for actual applicable outcomes.
- Cross-spec observed_at and ping contract works with unchanged top-level fields.
- Keep existing reconciliation every period until separate optimization task.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
