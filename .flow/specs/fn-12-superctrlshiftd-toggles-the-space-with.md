# Super+Ctrl+Shift+D toggles the space with no confirm

## Conversation Evidence

> user: "can you make the default hotkey super+ctrl+shift+d and don't have a confirmation window just switch but make the hotkey combo hard enough to be a friction"

## Goal & Context

<!-- scope: business -->

The friction for entering the distraction space is the key combo itself, not a dialog. The default toggle binding moves from Super+D to Super+Ctrl+Shift+D. Pressing it switches immediately: enter when off the space, leave when on it. The Enter / Stay confirm window is removed. The lock keeps its behavior: while locked, the toggle still refuses with the lock notice.

## Architecture & Data Models

<!-- scope: technical -->

- `hypr/bindings.lua`: the toggle bind becomes `SUPER + CTRL + SHIFT + D`. Super+D is no longer bound by the plugin snippet (stock Omarchy may bind it; the snippet neither binds nor unbinds it). Super+Alt+D (move window there) and Super+Ctrl+Shift+F (lock or unlock) stay.
- `ds/lock.py`: `enter()` no longer consults `nudges.entry_confirm` or calls `ui.confirm_enter`; it checks on-space and lock, then goes to the space. `_try_confirm_lock`, `_entry_confirm_on`, and the confirm hold file go away if nothing else uses them.
- `ds/ui.py`: `confirm_enter` and the `nudges.entry_confirm` settings row are removed. `ds/config.py`: `entry_confirm` leaves `NUDGE_KEYS` and `DEFAULTS`; an `entry_confirm` key already present in a saved config is tolerated on load and preserved on save like any unknown key (the validator must not reject it). The listener's empty expansion drops the key too.
- User-facing text that says "Super+D" (README, the app banner body "Super+D opens it.", the block page line, `BarWidget.qml` tooltip if any, the `catalog`/`status` help) says "Super+Ctrl+Shift+D". README drops the sentence "Entering is a deliberate choice behind a confirm." and the `enter` row's confirm description.
- Tests: `tests/test_enter.py` confirm cases become "enter switches without a prompt" cases (patch `ui.confirm_enter` must not exist or never be called); config tests cover a saved config that still carries `entry_confirm`; a text test asserts no "Super+D" remains outside `.flow/` except as part of "Super+Ctrl+Shift+D" or "Super+Alt+D".

## Edge Cases & Constraints

<!-- scope: technical -->

- Locked: toggle off-space refuses with the lock notice, exit 1, workspace unchanged (unchanged behavior).
- Already on the space: toggle leaves via the next occupied workspace (unchanged).
- Saved config with `"entry_confirm": true` or `false`: loads, validates, round-trips on save; no effect.
- Menu tooling missing: no longer relevant to enter; enter never touches `omarchy-menu-select`.
- The bar widget middle click still runs `distractions toggle`.

## Quick commands

```bash
python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
```

Redirect the suite to a file. A leaked child in one test keeps a pipe open, so piping the suite through `tail` stalls.

## Acceptance Criteria

<!-- scope: both -->

- **R1:** The shipped `hypr/bindings.lua` binds `SUPER + CTRL + SHIFT + D` to `distractions toggle` and no longer binds `SUPER + D`. Super+Alt+D and Super+Ctrl+Shift+F keep their bindings.
- **R2:** `distractions enter` and `distractions toggle` off the space switch to `name:distraction` immediately with no confirm dialog and no menu-tool call. Errors: locked → lock notice, exit 1, no switch.
- **R3:** `entry_confirm` is gone from `NUDGE_KEYS`, `DEFAULTS`, the settings menu, and README. A saved config that still contains `nudges.entry_confirm` loads and validates, and the key survives a save. Errors: none; the key is inert.
- **R4:** Every user-facing "Super+D" reference (README, banner body, block page, tooltip, CLI help) reads "Super+Ctrl+Shift+D". No bare "Super+D" remains in shipped files outside `.flow/`.

## Boundaries

<!-- scope: business -->

- The lock, its dialogs, and Super+Ctrl+Shift+F are unchanged.
- Site block, app banner, block page, and window rules are unchanged apart from the key name in their text.
- No migration of the user's `~/.config/hypr/bindings.lua`; the conductor updates the live machine after merge.
- `.flow/` specs and tasks may keep historical "Super+D" text.

## Decision Context

<!-- scope: both -->

The user chose the combo as the friction (2026-09-02). Rejected: keeping `entry_confirm` as an off-by-default option. It would leave a dialog path to maintain that nobody asked for, and the saved config on the user's machine already pins it to true, so a default flip alone would not have changed behavior.
