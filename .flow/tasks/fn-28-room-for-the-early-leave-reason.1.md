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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
