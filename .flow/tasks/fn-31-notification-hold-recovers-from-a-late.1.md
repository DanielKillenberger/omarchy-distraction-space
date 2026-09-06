---
satisfies: [R1, R2, R3, R4]
---
# fn-31-notification-hold-recovers-from-a-late.1 Implement Notification hold recovers from a late shell

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
The listener now tells a shell it could not reach from one that answered and refused, so a login race with omarchy-shell costs seconds of degraded state instead of a minute. A transport failure opens one retry episode — the shell push alone, every 2 seconds for 10 seconds measured from when the failure came back — while an answered failure keeps the per-period retry and the once-per-lifetime "run setup" notice, which no longer fires for a shell that was merely late. Only a push that gets through ends an outage, so nothing reopens a spent window. `silenced-owned.json` alone now says what is owed back to the shell, so a key whose removal the shell refused is retried on the next push instead of staying silenced forever; the `retire` parameter it replaces is gone.

Also fixed, in its own commit: tests/test_net.py's liveness helper caught only FileNotFoundError, while /proc/<pid>/stat raises ProcessLookupError when the task vanishes mid-read — the very outcome its assertion wants. It surfaced as a flake once the added listener tests shifted full-suite timing.

Follow-up not taken (outside the ACs): each shell call still blocks the tick for up to the 10-second IPC timeout, so a hanging shell can make the listener look unresponsive for that long. The spec accepts and documents this; docs/internals.md now names it.

stage: impl-review - ran [2026-09-06T11:00Z..2026-09-06T11:20Z] (codex:gpt-6-astra:medium, fan-out x3; round 1 NEEDS_WORK with 3 findings, all fixed; round 2 SHIP unanimous)
## Evidence
- Commits: 49b49a5c998ed1872ea07c4923ac2b1df5363e11, 3c9769259de123c6c16433eb4de58be8e0c14954, 264d55f7e9ef03f138c2a107cdaf2f5dfa8fcc0d
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (460 tests, OK; baseline 451 OK), green receipt .flow/tmp/green-receipts/264d55f7-unittest.json
- PRs: