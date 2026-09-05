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
Explicit listed URL targets now bypass host-only reuse and reach the distraction browser unchanged. Named product opens retain existing move/focus reuse; fake CLI regressions cover same-host deep links and failed delivery with an existing window.

Baseline: green, 16 tests. Verify: green, 17 launch tests; git diff --check passed. Regression red evidence: /tmp/fn25-1-red.log. No live browser navigation verified; success means accepted invocation.

Documentation implication: describe reuse for product-name opens and guaranteed invocation for explicit listed links. No CLI/config changes. Only the assigned two files changed.

stage: impl-review - skipped(policy: parallel-wave; conductor owns Fable through Claude CLI review after integration)

Fable claude-fable-5-1 reviewed the integrated commit and returned SHIP. Integrated full suite passed 386 tests. Documentation follow-up owns README Commands and docs/internals launch reuse wording.
## Evidence
- Commits: e1f1b18187255680db41edf29b31d0383084b1d4
- Tests: baseline: green (16 tests), PATH=/usr/bin:$PATH python3 -m unittest tests.test_launch (17 tests passed; /tmp/fn25-1-verify.log), Regression red before fix: /tmp/fn25-1-red.log (same-host URL delivery absent and launch failure masked), git diff --check, PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (386 passed, 163.580s), Fable claude-fable-5-1 implementation review: SHIP (.flow/reviews/fn-25-reliable-links-and-deliberate-window.1.md)
- PRs: