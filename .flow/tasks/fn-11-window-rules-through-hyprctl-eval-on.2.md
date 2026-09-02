---
satisfies: [R1, R2, R3, R4]
---
# fn-11-window-rules-through-hyprctl-eval-on.2 Port the eval rule primitive and configreloaded re-apply into the fn-9 ds package

## Description
TBD

## Acceptance
R1-R4 of the parent spec hold in ds/hypr.py and ds/listener.py after the fn-9 rewrite landed on main: rules via hyprctl eval, no keyword path, handle-based disable, configreloaded re-apply and rescan. tests/test_hypr.py and tests/test_listener.py doubles refuse keyword.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
