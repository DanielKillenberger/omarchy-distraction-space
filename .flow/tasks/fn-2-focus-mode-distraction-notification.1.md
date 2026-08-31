---
satisfies: [R1, R2, R3, R6, R8]
---
# fn-2-focus-mode-distraction-notification.1 Per-app mako mode and PipeWire mute

## Description
Land apply and lift for the custom mako mode plus PipeWire per-client mute (R1, R2, R6, R8, lift half of R3). Split from the count/catch-up work so the early proof can fail before any summary UI is written.

**Size:** M
**Files:** `distractions`, plugin-owned mako include (new), `tests/test_notification_block.py` (new)
**Touches:** [distractions, tests/test_notification_block.py]

### Approach
- Add named `apply_notification_block` / `lift_notification_block` and call them from `enable_focus`, `disable_focus`, and `listen` when the focus flag is on. Leave network-block hooks for fn-1.
- Plugin-owned include with `[mode=focus-distraction ...]` `invisible=1` criteria. Apply uses `makoctl mode -a`. Lift uses `makoctl mode -r`. Never call `omarchy-toggle-notification-silencing` or toggle `do-not-disturb`.
- Map shipped window-rule apps to mako `app-name` / `desktop-entry` and PipeWire client keys. Chromium PWAs match `desktop-entry`, never a bare Chrome `app-name`.
- Snapshot then rollback on apply fail. Tell the user via `notify()`. Focus still turns on.
- Unit-test the map, snapshot/rollback, and "do not toggle DND" contract with fakes. No live compositor required.

### Investigation targets
**Required** (read before coding):
- `distractions:37-44` — `notify()` helper to reuse on apply/lift fail
- `distractions:180-184` — `enable_focus()` apply hook
- `distractions:187-197` — `disable_focus()` lift hook
- `distractions:237-260` — `listen()` must reapply when focus is on
- `hypr/windows.lua:4-9` — shipped membership to map

**Optional** (reference as needed):
- `hypr/bindings.lua:5-17` — focus toggle and Super+Alt+D (unnamed class stays out of the mute set)
- `.flow/memory/declined/notification-exceptions.md` — no urgent bypass

### Key context
- Omarchy mute is `makoctl mode -t do-not-disturb` (whole desktop). This task must not use it.
- `default/mako/core.ini` already shows per-app `invisible` and mode-scoped criteria. Theme `mako.ini` is the wrong write target.
- Issue 5073. Banner hide does not stop app sounds. PipeWire per-client mute is required for R6.
- `omarchy-notification-send` / `notify-send` toasts must remain visible under the custom mode.

### Acceptance

## Acceptance
- [ ] Apply hides banners for mapped workspace apps only and does not toggle `do-not-disturb`
- [ ] PipeWire mute targets matching clients only (default sink stays up)
- [ ] Apply fail notifies, rolls back this spec's mutation, and still turns focus on
- [ ] Lift removes the custom mode and unmutes only clients this spec muted
- [ ] `listen` reapplies when the focus flag is on
- [ ] `python3 -m py_compile distractions` and `python3 -m unittest discover -s tests -p 'test_*.py'` pass


## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
