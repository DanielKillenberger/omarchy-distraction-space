---
satisfies: [R1, R2, R3]
---
# fn-34-github-actions-ci-runs-the-test-suite.1 Implement GitHub Actions CI runs the test suite

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
Added `.github/workflows/tests.yml`: on push to `main` and every pull request, `ubuntu-latest` runs `python3 -m unittest discover -s tests` on a Python 3.11 / 3.x matrix (`actions/checkout@v4`, `actions/setup-python@v5`, `permissions: contents: read`, `timeout-minutes: 20`, no pip, no apt, no secrets). README Contributing names the workflow and its one command. Implemented over a grok-4.6 bridge from a brief that carried the verified test-harness facts; the diff was reviewed against the spec before commit.

Why the CI command drops the README's `PATH=/usr/bin:$PATH` prefix: that prefix only keeps a local mise/pyenv `python3` shim off PATH. On a GitHub runner it would put Ubuntu's system `/usr/bin/python3` ahead of the setup-python interpreter and run both matrix entries on the same Python. The workflow comment and the README paragraph both say this.

R2 needed no apt step and no test edits: the suite fakes every desktop tool via `tests/harness.py`; the only real binaries the tests reach are `patch` and `cat`, both preinstalled on `ubuntu-latest`; `tests/test_nft.py` already skips with "nft not on PATH", the kernel test is gated on `DS_LIVE_NFT_TEST=1`, and `tests/test_clone.py` skips when the Omarchy notifications plugin is absent.

Honest limit: GitHub Actions cannot run locally. The job's green status is asserted from the local run of the same command (451 tests, 1 skipped, green on Python 3.14.7) and the runner facts above, not from an observed workflow run. The first push to GitHub is the real check.

baseline: green (PATH=/usr/bin:$PATH python3 -m unittest discover -s tests; no receipt existed at HEAD)
stage: impl-review - ran (codex:gpt-6-astra:medium fan-out, 3/3 draws SHIP, 0 findings, receipt /tmp/impl-review-receipt-aed9e3047b69-fn-34-github-actions-ci-runs-the-test-suite.1.json) (model: codex gpt-6-astra medium)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: ed590db6a7ef72230770bacc4191db1642526a5f
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (baseline: green, 451 tests, 1 skipped), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 451 tests, 1 skipped; receipt .flow/tmp/green-receipts/ed590db6-unittest.json), python3 -c 'yaml.safe_load(.github/workflows/tests.yml)' (parses: on.push.branches=[main], on.pull_request, matrix 3.11/3.x, 4 steps)
- PRs: