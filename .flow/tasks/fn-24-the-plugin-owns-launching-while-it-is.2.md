---
satisfies: [R3]
---
# fn-24-the-plugin-owns-launching-while-it-is.2 Setup routes every Omarchy web-app entry through the plugin, on setup, refresh, and the tick

## Description
Setup rewrites every Omarchy web-app entry that is not a listed product so unlisted web apps keep opening in the previous browser, per spec section "Setup routes every Omarchy web-app entry".

### Files

- `ds/setup.py`: `_plan` (or a sibling) scans `applications_dir()` for entries whose main-group Exec begins with `omarchy-launch-webapp`, excluding files the listed-product plan already writes; each becomes an owned entry with the original backed up under `entries-backup/` and recorded in `entries.json` exactly like a same-name listed file, Exec rewritten to `<absolute distractions> open --app <url> [extra args]` and every other key verbatim (the `parse_exec` grammar from `ds/launch.py` for the split, g_shell quoting on the way out). An unparseable Exec is skipped and logged once. `remove_entries` restores them through the existing backup path.
- `ds/listener.py`: `refresh` and the periodic tick re-run the entry sync (a cheap no-op when nothing changed), so a regenerated entry is rewritten within a minute; `check_links` unchanged.
- `tests/test_setup.py`, `tests/test_listener.py`: an unlisted Omarchy web app is rewritten with keys preserved and backed up, a listed one is not double-written, an unparseable Exec is left alone, remove restores, refresh rewrites a regenerated entry.

### Reuse

`sync_entries` staging and journal rollback, `_owned_files`, `state.read_entries`/`write_entries`, `launch.parse_exec`, `launch.read_exec`.
## Acceptance
- [ ] TBD

## Done summary
Setup now rewrites every Omarchy web-app entry that is not a listed product into `<distractions> open --app <url> [extra]` with every other key verbatim, backs the original up under `entries-backup/`, records it in `entries.json` like a same-name listed file, and `remove` restores it; the listener re-runs the entry sync on `refresh` and once a period, so a regenerated entry is rewritten within a minute (R3). An entry whose Exec cannot be parsed is left alone and named once per process on stderr.

What the spec left open and the implementation settled:
- The file half of `sync_entries` is `_sync_files`, a no-op when nothing changed (a few reads, no write, no desktop-cache refresh), so the minute tick costs nothing in the common case. The listener's entry point `setup.refresh_entries` runs only once setup has written the manifest and never touches the default browser: the handler stays as recorded, the recorded previous handler stands, `xdg-settings` is not asked (a displaced default remains `check_links`' notice).
- A file at any planned path that is not this plugin's launcher is Omarchy's and becomes the backup, replacing an older one, so the backup is always the latest entry displaced (a reinstalled web app's new icon survives). An owned launcher that is gone was removed by the person or Omarchy's remover: its backup goes with the record instead of resurrecting the web app on the next tick, and `remove_entries` follows the same rule.
- Dropping a listed product whose Omarchy file was shadowed now leaves a forwarder rather than handing the file back (R3 says every `omarchy-launch-webapp` entry is rewritten); `test_rerun_keeps_the_backup_and_a_dropped_entry_hands_its_file_back` was renamed and re-pinned by that intent.
- `setup` uses `launch._is_own_launcher` for "is this file ours": the definition has one owner and `ds/launch.py` is outside this task's files.
- Review round 1 (three codex draws) found two defects: an owned entry regenerated with a malformed Exec was logged "left alone" but restored from its stale backup (fixed: `_forward_entry` answers `KEEP`, the plan carries it with no text, the sync neither writes nor restores it), and the listener's sync ran unlocked beside `setup`/`remove` (fixed: `_entries_lock`, flock on `distraction-space.entries.lock` in the runtime dir; setup and remove wait up to `ENTRIES_LOCK_TIMEOUT` and report busy past it, the listener gives way at once). Round 2 caught the manifest-existence check outside that lock (moved inside). Round 3 SHIP.
- Test fixture: `tests/test_listener.py` had its applications directory under `runtime/data` while the harness pins the listener process's `XDG_DATA_HOME` to the sandbox `data/`; it now uses the harness directory for both, `_register_handler` writes the real rendered handler, and a fake `update-desktop-database` keeps the real tool out of the sandbox.
- Tests for R3: `test_unlisted_omarchy_web_app_is_rewritten_with_every_other_key_kept_and_remove_restores_it`, `test_an_omarchy_web_app_whose_exec_cannot_be_parsed_is_left_alone_and_named_once`, `test_a_regenerated_web_app_is_rewritten_from_the_new_file_and_a_removed_one_is_not_resurrected`, `test_an_owned_web_app_regenerated_with_a_malformed_exec_is_left_alone_and_still_recorded`, `test_one_entries_transaction_at_a_time_across_setup_remove_and_the_listener`, `test_the_listener_sync_keeps_nothing_a_remove_finished_before_it_took_the_lock` (tests/test_setup.py); `test_refresh_and_the_tick_rewrite_a_regenerated_web_app_and_never_touch_the_default` (tests/test_listener.py). Each was run red against the pre-fix code first.

Follow-ups, not built: `docs/internals.md` and the README do not yet describe the entry rewrite or the entries lock (R6, task .3). A persistent sync failure in the listener (unwritable applications directory, a refused manifest) prints to stderr once a period rather than once.

baseline: green via handoff (verified at cf14090f by fn-24-the-plugin-owns-launching-while-it-is.1)
stage: impl-review - ran [codex fan-out round 1 NEEDS_WORK (2 findings: malformed regenerated entry restored from stale backup; no lock beside setup/remove) .. round 2 NEEDS_WORK (existence check outside the lock) .. round 3 SHIP at 9410f58]
## Evidence
- Commits: 1ead900f150de0f420c9c0517e6de5f860ac5175, 03d6aa41d685c5e8ecab750c45df05e63b8341b7, 9410f5895944158ea5034883809c0448056a590c
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (378 tests, green at 9410f58; receipt .flow/tmp/green-receipts/9410f589-unittest.json), ./distractions open --help, ./distractions setup --help
- PRs: