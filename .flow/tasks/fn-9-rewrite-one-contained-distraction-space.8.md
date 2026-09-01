---
satisfies: [R10, R14]
---
# fn-9-rewrite-one-contained-distraction-space.8 Cutover: deletions, hypr snippets, manifest, README, migration check, line cap

## Description
Delete `focus_block.py`, `focus_dns.py`, `NotificationFilter.qml`, `PingCapture.qml`, `notification-members.json`, `app-list-defaults.json`, `defaults/destinations.json`, `focus.json`, and every old test file. Update `hypr/*.lua` to the documented bindings, `manifest.json` to kind `bar-widget` only with the new description, and rewrite `README.md` (install, setup, keys table, config schema, CLI, what fn-10 adds later). Run the migration against a copy of this machine's old `app-list.json`/`focus.json` in a temp HOME and record the result in the done summary. Add a test asserting non-test Python stays under 2,000 lines and that no deleted file exists.

**Files:** deletions, `hypr/*.lua`, `manifest.json`, `README.md`, `tests/test_tree.py`.

**Touches:** [focus_block.py, focus_dns.py, NotificationFilter.qml, PingCapture.qml, notification-members.json, app-list-defaults.json, defaults/**, focus.json, tests/**, hypr/**, manifest.json, README.md]
## Acceptance
- None of the deleted files exist; `git grep focus_block` is empty.
- `python3 -m unittest discover tests` passes; non-test Python under 2,000 lines.
- README documents every CLI command in the spec's API Contracts and the full config schema.
- Migration on the copied old files yields the expected `list` and `log`.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
