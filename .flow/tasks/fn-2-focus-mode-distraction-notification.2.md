---
satisfies: [R3, R4, R5, R7]
---
# fn-2-focus-mode-distraction-notification.2 Grouped catch-up count and docs

## Description
Count blocked pings with no mid-focus reader, send one grouped notice after a successful lift (R3 remainder, R4, R5, R7), and update user docs. Depends on apply/lift from fn-2-focus-mode-distraction-notification.1.

**Size:** M
**Files:** `distractions`, `NotificationFilter.qml`, `README.md`, `manifest.json`, `tests/test_notification_count.py` (new)
**Touches:** [distractions, NotificationFilter.qml, README.md, manifest.json, tests/test_notification_count.py]

### Approach
- Increment the XDG count file only after task 1's exact-row suppression and serialized popup-file delete are queued. Serialize QML increments through one helper queue; each helper takes the count-file `flock`, read/merges, fsyncs a temp file, and atomically renames. The suppression bypasses archive, so it creates no Omarchy history file.
- Lift disarms the service and waits for its `drained` acknowledgement before catch-up. Python takes the same count lock for read plus successful-notice clear. If any count is above zero, one `notify()` lists per-app counts and may play one sound through the existing helper. Clear only after successful notice; retain on failure/timeout. Zero counts skip it. Keep the existing "Focus mode off" toast.
- README Use/Install/intro cover mute scope, catch-up, apply-fail / lift-fail, and the dual `service` kind loaded through the existing bar-layout enablement. Manifest `description` and `barWidget.description` mention the mute and the catch-up.
- No new `distractions` subcommand. No changelog file unless one already exists (it does not).

### Investigation targets
**Required** (read before coding):
- `distractions:37-44` — `notify()` copy pattern for the grouped notice
- `distractions:187-197` — lift-then-notice order in `disable_focus()`
- `README.md:3-66` — Install / Use / Commands structure to extend
- `manifest.json:7-21` — `description` and `barWidget.description`

**Optional** (reference as needed):
- `.flow/memory/declined/notification-extra-ui.md` — no history screen
- `BarWidget.qml:63-76` — eye tooltip voice to match

### Key context
- Individual banners are discarded, not replayed. Task 1 removes the exact live row/ref and queues deletion behind its persisted popup write without invoking `dismissPopup`; Omarchy `showHistory` must not show this spec's blocked pings while focus is on.
- The notification server does not play sounds. R5 is optional ("may") via the existing `notify()` helper.
- fn-1 may also edit `README.md` on another branch. Keep notification copy in the existing Use/Install sections and do not rewrite the network-block docs that are not in this tree yet.

### Acceptance
## Acceptance
- [ ] Count increments and catch-up read/clear share a `flock` and atomic rename; lift waits for disarmed-and-drained so a boundary ping is counted or stays visible, never lost
- [ ] Suppressed member toasts create no Omarchy history entry and are not visible through `showHistory` while focus is on
- [ ] Successful lift with counts sends exactly one grouped notice that may play one sound through the existing helper
- [ ] Successful lift with zero counts sends no grouped notice
- [ ] Drain timeout is a lift failure and preserves counts; notice failure also preserves counts
- [ ] README and manifest describe mute, restore, grouped count, apply-fail / lift-fail, and the Quickshell service load
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` passes
## Done summary
# fn-2-focus-mode-distraction-notification.2

Grouped catch-up count and docs.

After exact-row suppression, QML serializes `count-increment` through one helper queue. Each helper takes a dedicated count-file flock, merges, fsyncs a temp file, and atomically renames. Failed increments retry and keep the label plus pendingOps until a write succeeds; drain reports error until then so lift cannot look drained.

Successful lift waits for disarmed-and-drained, then one grouped `notify()` lists per-app counts and may play one sound. Clear only after a successful notice. Zero counts skip it. Notify has a bounded subprocess timeout. The existing Focus mode off toast stays.

README and manifest cover mute, restore, grouped count, apply-fail / lift-fail, and the dual service kind loaded through the existing bar-layout enablement.

Host impl-review (gpt-5.6-sol-high): SHIP after two NEEDS_WORK rounds (notify timeout + increment retain).
## Evidence
- Commits: 1ed262d83598c3520db2439eb043b6a0d4a26cbd, 014eca06840b52c8fa5088fcc87fb5401f3acc70, 5190615152015a2773d92b5f51aa2b58d3d29d84
- Tests: python3 -m unittest tests.test_notification_count, python3 -m unittest discover -s tests -p 'test_*.py'
- PRs: https://github.com/DanielKillenberger/omarchy-distraction-space/pull/2