# Window rules through hyprctl eval on the Lua config

## Conversation Evidence

> user (turn 1): "so i thought that distracting apps would only open to distraction space? atm it's opening telegram on my workspace 1"
> user (turn 2): "/flow-next:work this in a new small planless spec"

## Overview

Listed apps are meant to be born on the distraction space through a named Hyprland window rule per app. Those rules are never installed on Omarchy 4: the listener writes them with `hyprctl keyword`, and Hyprland with the Lua config parser answers `keyword can't work with non-legacy parsers. Use eval.` on stdout with exit code 0. `check_output` sees success, the last-good registry is written, and no rule exists. The only placement left is the socket2 `openwindow` safety net, so Telegram appears on the current workspace and is then moved. The user sees it open on workspace 1.

Verified live on 2026-09-02 (Hyprland 0.56.2, `~/.config/hypr/hyprland.lua`): `hyprctl keyword "windowrule[x]:match:class y"` exits 0 with the refusal text; `hyprctl eval 'hl.window_rule({ name = "x", match = { class = "y" }, workspace = "name:distraction silent" })'` returns `ok`; the returned handle supports `set_enabled(false)`; a Lua error exits 7 with `error: ...`.

## Goal & Context

<!-- scope: business -->

Listed apps with a window class open directly on the distraction space, with no flash on the current workspace, on Omarchy 4's Lua Hyprland config. Rule install failures are detected instead of recorded as success. Rules survive a Hyprland config reload.

## Architecture & Data Models

<!-- scope: technical -->

`set_named_rule` and `disable_named_rule` in `distractions` drive Hyprland through one `hyprctl eval` each instead of three `hyprctl keyword` calls. The Lua fragment keeps rule handles in a global table (for example `_G.omarchy_ds_rules[name]`): on set, disable any existing handle under that name inside `pcall`, create the rule with `hl.window_rule({ name = name, match = { class = pattern }, workspace = "name:distraction silent" })`, and store the handle; on disable, look the handle up and `set_enabled(false)` inside `pcall`, no-op when absent. Class patterns and names are embedded as Lua string literals with correct escaping (backslashes, quotes, brackets); Hyprland matches `class` as a regex, which is what the current keyword path relied on.

The registry (`omarchy-ds-rules.last-good.json`, pending file), `desired_rule_map`, `apply_named_rules`, rollback, and `leftover_order` keep their shape. Only the two Hyprland-facing primitives change.

`process_socket2_line` handles the `configreloaded` event by re-applying the active rule set through the existing apply path (same lock discipline as a reload request), because a config reload drops dynamically added rules. Existing off-space clients are re-scanned after that re-apply.

The test double for `hyprctl` in `tests/test_enforcement.py` records `eval` fragments and exits nonzero on `keyword`, so a regression to the keyword path fails the suite. Tests that previously read `keywords.log` assert on the eval log instead: rule name, class pattern, workspace effect, enable/disable, and the `configreloaded` re-apply.

## Edge Cases & Constraints

<!-- scope: technical -->

- `hyprctl eval` nonzero exit or a Lua error: `set_named_rule` raises, `apply_named_rules` rolls back and notifies as today, last-good is not overwritten.
- A disable for a name whose handle is missing (fresh Lua state after reload, or never created): no error, no-op.
- Same name applied twice in one listener lifetime (list edit, reload): the old handle is disabled before the new rule is created, so no duplicate live rule matches.
- Class pattern containing `\`, `"`, `'`, or `]]`: still a valid Lua literal.
- `configreloaded` arriving while a list reload is in flight: serialized with the reload lock; the later apply wins.
- Legacy `hyprland.conf` parser: `hyprctl eval` refuses. That is reported through the existing rollback notify, and the socket2 move remains the fallback. Omarchy 4 ships the Lua config, so no keyword fallback is kept.
- The socket2 `openwindow`/`movewindow` move stays as the safety net and is unchanged.

## Quick commands

```bash
python3 -m unittest discover -s tests
```

## Acceptance Criteria

<!-- scope: both -->

- **R1:** Named window rules are installed through `hyprctl eval` with `hl.window_rule`, one rule per expanded entry with a class, named `omarchy-ds-<slug>`, matching the entry's class pattern, workspace effect `name:distraction silent`. Errors: a nonzero exit from `hyprctl eval` raises inside `set_named_rule`; `apply_named_rules` rolls back, notifies, and does not write last-good.
- **R2:** `hyprctl keyword` is not used for window rules anywhere in `distractions`. The test hyprctl double exits nonzero on `keyword`, and the suite passes.
- **R3:** Disabling a rule name uses the stored Lua handle's `set_enabled(false)`; re-applying an existing name disables the previous handle before creating the new rule. Errors: a missing handle is a no-op, never an exception that aborts the apply batch.
- **R4:** On the socket2 `configreloaded` event the listener re-applies the active rule set and re-scans existing clients, under the same lock as a list reload. Errors: an apply failure during that re-apply goes through the same rollback and notify path as R1 and leaves the listener running.

## Boundaries

<!-- scope: business -->

- No change to list membership, expansion, the banner, the network block, or focus mode.
- No change to the registry file format or the pending/last-good rollback design.
- fn-9's rewrite spec text is not edited here; its window containment section should adopt the eval primitive when it is implemented.
- README wording about placement stays; the install steps are unchanged.
- No keyword fallback for the legacy config parser.

## Decision Context

<!-- scope: both -->

Fix inside the current tree rather than waiting for fn-9: the user hits this today, and the eval primitive carries over to the rewrite unchanged.

Rejected: keeping `hyprctl keyword` and parsing its stdout for the refusal text. It still cannot install rules on the Lua parser.
Rejected: writing the rules into `~/.config/hypr/hyprland.lua` and running `hyprctl reload`. The plugin does not own that file, and a reload is disruptive on every list edit.
Rejected: relying on same-name redefinition to replace a rule. Whether Hyprland replaces or duplicates by name is unverified, so the handle table makes disable explicit.
