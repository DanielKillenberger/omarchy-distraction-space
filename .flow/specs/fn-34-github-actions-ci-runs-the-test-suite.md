# GitHub Actions CI runs the test suite

## Conversation Evidence

> user (turn 1): "implement github actions to run ci in a new spec with grok 4.6 worker and astra review"
> user (turn 2): "add on top of stack"

## Goal & Context
<!-- Source-tag breakdown: 50% [user] / 50% [inferred] -->

Every push and pull request runs the plugin's unit tests on GitHub Actions, so a red suite is visible on the PR before review. [paraphrase] The project's own check command is the authority: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests`, which the repo already runs locally on Python 3.11 and 3.14. [inferred]

## Acceptance Criteria

- **R1:** A workflow under `.github/workflows/` runs on push to `main` and on every pull request, on Ubuntu, with a matrix of Python 3.11 and the newest stable 3.x the runner offers, and executes the repo's unittest discovery command. Errors: a failing test fails the job; the workflow needs no secrets and installs no Python dependencies beyond the standard library, since the plugin has none. [inferred]
- **R2:** System tools the tests shell out to and that the runner lacks are either present via a documented apt step or the affected tests skip cleanly on the runner, so the job is green on the current branch. Errors: a test that only fails for a missing desktop tool is skipped with the tool named, never deleted or weakened. [inferred]
- **R3:** The README's development section names the workflow and the one command it runs, and a status badge is not required. [inferred]

## Boundaries

- No linting, packaging, release, or deployment jobs. [inferred]
- No changes to test logic beyond a runner-only skip guard where R2 needs one. [inferred]

## Decision Context

A single unittest job mirrors what `flowctl` gates already run locally, so CI and the local gate cannot disagree about the command. [inferred]

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.1 |
| R2 | fn-N.1 |
| R3 | fn-N.1 |
