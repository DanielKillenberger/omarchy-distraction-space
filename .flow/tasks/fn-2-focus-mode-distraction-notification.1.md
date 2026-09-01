---
satisfies: [R1, R2, R3, R6, R8]
---
# fn-2-focus-mode-distraction-notification.1 Per-app Quickshell filter and stream mute

## Description
Land apply and lift for the Quickshell notification service plus the session stream watcher (R1, R2, R6, R8, lift half of R3). Split from the count/catch-up work so the early proof can fail before any summary UI is written.

**Size:** M
**Files:** `distractions`, `NotificationFilter.qml` (new), `notification-members.json` (new), `manifest.json`, `tests/test_notification_block.py` (new)
**Touches:** [distractions, NotificationFilter.qml, notification-members.json, manifest.json, tests/test_notification_block.py]

### Approach
- Add named `apply_notification_block` / `lift_notification_block` and call them from `enable_focus`, `disable_focus`, and `listen` when the focus flag is on. Leave network-block hooks for fn-1.
- Add a `service` kind and `entryPoints.service` next to the existing bar widget. Install/update performs one `omarchy-shell shell rescanPlugins` and verifies ping after the manifest change. Steady-state apply never rescans because reload destroys the live notification service. The existing `bar.layout` reference already enables all declared kinds; do not add a redundant `plugins[]` entry. Lift disarms.
- Resolve `shell.serviceFor("omarchy.notifications")` lazily with a bounded retry timer; plugin IPC `ping` reports ready only after binding and API checks. Observe `popupModel` with an invisible `Instantiator`; `onObjectAdded` captures `originalId` + `timestamp` without mutating synchronously. Native rows match app/icon. Chromium-derived rows parse only the anchored leading origin token used by `NotificationLogic.js`, normalize and exact-match its host; a host later in prose and generic browser identity never match. For a live member, use `Qt.callLater`, relocate by immutable keys, re-check identity/`isRestoredRow`, verify the ref is current, then queue file deletion, remove that index, and dismiss the ref. Never use summary/all dismissal or DND.
- Apply waits for ready `ping` and verifies the built-in service exposes `popupModel`, `liveRefs`, `isRestoredRow`, and `deletePopupFileFor`; timeout or API mismatch rolls back under R8.
- Read one canonical `notification-members.json` from QML and Python; test parity with all named app rules in `hypr/windows.lua`.
- Make the session-long `listen` process the only stream-watcher owner. A worker thread parses a long-lived `pactl subscribe`; sink-input events trigger `pactl --format=json list sink-inputs`, and exact inputs mute through `pactl set-sink-input-mute`. Short-lived toggles write a focus generation and wait for runtime status acknowledgement; they never spawn a fallback. Missing/broken pactl is R8/R3 failure. Native apps match Pulse app/binary keys. Chromium PWAs walk bounded `/proc` ancestry and require a shipped host/app-id, with PID-reuse guards. Snapshot muted input ids; lift acknowledges after unmuting only those ids. Never mute bare Chrome or restart audio services.
- Snapshot then rollback on apply fail. Tell the user via `notify()`. Focus still turns on.
- Serialize apply/lift with a dedicated short-lived lock file, not the `LISTEN_LOCK` held by the session listener.
- On every service `Component.onCompleted`, re-read focus, lazily bind, and re-arm. For each restored member row observed by the Instantiator, asynchronously test its exact filename in the active popup directory with bounded retries on misses. Only an active-file hit is relocated/removed, deleted from `restoredPopups`, and deleted on disk; a history-only `showHistory` row remains. No restore-complete signal or history scan is assumed.
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
- live `shell/shell.qml:263-345` — injected `shell`, `serviceFor`, and third-party service loader

**Optional** (reference as needed):
- `hypr/bindings.lua:5-17` — focus toggle and Super+Alt+D (unnamed class stays out of the mute set)
- `.flow/memory/declined/notification-exceptions.md` — no urgent bypass

### Key context
- Live daemon is Quickshell `NotificationServer` (`docs/notifications.md` on basecamp/omarchy default). DND is one boolean. Per-app hide is this plugin's service, not `toggleDnd`.
- `dismiss(summary)` is an all-app substring purge and fails R2. Same-engine access through injected `shell.serviceFor("omarchy.notifications")` is the exact-row path; `notifications` alone names only the IPC target.
- PipeWire properties cannot distinguish Chromium PWAs. A host/app-id in the leaf or bounded ancestor cmdline is the PWA sound key. Hidden/missing proc identity is an accepted miss, not an all-Chrome mute.
- New streams must be evaluated while armed. One-shot `pactl` of current sink-inputs is not enough.
- `omarchy-notification-send` defaults to `omarchy-action` and must stay visible.

### Acceptance
## Acceptance
- [ ] Apply resolves the live built-in service, waits for plugin `ping`, hides only the exact mapped row, and does not call summary/all dismissal or DND
- [ ] Live Omarchy proof: member/non-member popups with identical summaries leave only the non-member; no member popup/history file survives; a member `showHistory` replay remains untouched
- [ ] Every shipped Chromium PWA banner exact-matches only its leading origin host; plain-browser, malformed/no-host, and a non-leading member-host-in-prose fixture remain visible, with no generic Chrome/Chromium/Brave match
- [ ] Invisible `Instantiator` captures immutable row keys, defers mutation with `Qt.callLater`, relocates/revalidates before removal, and checks `isRestoredRow` before any live-ref lookup, including an old/new id-collision fixture
- [ ] Stream watcher mutes matching nodes only, including nodes created after apply; Chromium matches a host/app-id on a leaf or bounded ancestor (default sink stays up; bare Chrome is never muted)
- [ ] `pactl subscribe` events discover new sink inputs; missing/dead subscribe or list command fails and reports status instead of silently claiming armed
- [ ] Exactly one watcher runs inside `listen`; short-lived toggles receive matching generation acknowledgements, and missing/unhealthy listener or timeout fails without spawning a watcher
- [ ] Apply fail notifies, rolls back this spec's mutation, and still turns focus on
- [ ] Lift disarms the service and unmutes only node ids this spec muted
- [ ] `listen` reapplies when the focus flag is on
- [ ] Identity map refuses a rule that matches generic Chrome / Chromium
- [ ] QML and Python consume the same `notification-members.json`, whose named members match `hypr/windows.lua`
- [ ] Live early proof exercises every shipped Chromium PWA sound and fails if ancestry matching does not produce reliable true positives
- [ ] Service reload while a member delete is queued lazily rebinds/re-arms and uses exact active-file existence to reconcile the restored row; a history-only replay remains
- [ ] `python3 -m py_compile distractions` and `python3 -m unittest discover -s tests -p 'test_*.py'` pass; `qmllint NotificationFilter.qml` passes when qmllint is installed, while live ping/proof remains mandatory
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
