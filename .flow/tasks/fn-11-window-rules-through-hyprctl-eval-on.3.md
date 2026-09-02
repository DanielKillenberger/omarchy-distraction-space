# fn-11-window-rules-through-hyprctl-eval-on.3 Hotfix: dispatch through hl.dsp Lua dispatchers (workspace focus and silent window move)

## Description
TBD

## Acceptance
hyprctl dispatch on the Lua parser evaluates its argument as Lua. move_to_space, cycle, and lock._go_to_space send hl.dsp.window.move({ window = "address:<a>", workspace = "name:distraction", follow = false }) and hl.dsp.focus({ workspace = "name:<n>" }); no legacy dispatcher strings remain; tests assert the Lua forms.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
