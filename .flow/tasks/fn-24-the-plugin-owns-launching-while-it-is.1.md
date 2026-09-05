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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
