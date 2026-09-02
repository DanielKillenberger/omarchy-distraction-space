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
`ds/ui.py` implements the `ds.ui` contract over `omarchy-menu-select` / `omarchy-menu-input` / `omarchy-notification-send`: `select`, `input` (None on cancel or timeout, `Unavailable` on a missing binary), `notify` that never raises, `confirm_enter`, `prompt_lock` (durations then purpose when `ask_purpose`), `prompt_reason`, and `menu()` with Lock/Unlock (no prompt when `reason_min_chars` is 0), Open/Leave the space, Edit list (catalog and custom rows toggling through `config.update` with the new value computed under the lock, Add a site or app), and Settings exactly per the spec's key list, with invalid config at any menu boundary becoming one notice and exit 1. The `menu` command is real. `BarWidget.qml` watches `state.json` with FileView (no polling), shows the eye glyph with urgent color while locked and the deadline and purpose tooltip, and maps left, right, and middle clicks to lock/unlock, menu, and toggle. Implemented by cursor-agent (cursor-grok-4.6-high) in an isolated worktree; the conductor committed and integrated.

stage: impl-review - ran [round 1 NEEDS_WORK (3 findings fixed in 2677e46), round 2 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)

Record repair 2026-09-02: status replayed from this task's own Done summary and evidence after PR #9 merged; the fn-9 run's flow-state never reached main.
## Evidence
- Commits: fe6424b95148ce316e2ab285775c407ad0e9cc85, bc7a3c259ffad05547f6a0431ca800d7cf248beb, 2677e466f851d3a51ad3c71c98ad97c6db3e3bd8
- Tests: python3 -m unittest discover tests
- PRs: 9