---
satisfies: [R1, R2, R3, R4]
---
# fn-36-marketplace-review-no-agent-instruction.1 Implement the marketplace review fixes

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
Both marketplace findings at bcfc76a are closed in the repository itself. `AGENTS.md` and `CLAUDE.md` are untracked and ignored (working copies stay on disk), and README's contributing section says agent instruction files are kept outside the repository. `ds/setup.py` takes its wrapper and sudoers destinations from the module constants with no environment override; `install()` and `remove()` refuse, before sudo, a destination that is not exactly canonical and name the path (the writable-ancestor check stays as defence in depth); the root transaction is rendered from the same constants at call time and refuses a non-canonical argv path before reading the payload or creating, staging, or renaming anything. Tests reach sandbox destinations only by patching the module in-process (`_point_destinations` in tests/test_setup.py, a sitecustomize for the CLI subprocess in `_cli_site`, `mock.patch.object` in tests/test_clone.py); new tests: `test_environment_never_moves_the_destinations`, `test_cli_ignores_destination_environment_variables`, `test_a_destination_that_is_not_canonical_stops_setup_before_sudo`, `test_root_transaction_refuses_a_non_canonical_path_before_touching_anything`. No doc presented the two variables as supported, so nothing to remove there.

Inherited flake, not fixed here: `tests/test_net.py::test_timeout_still_kills_descendant_after_parent_exits` races on `/proc/<pid>/stat` (ProcessLookupError between the existence check and the read); it fails roughly 1 run in 3 in isolation on untouched code and deserves its own change. Follow-up worth noting: `SPEC.md` still cross-links `CLAUDE.md` in a comment; harmless, but a fresh clone no longer carries that file.

stage: impl-review - ran [round 1 SHIP] (codex fan-out, gpt-6-astra medium, three draws all SHIP, rid f7a274ab84e9453cab73c7fc780eaa45) (model: codex gpt-6-astra medium)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 57255e5ba0767d3ae4a667870d27ea48e3a58c14
- Tests: baseline: green - PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (451 tests, rc 0, pre-edit), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (run 1 on 57255e5: 455 tests, rc 1 - single error in tests/test_net.py test_timeout_still_kills_descendant_after_parent_exits, an inherited /proc/<pid>/stat read race in files this task does not touch; reproduces 1 in 3 isolated runs), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (run 2 on 57255e5: 455 tests, rc 0, OK skipped=1 - receipted), PATH=/usr/bin:$PATH python3 -m unittest tests.test_setup tests.test_clone tests.test_net (focused, 91 tests), red-first: the four new tests fail against the pre-change ds/setup.py for the intended reasons (env override moves the paths; no refusal; no _transaction_script)
- PRs: