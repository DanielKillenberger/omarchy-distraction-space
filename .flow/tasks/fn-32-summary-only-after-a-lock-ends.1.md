---
satisfies: [R1, R2, R3, R4]
---
# fn-32-summary-only-after-a-lock-ends.1 Implement summary.after

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
`summary.after` decides whether entering the space shows the "While you were away" notice. `any`, the default, keeps today's behaviour: the notice on a lock ending and on entering the space. `unlock` keeps the notice for lock endings only; entering the space still claims the held records, clears the count, and hands the counts to the enter hook, silently. Validation rejects any other value naming `summary.after`; a config without the key loads with `any`. Both unlock paths, the listener's expiry and the manual command, are unchanged.

Implemented over a grok-4.6 bridge from a precise brief (config plumbing per the project's routing rule), diff reviewed on the session model, full suite green: 463 tests, 1 skipped.

stage: impl-review - ran [2026-09-06T12:05Z..2026-09-06T12:07Z] (model: codex gpt-6-astra medium, fan-out x3, all SHIP, 0 findings; requested by the user after the first receipt)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 4cd3b5f879e334405ab650cbacb5dac889995411
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (463 tests, OK, 1 skipped)
- PRs: