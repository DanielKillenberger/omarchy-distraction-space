---
satisfies: [R2]
---
# fn-9-rewrite-one-contained-distraction-space.4 Feedback servers: HTTP block page and TLS SNI banner

## Description
Implement `ds/feedback.py`: two daemon-thread servers binding 127.0.0.1 and ::1 on 28080 and 28443. 28080 answers any request with a self-contained block page naming the escaped Host header (fallback 'this site'), the Super+D line, and a lock note when locked; bounded read (2 s, 16 KiB). 28443 reads the ClientHello (2 s, 16 KiB), parses SNI, closes, and sends one banner per host per 30 s under a lock. Per-socket bind failure notifies once and continues. `start(config, is_locked)` / `stop()` API for the listener.

**Files:** `ds/feedback.py`, `tests/test_feedback.py`.

## Acceptance
- Block page renders with escaped host and fallback; non-HTTP input closes without exception.
- SNI parser handles valid, truncated, garbage, and no-SNI ClientHellos.
- Concurrent ClientHellos for one host inside 30 s yield exactly one banner.
- A failed bind on one family leaves the other serving and notifies once.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
