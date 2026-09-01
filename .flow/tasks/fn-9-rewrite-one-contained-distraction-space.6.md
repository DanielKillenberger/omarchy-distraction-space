---
satisfies: [R8, R12]
---
# fn-9-rewrite-one-contained-distraction-space.6 Menus, prompts, and the bar widget

## Description
Implement `ds/ui.py` to the spec's `ds.ui` contract, replacing the wave 1 stubs: `select(prompt, rows, timeout=None)` / `input(prompt, timeout=None)` over `omarchy-menu-select` / `omarchy-menu-input` (glyph\tlabel\tsubtext rows, `None` on cancel or timeout, `ui.Unavailable` when the binary is missing or fails to launch), `notify(...)` over `omarchy-notification-send` that never raises, `confirm_enter(timeout=30)` returning `enter`/`stay`/`unavailable`, `prompt_lock(cfg)` (durations: default_minutes, 50, 90, Until I unlock, Other…; then purpose when `ask_purpose`; `None` on duration cancel, empty purpose on purpose cancel), `prompt_reason(min_chars)`, and `menu()` with Lock…/Unlock…, Open/Leave the space, Edit list (checked/unchecked rows per catalog product and custom entry, Add a site or app…, Back; every toggle saves through `config.update` and calls `reload`), Settings exactly per the spec's Settings list: booleans flip, `hold_notifications` and `summary.command` cycle (argv shows "custom" and cycles to auto), integers prompt and refuse non-integers or negatives with a notice, `list` opens Edit list, `keep_reachable`/`hooks.*`/`log` are read-only rows whose select shows a notice naming the `distractions config set` form. Rewrite `BarWidget.qml` to watch `state.json` (FileView, no polling): eye glyph, urgent color while locked, tooltip with deadline and purpose, left click lock/unlock, right click menu, middle click toggle. Fixtures live in `tests/test_ui.py` only.

**Files:** `ds/ui.py`, `BarWidget.qml`, `tests/test_ui.py`.

**Touches:** [ds/ui.py, BarWidget.qml, tests/test_ui.py]
## Acceptance
- Every menu action writes only through `config.update` and triggers `reload`.
- `confirm_enter`, `prompt_lock`, `prompt_reason` return exactly the contracted values for choose, cancel, timeout, and missing binary.
- Edit list toggles a catalog product on and off and adds a custom hostname or `class=` entry.
- Settings flips each boolean, cycles each enum, prompts each integer and refuses invalid input, opens Edit list for `list`, and shows a notice for the read-only keys.
- Bar widget renders locked/unlocked from a `state.json` fixture and shows the idle state when the file is missing.
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
