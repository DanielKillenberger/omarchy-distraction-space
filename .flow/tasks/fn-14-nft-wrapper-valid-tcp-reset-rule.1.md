---
satisfies: [R1, R2]
---
# fn-14-nft-wrapper-valid-tcp-reset-rule.1 Implement nft wrapper: valid TCP reset rule

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
The TCP reset rules now read `meta l4proto tcp reject with tcp reset`. Live proof recorded by the conductor after install (R2).

stage: impl-review - ran (model: gpt-5.6-sol-high via cursor backend; SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: e0fd498
- Tests: python3 -m unittest discover -s tests
- PRs: