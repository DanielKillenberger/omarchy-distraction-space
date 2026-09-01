---
satisfies: [R1, R3]
---
# fn-9-rewrite-one-contained-distraction-space.2 Window containment: named rules, silent moves, intercept banner

## Description
Implement `ds/hypr.py`: hyprctl/json wrappers, `on_space`, workspace cycle skipping the space, `apply_rules(expanded)` setting `windowrule[omarchy-ds-<slug>]` per classed entry and disabling names in `rules.json` that are no longer desired, `handle_event(line)` for socket2 `openwindow`/`movewindow` that silently moves listed clients and calls the banner (one per app per 30 s, click action `distractions enter`) when off-space and `nudges.app_banner`. Tests use a fake `hyprctl` and fake `omarchy-notification-send` on PATH.

**Files:** `ds/hypr.py`, `tests/test_hypr.py`.

## Acceptance
- Listed classed windows are moved to the space on open and on move; unlisted windows are untouched.
- Removed entries have their rules disabled; `rules.json` matches the desired set after apply.
- Banner debounce is 30 s per app and never fires on the space.
- A failing hyprctl call is logged and skipped.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
