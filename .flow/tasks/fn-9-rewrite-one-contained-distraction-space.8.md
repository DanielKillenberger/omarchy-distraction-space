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
Blocked:
NEEDS_HUMAN: R14 line cap. The cutover work is complete and committed on worktree branch `wt/fn-9.8` (fd761e5; patch at `/tmp/flow-handover/fn-9/fn-9.8-cutover.patch` and in the run notes dir), with every test green except `test_tree.test_non_test_python_under_line_cap`: non-test Python is 3,290 lines against the spec's 2,000. Options: raise the cap in R14 and `LINE_CAP` (3,500 fits the reviewed code), drop the cap, or commission a trim task that reopens reviewed modules. After the decision, cherry-pick fd761e5 onto the branch, adjust `LINE_CAP` if chosen, run the suite, and complete the task.
## Evidence
- Commits:
- Tests:
- PRs:
