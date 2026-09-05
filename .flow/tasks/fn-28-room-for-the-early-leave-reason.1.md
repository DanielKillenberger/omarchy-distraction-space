---
satisfies: [R1, R2, R3]
---
# fn-28-room-for-the-early-leave-reason.1 Widen the native early-leave reason prompt

## Description
Use optional keyword-only width in ds.ui.input and request900 only from prompt_reason. Preserve all existing text/cancel/error semantics. Add focused regression tests for native argv, long UTF-8 text and cancellation; verify lock refusal stays unchanged. Document native single-line limitation.

**Files:** ds/ui.py, tests/test_ui.py, tests/test_status.py, README.md
**Touches:** ds/ui.py, tests/test_ui.py, tests/test_status.py, README.md

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_ui tests.test_lock tests.test_status.StubContractTests

## Acceptance
All R1-R3. Conductor owns native visual smoke, Fable review and final Flow completion.

## Done summary
Widened only the native early-leave reason prompt from its default 300 to 900 logical units. Omarchy owns scaling and viewport clamping; the field remains single-line. Full UTF-8 text, cancellation, errors and lock validation are preserved. Native actual-helper smoke returned a complete 61-character reason and Escape returned None without changing lock state.

Fable (claude-fable-5-1, Claude CLI) reviewed final commit f75e837: SHIP. Full suite: 448 tests, OK with one intentional live skip. The initial full run exposed a stale helper-signature contract, now corrected and verified. Installed locally at f75e837; installed ui.py matches reviewed source and runtime health is healthy/responsive without listener restart.

stage: completion-review - skipped(policy: single-task, per-task SHIP covers spec surface)

No push, merge to main, version bump, release or marketplace changes.
## Evidence
- Commits: 7d9272b1f5be794a1a0ad4cb1fbc47c71810b710, f75e8374d8705bf06ff81cf73f87870f24242b98
- Tests: baseline: green via handoff (e3ebaee runtime identical to 62c9f61/3c8c949; 447 tests on Python 3.11 and 3.14, one intentional skip each), PATH=/usr/bin:$PATH python3 -m unittest tests.test_ui.UiTests.test_prompt_reason_width_preserves_utf8_ordinary_input_unchanged: red before fix (both min_chars cases missing --width 900); /tmp/fn28-red.log, PATH=/usr/bin:$PATH python3 -m unittest tests.test_ui tests.test_lock: PASS, 43 tests; /tmp/fn28-tests.log, git diff --check: PASS, flowctl gate classify: FULL (ds/ui.py executable changes); focused task gate passed; full suite and shared receipts conductor-owned, PATH=/usr/bin:$PATH python3 -m unittest tests.test_status.StubContractTests tests.test_ui: PASS, 25 tests; /tmp/fn28-contract-tests.log (updated intentionally changed signature contract after conductor full-suite failure), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests: PASS 448 tests, one intentional skip; /tmp/fn28-full-tests-final.log, Fable Claude CLI final implementation review: SHIP at f75e837; .flow/reviews/fn-28-room-for-the-early-leave-reason.1.json, Native helper and local installation verified: .flow/evidence/fn-28-room-for-the-early-leave-reason.json, stage: completion-review - skipped(policy: single-task, per-task SHIP covers spec surface)
- PRs: