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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
