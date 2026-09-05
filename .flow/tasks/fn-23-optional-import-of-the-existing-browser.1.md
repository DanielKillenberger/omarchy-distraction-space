---
satisfies: [R1, R2, R3, R4]
---
# fn-23-optional-import-of-the-existing-browser.1 Implement distractions profile import with tests and docs

## Description

Add the one-time copy of the existing browser profile into the distraction profile, as a new verb, with tests and the README section. The spec body carries the design: source resolution from the picked browser, the two running-browser preconditions through `/proc`, the `--replace` rename, the cache-skipping copy through a temporary sibling renamed into place.

## Files

- `ds/profile.py` (new): `source_for(cfg)`, `is_running(user_data_dir, proc_root)`, `import_profile(src, dst, replace)`; env override for the `/proc` root the same way `ds/cgroup.py` takes `DS_PROC_ROOT`, and for the home directory the same way the existing modules resolve `XDG_*`.
- `distractions`: `profile` subcommand with `import` sub-verb, `--from`, `--replace`; exit codes 0/1/2.
- `README.md`: Upgrading section gains the optional import with preconditions and the double sign-in note; Commands section lists the verb.
- `docs/internals.md`: one paragraph on the copy discipline and the test count.
- `tests/test_profile.py` (new): fixtures under a sandbox home, fake `/proc` entries carrying `cmdline` with and without `--user-data-dir`, stale `SingletonLock`, `--replace` rename and never-delete, copy failure leaving backup and temporary sibling, cache directories skipped, source-inside-destination refusal.

## Reuse

- `ds/launch.py`: `pick_browser`, `_default_browser_id`, `profile_dir`, `PROFILE`, `HANDLER_ID`, `state.read_entries()["previous_handler"]` for the recorded previous handler.
- `ds/cgroup.py`: the `DS_PROC_ROOT` convention for reading `/proc`.
- `tests/harness.py` `Sandbox` for the isolated home and fake binaries.

## Acceptance
- [ ] R1 through R4 of the spec hold, each exercised by tests/test_profile.py.
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes offline.
- [ ] README Upgrading and Commands sections and docs/internals.md describe the verb.

## Done summary
`distractions profile import [--from DIR] [--replace]` (ds/profile.py) copies the default browser's main profile, or a named Chromium profile, into the distraction profile once: source resolved from the browser `open` would pick (config argv, Omarchy default, or the recorded previous handler; Chrome, Chromium, Brave, Edge, Opera, Vivaldi, Helium), refused without `Preferences` or when the source and destination overlap, refused while either browser runs (a `/proc` cmdline scan for `--user-data-dir=` or the browser's binary on its default directory, plus a live `SingletonLock`), copied minus the regenerable caches and singleton files into a `Distraction.import-<pid>` sibling renamed into place, with `--replace` moving the existing profile to `Distraction.bak-<stamp>` and never deleting it. tests/test_profile.py holds 17 cases against fixture profiles and a fake `/proc` (R1 to R4, every enumerated error case, path aliases, and the symlinked destination); README Upgrading and Commands and docs/internals.md describe the verb.

baseline: green (PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, 350 tests pre-edit); verify: 367 tests green, receipt .flow/tmp/green-receipts/48c597ba-unittest.json

stage: impl-review - ran, cursor gpt-5.6-sol-high, 3 rounds (NEEDS_WORK x2 -> SHIP)

Follow-up (not built): tests/harness.py Sandbox does not override XDG_DATA_HOME; this task's tests set it themselves and assert their paths sit inside the sandbox. Moving that override into harness.py is a separate change.
## Evidence
- Commits: 92130c846c352abcd5fa2924e67525792f5549d1, 1d55315d5b6fb556450e4217d79c5d976a1cd0a3, 48c597bae93b547b56c759402e7b6ac2d1c0ecce
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, ./distractions profile import --help
- PRs: