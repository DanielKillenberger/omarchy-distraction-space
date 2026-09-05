---
satisfies: [R3, R4]
---
# fn-22-the-space-is-a-process-group-one.4 Setup: launcher entries with backup, URL handler, entries manifest, remove, displaced check

## Description
The reversible install surface for links and launchers (R3, R4). Split from `open` because setup only writes desktop files and calls `xdg-settings`; it never launches anything.

**Size:** M
**Files:** `ds/setup.py`, `ds/listener.py`, `tests/test_setup.py`, `tests/test_listener.py`
**Touches:** [ds/setup.py, ds/listener.py, tests/test_setup.py, tests/test_listener.py]

### Approach
- `ds/setup.py` `sync_entries(exp, cfg)`, called from `install()` after `sync_slice()` and the root transaction (fn-21's single sudo prompt untouched), all user-level:
  1. For each listed product write `<apps>/<Name>.desktop` (web products: the same filename Omarchy's web-app installer uses, i.e. the product name; native products: `<desktop-id>.desktop`) with `Exec=<plugin-dir>/distractions open <name>`, `Icon`, `StartupWMClass` for the profile class. If a file exists at that path and the manifest does not own it, move it to `<state>/entries-backup/<filename>` first and record `backup`.
  2. When `open_links_in_space` is true, write `<apps>/io.github.danielkillenberger.distraction-space.desktop` with `MimeType=x-scheme-handler/http;x-scheme-handler/https;`, `Exec=<plugin-dir>/distractions open %u`, `NoDisplay=true`; record `previous_handler` from `xdg-settings get default-web-browser` (skip when it already is the plugin id); run `xdg-settings set default-web-browser <id>`; exit 4 or any failure → state `links: displaced` plus one notice; success → `links: on`. When false → `links: off`, no handler file.
  3. `update-desktop-database <apps>` when present.
  4. Write `entries.json` last. Any failure before that rolls back every file written or moved in this run (memory `bug/data/ownership-record-accepted-any-json-and-2026-09-02` pattern: finish-or-rollback in one function).
- `remove()`: user-level undo first, in reverse: restore the previous default with `xdg-settings set` when the current default is the plugin, delete exactly the manifest's paths, move each backup back, delete `entries.json`, print the profile directory path and that it was kept; then `remove_slice()`, then the existing flush and root teardown. A file not in the manifest is never touched.
- `ds/listener.py`: `check_links()` on start and on the periodic tick: `xdg-settings get default-web-browser` compared to the plugin id when `open_links_in_space` is true; mismatch → state `links: displaced` and one notice per listener lifetime naming `distractions setup`.

### Investigation targets
**Required** (read before coding):
- `ds/setup.py:408-409,500-577` — `_record_path`, `sync_clone`, `_finish_clone` manifest pattern
- `ds/setup.py:613-666` — `install()` / `remove()` ordering
- `tests/test_setup.py` — existing sandboxed setup tests
- `/usr/share/omarchy/bin/omarchy-webapp-install:200-240` — where Omarchy writes web-app entries and their filename shape

**Optional:**
- `ds/listener.py:360-372` — `tick()` for the periodic check
- `~/.local/share/applications/YouTube.desktop` — an Omarchy entry to shadow

### Key context
- `xdg-settings` and `xdg-mime` run as the person, never through sudo.
- `xdg-settings` exit codes: 2 missing file, 3 missing tool, 4 action failed. All map to `displaced`, not to a setup failure.

## Acceptance
- [ ] With a pre-existing Omarchy `YouTube.desktop` in the sandbox apps dir, setup moves it to `entries-backup/`, writes the plugin entry, records both in `entries.json`; `setup --remove` restores the original byte-for-byte and deletes only manifest paths
- [ ] A stray file not in the manifest survives `setup --remove`
- [ ] Setup registers the handler, records `previous_handler`, state reads `links: on`; a fake `xdg-settings` exiting 4 leaves `links: displaced` with one notice and setup still exits 0
- [ ] `open_links_in_space: false` writes no handler and reports `links: off`
- [ ] A write failure mid-run leaves no manifest and no plugin-written files behind
- [ ] Listener reports `links: displaced` on a later tick when the default changes, one notice only
- [ ] The root transaction is still a single sudo call and the fn-21 tests pass unchanged
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes


## Done summary
Setup writes one launcher entry per listed product and the URL-handler entry under the person's applications directory, moves aside whole any file it does not own into `entries-backup/`, records everything in `entries.json` written after every file it names, and rolls the whole run back on a write failure. `setup --remove` undoes the user-level half first: hands the recorded default back while the plugin still holds it, deletes exactly the manifest's paths, moves backups home byte-for-byte, drops the manifest, and prints the kept browser profile path. The listener's `check_links` runs on start, reload, and every period, asks `xdg-settings` only once the manifest names the handler, and notifies once per lifetime naming `distractions setup` (R3, R4).

### What changed (commits d5601c7, d02c955, a3eaec9; base 31235f1; the worker's 3fe0528 was cherry-picked as d5601c7)
- `ds/setup.py`: `sync_entries`, `remove_entries`, `_plan`, `_render_entry`, `_render_handler`, `_class_prefix`, `_wm_class`, `_write_text`, `_rollback`, `_restore_handler`, `default_handler`, `_owned_files`, `_update_desktop_database`. After review: `default_handler` reports whether xdg-settings answered, and an unanswered query never changes the default at install nor deletes anything at remove; a failed restore keeps the handler; the manifest is refused whole unless every path is a direct child of the applications directory and every backup its twin under the backup directory; owned entries about to be replaced or dropped are staged so rollback restores their exact bytes; the database refresh is best effort and runs after the record; the window-class prefix follows a configured browser argv; switching links off restores the default before the handler file goes and keeps the file with `links: displaced` when that fails.
- `ds/listener.py`: `check_links` on start, reload, and the periodic tick; `_links_state` treats an unanswered query as displaced.
- Tests: `tests/test_setup.py` (shadow and restore, re-run convergence, dropped entry, exit-4 displaced, switch off, mid-run rollback, unwritable directory, unanswered query at install and remove, failed restore at remove, foreign manifest refused, rollback of drifted owned files and a dropped entry, best-effort database refresh, configured-browser class, links-off hand-back), `tests/test_listener.py` (displaced on a later tick with one notice; off when nothing is registered or the switch is off), `tests/test_clone.py` (fake `xdg-settings` and `update-desktop-database`, sandboxed `XDG_DATA_HOME`; test-only Touches deviation).

### Review
cursor / gpt-5.6-sol-high, three rounds: round 1 NEEDS_WORK (five findings: lost previous handler on a failed query, unvalidated manifest paths, incomplete rollback, database timeout escaping, class prefix ignoring the configured browser), round 2 NEEDS_WORK (links-off dropped the handler before the restore was known), round 3 SHIP with R3 and R4 met.

### Gates
- baseline: green via handoff (b5bd9393)
- verify: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at a3eaec9 on the integrated target, 336 tests, OK; receipt `.flow/tmp/green-receipts/a3eaec98-unittest.json`
- classify: FULL

stage: impl-review - ran (cursor gpt-5.6-sol-high, 3 rounds, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: d5601c7, d02c955, a3eaec9
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 336 tests at a3eaec9 on the integrated target; receipt .flow/tmp/green-receipts/a3eaec98-unittest.json), PATH=/usr/bin:$PATH python3 -m unittest tests.test_setup tests.test_clone tests.test_listener
- PRs: