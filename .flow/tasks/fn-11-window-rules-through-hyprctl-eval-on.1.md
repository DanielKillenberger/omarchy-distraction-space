---
satisfies: [R1, R2, R3, R4]
---
# fn-11-window-rules-through-hyprctl-eval-on.1 Implement Window rules through hyprctl eval on the Lua config

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
Named window rules are now installed through `hyprctl eval` on Hyprland's Lua config: `set_named_rule` sends one Lua fragment that disables any previous handle for the name, calls `hl.window_rule({ name, match = { class }, workspace = "name:distraction silent" })`, and stores the handle in `_G.omarchy_ds_rules`; `disable_named_rule` sends a fragment that `set_enabled(false)`s the stored handle inside `pcall` and is a no-op when absent. `lua_string` escapes names and class regexes as Lua literals. The socket2 `configreloaded` event re-applies the active rule set and re-scans off-space clients under `_reload_lock`. `hyprctl keyword` is gone from `distractions`.

R-ID coverage (tests/test_enforcement.py):
- R1: `test_named_rule_update_enable_disable` (name, class, workspace in one eval fragment), `test_eval_failure_raises_inside_set_named_rule`, `test_create_failure_rolls_back_batch` (rollback, notify, last-good not written), `test_lua_string_round_trips_through_lua` (backslash, quotes, `]]`, control chars, run under real Lua).
- R2: `test_keyword_path_is_gone_and_refused_by_double`; the double exits 1 on `keyword`, and the whole suite passes on it.
- R3: `test_lua_fragments_disable_old_handle_and_noop_when_missing` (stub `hl` under lua5.4: old handle disabled before the new create; disable of missing/unknown name is a silent no-op), `test_lua_fragment_create_error_is_not_swallowed`, `test_disable_failure_keeps_desired_and_leftovers`.
- R4: `test_configreloaded_reapplies_rules_and_rescans`, `test_configreloaded_apply_failure_notifies_and_keeps_listener`, `test_configreloaded_waits_for_reload_lock`.

Live smoke (permitted): `hyprctl eval` of the generated set fragment for class `^zzz-omarchy-ds-probe$` printed `ok`; the disable fragment printed `ok`; a second disable (missing handle) printed `ok`. No `hyprctl reload`, no real-class rules.

baseline: green (python3 -m unittest discover -s tests, 382 tests, rc 0). Verify at HEAD: 390 tests, rc 0; green receipt .flow/tmp/green-receipts/29b54050-unittest.json. Pre-existing harness noise, unchanged by this task: one `FileNotFoundError ... hypr/hyprctl.log` traceback printed by a background thread of the test double after temp-dir cleanup, present once in the baseline log and once in the verify log; the suite still reports OK.

Follow-ups noted, not built: the Lua-side `pcall` around `hl.window_rule` was deliberately not added (a create error must propagate so `hyprctl eval` exits nonzero); `handle_reload_conn` still does not re-scan existing clients after a list reload (unchanged behavior, outside this spec).

stage: impl-review - ran (model: gpt-5.6-sol-high via cursor backend; verdict SHIP, 0 findings)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 29b54050ab110157e470e8720b91367e3cc9c452
- Tests: python3 -m unittest discover -s tests, python3 -m unittest tests.test_enforcement
- PRs: