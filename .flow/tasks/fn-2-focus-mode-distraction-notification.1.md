---
satisfies: [R1, R2, R3, R6, R8]
---
# fn-2-focus-mode-distraction-notification.1 Per-app Quickshell filter and stream mute

## Description
Land apply and lift for the Quickshell notification service plus the session stream watcher (R1, R2, R6, R8, lift half of R3). Split from the count/catch-up work so the early proof can fail before any summary UI is written.

**Size:** M
**Files:** `distractions`, `NotificationFilter.qml` (new), `manifest.json`, `tests/test_notification_block.py` (new)
**Touches:** [distractions, NotificationFilter.qml, manifest.json, tests/test_notification_block.py]

### Approach
- Add named `apply_notification_block` / `lift_notification_block` and call them from `enable_focus`, `disable_focus`, and `listen` when the focus flag is on. Leave network-block hooks for fn-1.
- Add a `service` kind and `entryPoints.service` next to the existing bar widget. Apply ensures `shell.json` `plugins[]` lists this plugin, then `omarchy-shell shell rescanPlugins`. Lift disarms. It does not remove `plugins[]`.
- Service matches member toasts by `app` / `appIcon` / desktop-entry and dismisses with `omarchy-shell notifications dismiss <summary>`. Never call `toggleDnd`, `setDnd`, or `omarchy-toggle-notification-silencing`.
- Arm a stream watcher for the focus session. Native apps match PW `application.name` / `application.process.binary`. Chromium PWAs match `/proc/<pid>/cmdline` host or app-id only. Snapshot muted node ids. Lift unmutes those ids. Do not mute bare Chrome. Do not restart PipeWire or WirePlumber.
- Snapshot then rollback on apply fail. Tell the user via `notify()`. Focus still turns on.
- Unit-test the identity map, snapshot/rollback, "do not toggle DND", and "do not mute bare Chrome" with fakes. No live compositor required.

### Investigation targets
**Required** (read before coding):
- `distractions:37-44` — `notify()` helper to reuse on apply/lift fail
- `distractions:180-184` — `enable_focus()` apply hook
- `distractions:187-197` — `disable_focus()` lift hook
- `distractions:237-260` — `listen()` must reapply when focus is on
- `hypr/windows.lua:4-9` — shipped membership to map
- `BarWidget.qml:1-38` — Quickshell imports, `IpcHandler`, `Process` patterns to match
- `manifest.json:11-16` — add `service` kind and entry point beside `barWidget`

**Optional** (reference as needed):
- `hypr/bindings.lua:5-17` — focus toggle and Super+Alt+D (unnamed class stays out of the mute set)
- `.flow/memory/declined/notification-exceptions.md` — no urgent bypass

### Key context
- Live daemon is Quickshell `NotificationServer` (`docs/notifications.md` on basecamp/omarchy default). DND is one boolean. Per-app hide is this plugin's service, not `toggleDnd`.
- IPC can dismiss by summary substring. `dismissAll` fails R2.
- PipeWire properties cannot distinguish Chromium PWAs. Cmdline host/app-id is the PWA sound key. Hidden cmdline is an accepted miss, not an all-Chrome mute.
- New streams must be evaluated while armed. One-shot `pactl` of current sink-inputs is not enough.
- `omarchy-notification-send` defaults to `omarchy-action` and must stay visible.

### Acceptance
## Acceptance
- [ ] Apply hides banners for mapped workspace apps only and does not call `toggleDnd` / `setDnd` / `omarchy-toggle-notification-silencing`
- [ ] Stream watcher mutes matching nodes only, including nodes created after apply (default sink stays up; bare Chrome is never muted)
- [ ] Apply fail notifies, rolls back this spec's mutation, and still turns focus on
- [ ] Lift disarms the service and unmutes only node ids this spec muted
- [ ] `listen` reapplies when the focus flag is on
- [ ] Identity map refuses a rule that matches generic Chrome / Chromium
- [ ] `python3 -m py_compile distractions` and `python3 -m unittest discover -s tests -p 'test_*.py'` pass
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
