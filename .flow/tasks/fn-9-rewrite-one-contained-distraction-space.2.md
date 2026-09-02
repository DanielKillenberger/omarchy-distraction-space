---
satisfies: [R1, R3]
---
# fn-9-rewrite-one-contained-distraction-space.2 Window containment: named rules, silent moves, intercept banner

## Description
Implement `ds/hypr.py`: hyprctl/json wrappers, `on_space`, workspace cycle skipping the space, `apply_rules(expanded)` setting `windowrule[omarchy-ds-<slug>-<n>]` per class in each entry's `classes` and disabling names in `rules.json` that are no longer desired, `handle_event(line)` for socket2 `openwindow`/`movewindow` that silently moves clients matching any listed class and calls the banner (one per app per 30 s, click action `distractions enter`) when off-space and `nudges.app_banner`. Tests use a fake `hyprctl` and fake `omarchy-notification-send` on PATH via `tests/harness.py`; fixtures specific to this task live in `tests/test_hypr.py` only.

**Files:** `ds/hypr.py`, `tests/test_hypr.py`.

**Touches:** [ds/hypr.py, tests/test_hypr.py]
## Acceptance
- Listed classed windows, native and automatic PWA class alike, are moved to the space on open and on move; unlisted windows are untouched.
- An entry with two classes yields two named rules; removed entries have their rules disabled; `rules.json` matches the desired set after apply.
- Banner debounce is 30 s per app and never fires on the space.
- A failing hyprctl call is logged and skipped.
## Done summary
`ds/hypr.py` implements window containment: hyprctl JSON wrappers, `on_space()` (None on failure, logged), `apply_rules(expanded)` setting one named rule per class (`omarchy-ds-<slug>-<hash>-<n>`, collision-free) and disabling stale names from `rules.json` with failed disables retained for retry, `handle_event(line)` moving listed clients to the space on `openwindow`/`movewindow` and sending one banner per app per 30 s only when the person is known to be off the space and `nudges.app_banner` is on, `cycle()` skipping the space, and real `next`/`prev` commands (the foundation's stub test was updated accordingly). Implemented by cursor-agent (cursor-grok-4.6-high) in an isolated worktree; the conductor committed and integrated.

stage: impl-review - ran [round 1 NEEDS_WORK (3 findings fixed in 1a8d92a), round 2 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 95f937641ae4e50dfea1569fd42b4bceaf4744d8, 1a8d92aeccfda2c6e2e30d8feba6f5997e71e025
- Tests: python3 -m unittest discover tests
- PRs: