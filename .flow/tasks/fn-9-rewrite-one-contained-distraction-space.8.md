---
satisfies: [R10, R14]
---
# fn-9-rewrite-one-contained-distraction-space.8 Cutover: deletions, hypr snippets, manifest, README, migration check

## Description
Delete `focus_block.py`, `focus_dns.py`, `NotificationFilter.qml`, `PingCapture.qml`, `notification-members.json`, `app-list-defaults.json`, `defaults/destinations.json`, `focus.json`, and every old test file. Update `hypr/*.lua` to the documented bindings, `manifest.json` to kind `bar-widget` only with the new description, and rewrite `README.md` (install, setup, keys table, config schema, CLI, what fn-10 adds later). Run the migration against a copy of this machine's old `app-list.json`/`focus.json` in a temp HOME and record the result in the done summary. Add a test asserting that no deleted file exists.

**Files:** deletions, `hypr/*.lua`, `manifest.json`, `README.md`, `tests/test_tree.py`.

**Touches:** [focus_block.py, focus_dns.py, NotificationFilter.qml, PingCapture.qml, notification-members.json, app-list-defaults.json, defaults/**, focus.json, tests/**, hypr/**, manifest.json, README.md]
## Acceptance
- None of the deleted files exist; `git grep focus_block` is empty.
- `python3 -m unittest discover tests` passes.
- README documents every CLI command in the spec's API Contracts and the full config schema.
- Migration on the copied old files yields the expected `list` and `log`.

## Done summary
Owner dropped R14 line-count budget (rewrite size check only; not a product AC). Cutover cherry-picked onto the branch (b6e276d). Removed LINE_CAP / test_non_test_python_under_line_cap from tests/test_tree.py; kept deleted-file and leftover-name checks. R14 in the spec is deletions + suite green. Full suite: Ran 163 tests in 51.230s — OK (skipped=1).
## Evidence
- Commits: b6e276d825c3222c91eb84c716a826ef4b2f2132
- Tests: python3 -m unittest discover -s tests — Ran 163 tests in 51.230s OK (skipped=1)
- PRs: