# Optional import of the existing browser profile into the distraction profile

## Goal & Context
<!-- scope: business -->

Version 3 gives listed web products their own browser profile, so the person logs into each web app once more after the upgrade. The person asked for an optional step that copies the existing profile over instead, so logins, cookies, passwords, bookmarks, history, and extensions carry into the distraction profile in one go.

On this machine on 2026-09-05 the default browser is Google Chrome with its main profile at `~/.config/google-chrome/Default` (1.4 GB, of which about 400 MB is regenerable cache), the distraction profile lives at `~/.local/share/omarchy/distraction-space/browser/Distraction` (412 MB, already logged into two apps), and Chrome encrypts cookies and passwords with a per-user key held in the keyring through the secret portal, not a per-profile key, so a copied profile decrypts in the same session.

This is a one-time snapshot. Nothing keeps the two profiles in sync afterwards, and the copied extensions run in the distraction profile from then on.

## Architecture & Data Models
<!-- scope: technical -->

**One verb, never part of setup.** `distractions profile import [--from <dir>] [--replace]` lives in a new `ds/profile.py` and is wired in `distractions`. Setup never runs it: it needs both browsers closed and moves about a gigabyte, which is nothing to do silently.

**Source.** Without `--from`, the source is the main profile of the browser `open` would pick: the desktop id from `launch.pick_browser`'s resolution (the recorded previous handler when the plugin is the default) maps to a config directory, `google-chrome` to `~/.config/google-chrome`, `chromium` to `~/.config/chromium`, `brave` to `~/.config/BraveSoftware/Brave-Browser`, `microsoft-edge` to `~/.config/microsoft-edge`, `vivaldi` to `~/.config/vivaldi`, and the profile is that directory's `Default`. `--from` names a profile directory explicitly and skips the mapping. A source that has no `Preferences` file is not a Chromium profile and is refused.

**Destination.** `launch.profile_dir() / launch.PROFILE`, the same directory `open` launches with `--profile-directory=Distraction`.

**Preconditions, all checked before any byte moves.** The source browser is not running: no process of this user carries `--user-data-dir=<source user-data-dir>` and no process runs from that browser without a `--user-data-dir` at all (its default), checked through `/proc`; and the source user-data directory holds no live `SingletonLock` whose target names a running pid on this host. The distraction browser is not running: no process carries `--user-data-dir=<profile_dir()>`. The destination does not exist, or `--replace` was given, in which case the existing profile is renamed to `Distraction.bak-<YYYYMMDD-HHMMSS>` beside it before the copy and never deleted.

**The copy.** `shutil.copytree` from the source profile to the destination, symlinks preserved, ignoring the cache directories that Chromium regenerates: `Cache`, `Code Cache`, `GPUCache`, `DawnCache`, `DawnGraphiteCache`, `DawnWebGPUCache`, `ShaderCache`, `GrShaderCache`, `Service Worker/CacheStorage`, `Service Worker/ScriptCache`, and the two singleton files `SingletonLock`, `SingletonSocket`, `SingletonCookie` if they sit inside the profile. The copy goes to a temporary sibling `Distraction.import-<pid>` first and is renamed into place only when it completed, so a failed or interrupted copy leaves either no destination or the renamed backup, never a half profile. Progress is one line per 100 MB on stderr and a final line with the byte count and the time.

**After the copy.** The command prints the destination path, the byte count, and one sentence that the next `open` registers the profile and that the Google account will show as signed in twice. It does not launch anything.

**State.** Nothing in `state.json`. The verb is an operation, not a mode.

## API Contracts
<!-- scope: technical -->

- `distractions profile import [--from <profile-dir>] [--replace]` - exit 0 after a completed copy, 1 when a precondition fails or the copy fails, 2 on usage. Every refusal names the exact reason and the fix on one stderr line: which browser is running, that the destination exists and `--replace` would move it aside, that the source is not a Chromium profile.
- No new config keys. No change to `setup`, `open`, or the listener.
- The catalog and the expansion are untouched.

## Edge Cases & Constraints
<!-- scope: technical -->

- The source browser is running: refused, naming the browser. Copying a live LevelDB and SQLite set yields a corrupt profile.
- The distraction browser is running: refused, because Chrome would keep writing into the directory being replaced.
- `--replace` with an existing backup name collision: the timestamp carries seconds, and a second collision within a second appends a counter.
- The temporary sibling from an earlier interrupted run exists: it is moved aside to `Distraction.import-<pid>.stale` rather than reused, and the command says so.
- Not enough free space: `copytree` fails part way, the temporary sibling is left in place with a message naming it and the command exits 1; the destination and the backup are untouched.
- The source is the same directory as the destination, or one contains the other: refused.
- Firefox as the default browser: there is no Chromium profile to import; refused with the message that only Chromium-family profiles import, and `--from` still works for a Chromium profile elsewhere.
- The profile directory of Chrome contains `Local State` one level up, not inside the profile; it is never copied. Chrome regenerates the profile registry on the next launch and the existing `Local State` of the distraction user-data directory keeps its own entries.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** `distractions profile import` with both browsers closed and no existing destination copies the default browser's main profile into `Distraction`, skipping the listed cache directories and singleton files, through a temporary sibling renamed into place, and prints the destination and the byte count. Errors: a source without `Preferences` exits 1 naming it; a non-Chromium default browser exits 1 unless `--from` names a Chromium profile; a source that is or contains the destination exits 1.
- **R2:** With the source browser or the distraction browser running, the command exits 1 before any byte moves, naming which one. Errors: a stale `SingletonLock` whose pid is not alive does not count as running.
- **R3:** With an existing destination the command exits 1 unless `--replace`, which renames the existing profile to a dated backup beside it and never deletes it. Errors: a failed copy after the rename leaves the backup and the temporary sibling in place and names both.
- **R4:** The README's Upgrading section describes the verb as the optional alternative to logging in again, with its preconditions and the double sign-in note, and `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes offline with the copy exercised against fixture directories and running-browser checks against a fake `/proc`. Errors: none.

## Boundaries
<!-- scope: business -->

- No ongoing sync between the two profiles.
- No import of Firefox profiles.
- No selective import; the whole profile minus caches, or nothing.
- No launch of the browser by the command.
- No change to setup, remove, or the listener.

## Decision Context
<!-- scope: both -->

- Whole-profile copy over cookie-only extraction: Chrome's encrypted stores decrypt with the per-user keyring key, so copying the directory carries everything at once with no format knowledge, and the price is the one-time disk cost.
- A temporary sibling renamed into place over copying straight to the destination, so an interrupted copy can never leave a half profile that Chrome would try to repair.
- Rename over delete for the existing profile with `--replace`: the existing profile holds logins the person made after the upgrade.
- A separate verb over a setup flag: setup runs with sudo and rescans the shell; a gigabyte copy that needs both browsers closed does not belong in it.

## Quick commands

```bash
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
./distractions profile import --help
```

## Early proof point

Task fn-23.1 is the whole spec; the copy against fixture directories with a fake `/proc` proves the preconditions and the rename-into-place discipline.

## Requirement coverage

| Req | Description | Task(s) | Gap justification |
|-----|-------------|---------|-------------------|
| R1 | Copy with cache skip through a temporary sibling | .1 | — |
| R2 | Refuse while either browser runs | .1 | — |
| R3 | `--replace` renames, never deletes | .1 | — |
| R4 | README section and offline tests | .1 | — |
