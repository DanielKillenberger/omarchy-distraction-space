---
satisfies: [R1, R2, R3, R4]
---
# fn-5-focus-mode-enable-network-block-crash.1 Implement Focus-mode enable network-block crash

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
Privilege-run now always uses text mode and decodes stderr/stdout before missing-table checks, so unprivileged nft bytes no longer TypeError; permission denied still retries pkexec then sudo, and a missing table still raises MissingTable. Tests lock bytes stderr for permission-denied, missing-table, and empty output (R1–R4).

Live plugin probe: `privileged(["nft", "list", "table", "inet", "omarchy_focus_missing_probe_fn5"])` raised MissingTable (`Error: No such file or directory`), not TypeError.

baseline: none (parent spec has no Quick commands)
stage: impl-review - ran [cursor:gpt-5.6-sol-high] (model: gpt-5.6-sol-high)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 372010a98a53ae74e5a30380253094b8f51db918
- Tests: python3 -m unittest discover -s tests -p 'test_*.py', python3 -m py_compile focus_block.py tests/test_focus_block.py
- PRs: