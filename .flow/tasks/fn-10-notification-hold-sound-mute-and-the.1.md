---
satisfies: [R1, R7, R8]
---
# fn-10-notification-hold-sound-mute-and-the.1 Shell patch file and the notification-service clone lifecycle in setup

## Description
Export the `notifications-silenced-senders` commit from `~/Projects/omarchy` as `shell/notifications-silenced-senders.patch` (unified diff of `Service.qml` and `NotificationLogic.js` only). Add the clone step to `ds/setup.py`: detect `silencedSenders` on the built-in, `omarchy plugin clone omarchy.notifications`, `patch -p1 --dry-run` then apply, record first-party SHA-256s in `clone.json`, re-clone on drift, remove on patch failure or once the built-in has the method, never touch a clone without `clone.json`, `--remove` support. Add the start-time drift check to the listener (notice only). Tests run against a fake `omarchy-plugin-clone`, fake `omarchy-shell`, and a temp copy of the first-party files.

**Files:** `shell/notifications-silenced-senders.patch`, `ds/setup.py`, `ds/listener.py`, `tests/test_clone.py`.

## Acceptance
- Patch applies cleanly to the installed first-party files (`/usr/share/omarchy/shell/plugins/notifications`).
- Each lifecycle branch (fresh, unchanged, drift, patch failure, upstream has method, foreign clone) behaves as specified in a test.
- `--remove` removes only a plugin-created clone.
- Upstream `test/shell.d/notifications-test.sh` passes on the patched checkout.

## Done summary
Shipped `shell/notifications-silenced-senders.patch` (unified diff of `Service.qml` and `NotificationLogic.js` from omarchy cd6e991, `--relative` so `patch -p1` applies inside the plugin directory; the patched installed files come out byte-identical to the branch) and added the notification-service clone lifecycle to `ds/setup.py` as the step between the wrapper install and the rescan: `sync_clone()` clones `omarchy.notifications` while the first-party `Service.qml` lacks `function silencedSenders(`, dry-runs the patch against the first-party files before cloning, applies it in the clone, and records the SHA-256 of every first-party file plus the patch hash in `clone.json`; an unchanged fingerprint is a no-op, drift re-clones, a patch that no longer applies removes the clone and exits 1, the built-in growing the method removes the clone, and a `<user>.notifications` directory without a record naming exactly that clone is reported and left alone. `remove_clone()` backs `setup --remove`. The listener calls `setup.clone_drift()` once at start and shows one notice pointing at `distractions setup`; it never re-clones.

Two facts from the live shell shaped the design. Enabling a clone puts `omarchy.notifications` on the shell's `disabledPlugins`, so every removal first runs `omarchy-shell shell setPluginEnabled <id> false` (what `omarchy-plugin-remove` does) and refuses to delete the directory when that call fails, so a shell that is down never leaves the machine without a notification server. And with a clone active the `notifications` IPC target answers `silencedSenders` from the clone, so "built-in has the method" is read from the first-party source text, not from IPC.

Tests (`tests/test_clone.py`, 14 cases): fresh, unchanged, drift (first-party file and refreshed patch), patch failure (with and without an existing clone), clone tool failing early and late, corrupt clone / unwritable record rollback, upstream method, foreign clone with a subTest table of malformed records, `--remove` including the shell-down guard, listener notice, `install()`/`remove()` ordering with the clone step before the final rescan, missing source, and a dry run of the shipped patch against a temp copy of the installed first-party files (skips when Omarchy is absent). Lifecycle tests run against a fake `omarchy-plugin-clone`, fake `omarchy-shell`, and a first-party preimage rebuilt from the patch's context lines, so they need no `/usr/share`. Confirmed red first (module surface missing without the implementation).

Edit outside the declared Files: one env line in `tests/test_setup.py` `setUp` (`DS_NOTIFICATIONS_SOURCE` -> absent path) so the pre-existing `install()` tests take the "source missing, hold unavailable" branch instead of reaching the real `omarchy-plugin-clone` on PATH. No dispatcher or README change; README already describes the fn-10 clone step as pending and task 4 owns it.

Upstream acceptance: `bash test/shell.d/notifications-test.sh` from a temporary detached worktree of `~/Projects/omarchy` at cd6e991 ran headless under node, 145 assertions ok (8 on silencing), rc 0; the worktree was removed afterwards. Live machine untouched: no `distractions setup`, clone, rescan, or hyprctl against the desktop.

baseline: green (179 tests OK at 89989ae, `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests`)
gate: unittest full suite 193 OK at 50a5b0a; GREEN_RECEIPT .flow/tmp/green-receipts/50a5b0aa-unittest.json
stage: impl-review - ran [round 1 NEEDS_WORK (ownership check accepted any JSON record; clone creation not transactional) -> fixed in 50a5b0a -> round 2 SHIP], backend cursor
memory: bug/data/ownership-record-accepted-any-json-and-2026-09-02 captured
Follow-ups (not built): none required; the `omarchy-plugin-remove` backup-directory behaviour is bypassed deliberately by removing through the shell IPC plus rmtree.

stage: plan-sync - skipped(config: planSync.enabled != true)

## Evidence
- Commits: c33d2d028c1303d90c913448039a6344ee77fcff, 50a5b0aa434b6d76937f96ca1d5e39938825e643
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (193 tests OK at 50a5b0a; baseline 179 OK at 89989ae), PATH=/usr/bin:$PATH python3 -m unittest tests.test_clone tests.test_setup (23 tests OK), bash test/shell.d/notifications-test.sh in a temporary worktree of ~/Projects/omarchy at cd6e991 (145 ok, rc 0, worktree removed), patch -p1 --dry-run against a temp copy of /usr/share/omarchy/shell/plugins/notifications (applies; patched files byte-identical to cd6e991), GREEN_RECEIPT unittest 50a5b0aa
- PRs: