---
satisfies: [R1, R2, R3]
---
# fn-29-type-focus-minutes-directly.1 Replace focus duration presets with direct minutes input

## Description
Update ds/ui.py prompt_lock, tests/test_ui.py and README.md. Check callers and tests/test_status.py signature contract. Quick: PATH=/usr/bin:$PATH python3 -m unittest tests.test_ui tests.test_lock tests.test_status.StubContractTests. Preserve fn28 reason width. Conductor owns Fable review, live native smoke, full gate and local installation.

## Acceptance
All R1-R3 in parent spec.

## Done summary
Replaced the searchable duration presets and Other option with direct native minutes input. Positive whole minutes work directly, and 0 maps to until manual unlock at the UI boundary. Native width500 makes the full hint visible. Empty/cancelled/invalid entry does not start a lock or ask purpose; purpose semantics and direct CLI duration behavior are unchanged. Native actual-helper probe verified37,0,Escape with lock bytes unchanged.

50 focused tests passed; final full suite451 tests OK with one intentional skip. Fable Claude CLI final review SHIP at42d17ca. Reviewed source installed locally at42d17ca, exact ui.py match, healthy/responsive listener without restart. Initial full run was stopped when visual smoke showed truncated hint; final width500 source passed the full gate.

stage: impl-review - ran (model: claude-fable-5-1)
stage: completion-review - skipped(policy: single-task, per-task SHIP covers spec surface)

No version bump, push, main merge, release or marketplace edits.
## Evidence
- Commits: 49f19878613510401102b079f9e4d9f56d2c2641, 42d17ca0bbbfb66383584c124542b81fa6a78554
- Tests: baseline: green; PATH=/usr/bin:$PATH python3 -m unittest tests.test_ui tests.test_lock tests.test_status.StubContractTests (47 tests; exit 0; /tmp/fn29-baseline.log), red regression: PATH=/usr/bin:$PATH python3 -m unittest tests.test_ui (18 expected failures against old preset flow; /tmp/fn29-red.log), PATH=/usr/bin:$PATH python3 -m unittest tests.test_ui tests.test_lock tests.test_status.StubContractTests (50 tests; exit 0; /tmp/fn29-focused.log), git diff --check (exit 0), gate classify: FULL; focused worker verification passed; conductor owns full gate, width regression: two focused native argv tests failed before width fix (10 subtest failures; /tmp/fn29-width-red.log), PATH=/usr/bin:$PATH python3 -m unittest tests.test_ui tests.test_lock tests.test_status.StubContractTests (width500 correction:50 tests passed; exit0; /tmp/fn29-width-focused.log), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests: PASS451 tests,1 intentional skip; /tmp/fn29-full-tests-final.log, Native helper/visual/local installation: .flow/evidence/fn-29-type-focus-minutes-directly.json, Final Fable Claude CLI SHIP: .flow/reviews/fn-29-type-focus-minutes-directly.1.json
- PRs: