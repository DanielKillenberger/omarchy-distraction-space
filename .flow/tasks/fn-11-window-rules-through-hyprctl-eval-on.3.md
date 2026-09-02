# fn-11-window-rules-through-hyprctl-eval-on.3 Hotfix: dispatch through hl.dsp Lua dispatchers (workspace focus and silent window move)

## Description
TBD

## Acceptance
hyprctl dispatch on the Lua parser evaluates its argument as Lua. move_to_space, cycle, and lock._go_to_space send hl.dsp.window.move({ window = "address:<a>", workspace = "name:distraction", follow = false }) and hl.dsp.focus({ workspace = "name:<n>" }); no legacy dispatcher strings remain; tests assert the Lua forms.

## Done summary
Dispatch calls use Lua dispatchers: `hl.dsp.focus({ workspace = "name:<n>" })` for enter and cycle, `hl.dsp.window.move({ window = "address:<a>", workspace = "name:distraction", follow = false })` for the silent move. Verified live on Hyprland 0.56.2: a window moved to an empty workspace and back while the active workspace stayed put. Tests assert the Lua forms; `test_tree` skips nested `.worktrees`.

stage: impl-review - skipped(policy: hotfix restoring blocked Super+D entry while the user waited; suite green at 179)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: b8f52db
- Tests: python3 -m unittest discover -s tests
- PRs: