---
satisfies: [R1, R2]
---
# fn-30-publish-reviewed-v3-and-refresh-the.1 Publish tested v3 through PR23 and refresh issue4518

## Description
Correct docs/marketplace-submission.md, amend existing PR23 with reviewed stacked branches, validate, merge exact head and edit existing submission with merged SHA. Record external evidence and verify done.

## Acceptance
- [ ] TBD

## Done summary
Amended PR23 with all reviewed v3 improvements and fn28/fn29 UI fixes, corrected marketplace notes, and merged exact verified head0c683e4 as 8996d60870b7943ff407de64ee208349943cc849. Both Python3.11 and3.14 full suites passed451 tests each with1 intentional skip; plugin validation passed. Server confirms MERGED and the squash tree exactly matches the verified head. Existing marketplace issue4518 was updated and read back byte-identical to the prepared v3 body, preserving metadata/checklist/history. No release procedure was found, so no tag or GitHub release was created.

User explicitly authorized the merge based on final checks. No hosted CI/review policy exists; recorded local Fable reviews and actual local tests are the evidence, not fabricated hosted checks. Marketplace admission remains pending.
## Evidence
- Commits: 0c683e40c7d50d712a59a9d19fbf70d5b0b08f79, 8996d60870b7943ff407de64ee208349943cc849
- Tests: Python3.14 final full suite451 tests OK,1 intentional skip; /tmp/fn29-full-tests-final.log, Python3.11 final full suite451 tests OK,1 intentional skip; /tmp/ds-v3-final-python311.log, omarchy plugin validate .: PASS, Squash merge tree identical to verified PR head, Marketplace issue body read-back matches v3 notes and exact merged SHA
- PRs: https://github.com/DanielKillenberger/omarchy-distraction-space/pull/23