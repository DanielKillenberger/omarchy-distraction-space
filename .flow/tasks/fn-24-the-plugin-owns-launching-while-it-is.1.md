---
satisfies: [R1, R2, R5]
---
# fn-24-the-plugin-owns-launching-while-it-is.1 open forwards what it does not own: no target, browser flags, --app, and the profile that never asks

## Description
`distractions open` grows into the launcher Omarchy's scripts expect when the plugin is the default browser, per spec sections "open forwards what it does not own" and "The distraction profile never asks".

### Files

- `ds/launch.py`: `open_target` takes the full argv after `open` (`--app`, an optional target, `-`-prefixed flags in any order); `forward(url=None, flags=(), app=False)` builds the previous handler's Exec with the URL field code removed when there is no URL, `--app=<url>` when `app` is set, and the flags appended; the plugin's own entry is skipped as `_is_own_launcher` does today and `omarchy-launch-browser` (with `BROWSER` dropped) is the fallback, exit 1 with one line when that is missing too. Before the first slice launch, when `profile_dir()/PROFILE` does not exist, create it with a `Preferences` file `{"browser": {"check_default_browser": false}}`; never touch an existing directory.
- `ds/profile.py`: after the copy, set `browser.check_default_browser` to false in the copied `Preferences` (JSON load, set, atomic write).
- `distractions`: the `open` parser accepts `--app`, an optional `target`, and passes unknown `-` flags through (`parse_known_args` or `nargs=argparse.REMAINDER`, whichever keeps `open --help` sane).
- `tests/test_launch.py`, `tests/test_profile.py`: no target, `--incognito` only, `--app` unlisted with extra args, `--app` listed, own-entry skip, fallback missing, profile directory created with the preference and left alone when present, import sets the preference.

### Reuse

`exec_argv`, `parse_exec`, `_detached`, `_is_own_launcher`, `state.read_entries()["previous_handler"]`, the fake browsers on PATH in `tests/test_launch.py`.

### Manual proof (record in the summary)

On this machine `omarchy-launch-browser` and `omarchy-launch-browser --private` must open Google Chrome through the plugin's handler; run them once after the change and note the result. Do not leave extra Chrome windows open afterwards beyond what they create.
## Acceptance
- [ ] TBD

## Done summary
`distractions open` now forwards what the space does not own: no target and flags-only run the previous handler's Exec with the URL field code dropped and the flags appended (R1); `--app <unlisted url> [extra]` forwards `--app=<url>` plus the extras, a listed target opens in the space as before (R2); the first slice launch publishes the distraction profile with `browser.check_default_browser: false` by rename of a complete sibling and never touches an existing directory, and `profile import` sets the same key in the copied `Preferences` before the rename (R5).

What the spec did not spell out and the implementation settled:
- Omarchy's browser keybind runs the handler Exec's first token alone, so the bare binary (`distractions`, `distractions --incognito`) is `open`; `tests/test_status.py::test_no_command_exits_2` was retired by that AC and its coverage moved to `tests/test_launch.py` (the file is outside the declared list; a one-test deletion, flagged for the conductor).
- `open`'s tail never goes through argparse (`-headless` is not `-h`; a flag's separate value stays with its flag); `launch.split_args` takes the first scheme-carrying token, else the first non-dash token, as the target. `open_target(argv)` takes the raw tail as the task note asked.
- The `omarchy-launch-browser` fallback resolves the default browser again; when that is this plugin it would recurse, so `forward` refuses with one line and exit 1 instead. An unparseable previous-handler Exec now falls back too (spec text) instead of dropping the link; the pinned test was updated by that intent.
- Tests: R1 `test_no_target_forwards_the_bare_browser_with_flags_in_any_order`, `test_unusable_previous_handler_falls_back_with_browser_dropped` (fallback, guard, missing script); R2 `test_app_forwards_an_unlisted_url_as_an_app_window`; R5 `test_first_launch_creates_the_profile_that_never_asks`, `test_profile_creation_that_loses_the_race_leaves_the_winner_alone`, `assert_imported_preferences` in test_profile plus `test_preferences_that_are_not_json_fail_the_copy_like_a_disk_error`.

Manual proof: the installed clone at /home/daniel/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space was fast-forwarded from the local repo (no push) to 1d20b32 and again to cf14090; `omarchy-launch-browser` and `omarchy-launch-browser --private` each ran `distractions` / `distractions --incognito` through the handler (journal) and opened Google Chrome's New Tab and New Incognito Tab windows; both were closed afterwards, nothing else left open.

Follow-ups, not built: a flag that takes a separate value before a non-URL target (`open --class Example YouTube`) reads `Example` as the target; the help text says to use `--flag=value`.

baseline: green (367 tests at 2a2a900)
stage: impl-review - ran [codex fan-out round 1 NEEDS_WORK (2 findings: argparse read browser flags as its own; profile dir published before Preferences) .. round 2 SHIP at cf14090]
## Evidence
- Commits: 1d20b3243cb82402d95072b77d6f486ae52cb861, cf14090fac0629b638ba837830c10cccae35e2a5
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (baseline: green, 367 tests, 142 s at 2a2a900; verify: green, 371 tests, 142 s at cf14090; GREEN_RECEIPT .flow/tmp/green-receipts/cf14090f-unittest.json), PATH=/usr/bin:$PATH python3 -m unittest tests.test_launch tests.test_profile tests.test_status (52 tests, green), ./distractions open --help (exit 0), manual proof: omarchy-launch-browser and omarchy-launch-browser --private through the installed clone at cf14090 opened Google Chrome (New Tab, New Incognito Tab); both windows closed afterwards
- PRs: