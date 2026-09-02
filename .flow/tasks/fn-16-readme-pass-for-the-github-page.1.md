---
satisfies: [R1, R2, R3, R4, R5]
---
# fn-16-readme-pass-for-the-github-page.1 Implement README pass for the GitHub page

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
The README is now a landing page: 143 lines (from 276), opening with the tagline, `preview.png`, one second-person paragraph, and the three-step install with the Omarchy 4 / Hyprland / Python 3.11 line. Each "what it does" section names its mechanism (`hyprctl eval` with `hl.window_rule` plus the socket2 `openwindow` net, the `omarchy_ds_v4`/`v6` sets with the 28080 block page and the 28443 SNI read, the per-sender silenced list, the `muted.json` identity check), a Limits heading states the address-level collateral, the missing HTTPS block page, the unmutable Chrome web-app audio, the shell-patch dependency and the sudo grant, and 132 lines of maintainer detail moved to `docs/internals.md`. `preview.png` (22 KB) is a real capture of this machine's bar showing the eye glyph with one held notification plus the "While you were away" notice that `ds/summary.py` produced through `claude -p`. `manifest.json`'s description now matches the tagline.

Written by Claude Opus under the flow-next artifact prose contract: zero em dashes and zero arrow glyphs in both files, mechanisms and numbers instead of adjectives, active voice with a named actor.

Cursor (gpt-5.6-sol-high) round 1 returned NEEDS_WORK with four introduced findings, all fixed in c1868ae: the preview lacked the summary notice; "notifications and sounds wait" implied muted audio is replayed; both README and internals claimed the HTTP path raises the "Blocked on this workspace" banner when only `_tls_conn` calls `_maybe_banner`; and the printed test command fails under this machine's mise `python3` shim. Round 2 returned SHIP with every R-ID met.

Follow-ups not done here: the marketplace listing badge waits on fn-17, and the address-level blocking limit is stated as a limit rather than fixed (fn-18).

stage: impl-review - ran [round 1 NEEDS_WORK, round 2 SHIP] (cursor, gpt-5.6-sol-high)
## Evidence
- Commits: 6ee333d2466a912cf2755ce2ea1882d6b0a90596, c1868ae85bc6388843520a7dc07668fe3004d6f3
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (239 passed, 73.2s), grep -c -- "—" README.md docs/internals.md (0, 0), omarchy plugin validate . (rc 0)
- PRs: