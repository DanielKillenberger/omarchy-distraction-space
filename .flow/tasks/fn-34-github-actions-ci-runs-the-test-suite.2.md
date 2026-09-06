---
satisfies: [R2]
---
# fn-34-github-actions-ci-runs-the-test-suite.2 Make the suite green on the GitHub runner

## Description
TBD

## Acceptance
The tests.yml job is green on ubuntu-latest for both matrix entries. Tests that need a Lua interpreter get it from a documented apt step; tests that need a user systemd bus or another desktop facility the runner lacks are skipped with the facility named, never weakened. The first observed green run on GitHub is the evidence.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
