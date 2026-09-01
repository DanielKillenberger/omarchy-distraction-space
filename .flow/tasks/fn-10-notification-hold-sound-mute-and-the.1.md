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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
