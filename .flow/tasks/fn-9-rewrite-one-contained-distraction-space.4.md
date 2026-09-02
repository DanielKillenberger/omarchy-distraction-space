---
satisfies: [R2]
---
# fn-9-rewrite-one-contained-distraction-space.4 Feedback servers: HTTP block page and TLS SNI banner

## Description
Implement `ds/feedback.py`: two daemon-thread servers binding 127.0.0.1 and ::1 on 28080 and 28443. 28080 answers any request with a self-contained block page naming the escaped Host header (fallback 'this site'), the Super+D line, and a lock note when locked; bounded read (2 s, 16 KiB). 28443 reads the ClientHello (2 s, 16 KiB), parses SNI, closes, and sends one banner per host per 30 s under a lock. Per-socket bind failure notifies once and continues. `start(config, is_locked)` / `stop()` API for the listener. Fixtures live in `tests/test_feedback.py` only.

**Files:** `ds/feedback.py`, `tests/test_feedback.py`.

**Touches:** [ds/feedback.py, tests/test_feedback.py]
## Acceptance
- Block page renders with escaped host and fallback; non-HTTP input closes without exception.
- SNI parser handles valid, truncated, garbage, and no-SNI ClientHellos.
- Concurrent ClientHellos for one host inside 30 s yield exactly one banner.
- A failed bind on one family leaves the other serving and notifies once.

## Done summary
`ds/feedback.py` serves the loopback block page on 28080 (escaped Host header, "this site" fallback, Super+D line, lock note through the `is_locked` callable, strict HTTP request line, 2 s / 16 KiB bounded read) and the TLS ClientHello SNI catcher on 28443 (one banner per host per 30 s, first banner never suppressed at early uptime), binding 127.0.0.1 and ::1 with per-socket bind failures notified once. `start(config, is_locked)` / `stop()` keep the wave-1 signatures for the listener. Implemented by cursor-agent (cursor-grok-4.6-high) in an isolated worktree; the conductor committed and integrated.

stage: impl-review - ran [round 1 NEEDS_WORK (2 findings fixed in 245c38c), round 2 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)

Record repair 2026-09-02: status replayed from this task's own Done summary and evidence after PR #9 merged; the fn-9 run's flow-state never reached main.
## Evidence
- Commits: f4dd6eca991042640448d58a7f741f85cafca5bb, 245c38cec5824c6f3427481defa1dd135d50d0a5, 82192e11f19494f90de15e7b2e8441bde03469ce
- Tests: python3 -m unittest discover tests
- PRs: 9