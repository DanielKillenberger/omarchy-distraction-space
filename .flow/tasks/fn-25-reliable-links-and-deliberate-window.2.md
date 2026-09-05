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
Foreign listed web apps now move intact, subject to existing release and snap-back policy, with a bounded identity-keyed migration notice. The standalone migration action checks address, compositor, process lifetime, class, initial identity and product before and after explicit confirmation; cancellation, failure and success all leave the original open. The old automatic close/retry path and its unused helper are removed.

R3/R4/R5 are covered by focused discovery, failed-move, migration-outcome and stale-window regressions, plus the startup scan expectation. Baseline green: 88 tests. Verify green: 89 tests. Logs and commands are in the evidence file. No live desktop changes or verification occurred.

Documentation follow-up: replace automatic adoption-close descriptions; explain the notification action, separate profile and lack of live state transfer, manual closure after saving, and unchanged outside-profile network policy. Actions without a readable process identity are not offered. Offers are bounded in memory, so a listener restart may offer again; identity rechecks and explicit confirmation still apply. Existing open handles launch/focus semantics; migration adds no network exemption or workspace focus.

Known identity limit: same-process reuse of an address with identical initial class/title is indistinguishable through the available client snapshot. A stale action still requires fresh confirmation and can only launch, never close. No persisted token store was added, as directed by the conductor.

stage: impl-review - skipped(policy: parallel-wave; conductor owns Fable through Claude CLI review after integration)

Conductor integrated as cc6a601d602121dac781bd490d2bbef96547787a. Fable via Claude CLI (claude-fable-5-1) returned SHIP; evidence retained .flow/reviews/fn-25-reliable-links-and-deliberate-window.2.*. Integrated focused89 tests passed. Combined suite409 tests passed at b82c598 in169.650s after repairing unrelated public net.apply signature; log /tmp/v3-integrated-suite-fixed.log.
stage: impl-review - ran (model: claude-fable-5-1)
## Evidence
- Commits: cc6a601d602121dac781bd490d2bbef96547787a
- Tests: PATH=/usr/bin:$PATH python3 -m unittest tests.test_hypr tests.test_launch tests.test_listener (89 passed), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (409 passed, b82c598), git diff --check
- PRs: