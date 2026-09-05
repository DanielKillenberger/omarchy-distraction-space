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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
