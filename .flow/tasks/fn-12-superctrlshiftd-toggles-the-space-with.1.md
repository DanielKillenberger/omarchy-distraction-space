---
satisfies: [R1, R2, R3, R4]
---
# fn-12-superctrlshiftd-toggles-the-space-with.1 Implement Super+Ctrl+Shift+D toggles the space with no confirm

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
The plugin's toggle binding moves from Super+D to Super+Ctrl+Shift+D and entering the space no longer shows the Enter / Stay dialog: `lock.enter()` checks on-space and lock, then switches; `ui.confirm_enter`, the confirm hold file, `_try_confirm_lock`/`_release`, and `nudges.entry_confirm` (schema, defaults, settings menu, listener empty expansion, README) are removed, while a saved config that still carries `entry_confirm` loads, validates, and round-trips as an inert unknown key. Banner body, block page, block banner, README, and windows.lua now say Super+Ctrl+Shift+D.

- R1: hypr/bindings.lua binds `SUPER + CTRL + SHIFT + D`; Super+Alt+D and Super+Ctrl+Shift+F unchanged — pinned by `tests/test_tree.py::test_bindings_toggle_is_super_ctrl_shift_d`.
- R2: enter/toggle switch immediately with `ds.ui.select` patched to raise (no menu-tool call); locked → notice, exit 1, no switch — `tests/test_enter.py` (`test_enter_switches_without_prompt`, `test_toggle_off_space_enters`, `test_locked_enter_shows_notice_and_does_not_switch`, `test_toggle_off_space_locked_refuses`).
- R3: `tests/test_config.py::test_saved_entry_confirm_loads_and_survives_save` (True/False), `tests/test_enter.py::test_saved_entry_confirm_key_is_inert`, settings-menu index tests updated.
- R4: `tests/test_tree.py::test_no_bare_old_hotkey_outside_flow` rejects any bare "Super+D" outside .flow/ except inside Super+Ctrl+Shift+D / Super+Alt+D.

Baseline green (179), verify green (178: 6 confirm-era tests removed, 5 added). Review: cursor:gpt-5.6-sol-high SHIP first pass, 0 findings.

stage: impl-review - ran (cursor:gpt-5.6-sol-high, 1 round, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: fe223348fa1da6f6bec43d07e1a87fb47a8d525f
- Tests: baseline: green (179 tests, rc=0) - cd <worktree> && PATH=/usr/bin:$PATH python3 -m unittest discover -s tests > <log> 2>&1, red-first: 11 changed/new tests failed against d1b67f9 source (enter opened a menu, old hotkey text, schema key present), verify: cd <worktree> && PATH=/usr/bin:$PATH python3 -m unittest discover -s tests > <log> 2>&1 -> Ran 178 tests, OK, suite_rc=0, gate receipt: unittest - python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
- PRs: