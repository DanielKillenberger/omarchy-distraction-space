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
- Increment the XDG count file when the service dismisses a member toast. Delete matching Omarchy history files this dismiss created. No command, widget, or history screen reads the count while focus is on.
- After successful lift, if any count is above zero, one `notify()` lists per-app counts and may play one sound through the existing helper. Do not add a new sound player. Clear the file after a successful notice. Keep counts if the notice send fails. Zero counts skip the grouped notice. Keep the existing "Focus mode off" toast.
- README Use/Install/intro cover mute scope, catch-up, apply-fail / lift-fail, the `service` kind, and `plugins[]` load. Manifest `description` and `barWidget.description` mention the mute and the catch-up.
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
- Individual banners are discarded, not replayed. Omarchy `showHistory` must not show this spec's blocked pings while focus is on.
- The notification server does not play sounds. R5 is optional ("may") via the existing `notify()` helper.
- fn-1 may also edit `README.md` on another branch. Keep notification copy in the existing Use/Install sections and do not rewrite the network-block docs that are not in this tree yet.

### Acceptance
## Acceptance
- [ ] Count file updates per mapped app and has no mid-focus reader or new command
- [ ] Dismissed member toasts are not left in Omarchy history while focus is on
- [ ] Successful lift with counts sends exactly one grouped notice that may play one sound through the existing helper
- [ ] Successful lift with zero counts sends no grouped notice
- [ ] README and manifest describe mute, restore, grouped count, apply-fail / lift-fail, and the Quickshell service load
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
