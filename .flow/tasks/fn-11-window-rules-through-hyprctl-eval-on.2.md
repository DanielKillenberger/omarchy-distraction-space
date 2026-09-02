---
satisfies: [R1, R2, R3, R4]
---
# fn-11-window-rules-through-hyprctl-eval-on.2 Port the eval rule primitive and configreloaded re-apply into the fn-9 ds package

## Description
TBD

## Acceptance
R1-R4 of the parent spec hold in ds/hypr.py and ds/listener.py after the fn-9 rewrite landed on main: rules via hyprctl eval, no keyword path, handle-based disable, configreloaded re-apply and rescan. tests/test_hypr.py and tests/test_listener.py doubles refuse keyword.

## Done summary
Ported the eval rule primitive into the fn-9 package after PR #9 landed. `ds/hypr.py` installs each rule with one `hyprctl eval` fragment (`hl.window_rule`, handle kept in `_G.omarchy_ds_rules`, old handle retired first), disables through the stored handle, and records name-to-class in `rule-specs.json` beside `rules.json`. A failed create rolls the batch back (re-set from recorded class or disable), keeps both registries, notifies once, and returns False. `ds/listener.py` re-applies and rescans on socket2 `configreloaded`. Test doubles refuse `keyword` like the live parser and refuse an eval argument starting with `-` (hyprctl parses it as a flag; caught by the live smoke). Separately fixed `ds/net.py`: the flush call inherited stdin while the wrapper reads stdin to EOF, which hung the network worker whenever stdin was a live socket or pipe.

R-ID coverage: R1 `test_partial_install_failure_rolls_back_created_rules`, `test_hyprctl_failure_logged_and_skipped`; R2 `test_keyword_is_never_used_for_rules`, `test_keyword_double_refuses_like_the_lua_parser`; R3 `test_lua_fragments_disable_old_handle_and_noop_when_missing`, `test_reset_of_existing_name_is_restored_on_failure`, `test_failing_reset_of_existing_name_is_restored`; R4 `test_configreloaded_reapplies_rules_and_rescans`, `test_configreloaded_rule_failure_notifies_and_keeps_listener`.

stage: impl-review - ran (model: gpt-5.6-sol-high via cursor backend; SHIP on round 5 after 4 NEEDS_WORK rounds on rollback completeness)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 09d9757, 7c87476, 0a8e422, 1dce1c1, 74e7c81, 69f26ca, 8d7b8d5
- Tests: python3 -m unittest discover -s tests
- PRs: