---
satisfies: [R8, R12]
---
# fn-9-rewrite-one-contained-distraction-space.6 Menus, prompts, and the bar widget

## Description
Implement `ds/ui.py`: `select(prompt, rows)` / `input(prompt)` wrappers over `omarchy-menu-select` / `omarchy-menu-input` (glyph\tlabel\tsubtext rows, cancel handling, timeout support), `notify(...)` over `omarchy-notification-send`, `confirm_enter()`, `prompt_lock()` (durations: default_minutes, 50, 90, Until I unlock, Other…; then purpose when `ask_purpose`), `prompt_reason(min_chars)`, and `menu()` with Lock…/Unlock…, Open/Leave the space, Edit list (checked/unchecked rows per catalog product and custom entry, Add a site or app…, Back; every toggle saves through `config` and calls `reload`), Settings (one row per key, booleans flip, enums cycle, integers prompt, Back). Rewrite `BarWidget.qml` to watch `state.json` (FileView, no polling): eye glyph, urgent color while locked, tooltip with deadline and purpose, left click lock/unlock, right click menu, middle click toggle.

**Files:** `ds/ui.py`, `BarWidget.qml`, `tests/test_ui.py`.

## Acceptance
- Every menu action writes only through `config` functions and triggers `reload`.
- Edit list toggles a catalog product on and off and adds a custom hostname or `class=` entry.
- Settings changes each schema key type correctly and refuses invalid input.
- Bar widget renders locked/unlocked from a `state.json` fixture and shows the idle state when the file is missing.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
