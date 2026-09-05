---
satisfies: [R1, R2, R5]
---
# fn-25-reliable-links-and-deliberate-window.1 Preserve explicit URL delivery while reusing named products

## Description
Distinguish explicit URL targets from product names, bypass host-only reuse for explicit URLs, and preserve exact URL argv plus existing forwarding/focus/lock semantics. Use existing Target, resolve_target and profile launch code. Success means accepted browser invocation, not proof of navigation.

**Files:** ds/launch.py, tests/test_launch.py
**Touches:** ds/launch.py, tests/test_launch.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_launch

## Acceptance
- Same-host distinct explicit URLs reach browser invocation intact, including query and fragment.
- Product-name reuse remains. Forwarded opaque flags, malformed URLs, absent launcher, and immediate launch refusal remain correct.
- Add focused regression tests and record documentation implications for final integration.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
