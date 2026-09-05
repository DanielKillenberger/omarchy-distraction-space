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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
