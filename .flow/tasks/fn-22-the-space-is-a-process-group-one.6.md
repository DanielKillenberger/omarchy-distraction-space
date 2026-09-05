---
satisfies: [R5, R6, R10]
---
# fn-22-the-space-is-a-process-group-one.6 Windows: profile rule, pid/ancestor safety net, adoption, Opened banner wiring

## Description
The three containment layers (R5, R6) and the Opened half of R10. Depends on `open` for adoption and on the feedback API for the banner.

**Size:** M
**Files:** `ds/hypr.py`, `ds/listener.py`, `tests/test_hypr.py`, `tests/test_listener.py`
**Touches:** [ds/hypr.py, ds/listener.py, tests/test_hypr.py, tests/test_listener.py]

### Approach
- `ds/hypr.py` `apply_rules`: one named rule `omarchy_ds_profile` matching class `^[a-z-]+-.+__-Distraction$` → `workspace = "name:distraction silent"`, plus the existing per-native-class rules; drop the per-host web rules (`pwa_class`). Re-apply on `configreloaded` as today.
- `_match_entry`: return a match for the distraction profile class and native classes only. Add `_foreign_webapp(klass) -> entry | None` matching `^[a-z-]+-(<host>)__-(?!Distraction)` for every listed `pwa`/hosts host.
- `_handle_event` on `openwindow` and (subject to task 8's policy) `movewindow`: read the client via `_client_by_address` including `pid`. Layer 1: `_match_entry` → `move_to_space`. Layer 2: `cgroup.ancestor_in_slice(pid)` → `move_to_space`; unreadable cgroup → skip to layer 3. Layer 3: `_foreign_webapp` → close the window (`hl.dsp.window.close({window="address:..."})` via `hyprctl eval`), remember the address in a bounded set, and run `<plugin>/distractions open <name>` detached; if `open` fails, move the window by class and log one line.
- After any move by layers 1 to 3 or a successful adoption, when `on_space()` is False call `feedback.opened(name)`; replace the old `_maybe_banner` call.
- `_scan` on start and reload runs the same three layers over `hyprctl clients -j`.

### Investigation targets
**Required** (read before coding):
- `ds/hypr.py:161-264` — rule Lua, `apply_rules`, `move_window_lua`
- `ds/hypr.py:447-491` — `_handle_event`, `_match_entry` use
- `ds/listener.py:350-358,466-491` — `event`, `_scan`
- `ds/cgroup.py` — helper from task 1
- `ds/feedback.py` — `opened()` from task 5

**Optional:**
- `ds/catalog.py:34-35` — `pwa_class`, to retire
- `tests/test_hypr.py` — fake `hyprctl` fixtures

### Key context
- Hyprland here uses the Lua config provider; rules go through `hyprctl eval` with `hl.window_rule`, never `hyprctl keyword`.
- Adoption closes a host-bearing web-app window only; a plain browser window is never closed.

## Acceptance
- [ ] `apply_rules` emits one profile rule and one rule per native class, and no per-host web rule; re-applied on `configreloaded`
- [ ] A window with class `chrome-web.whatsapp.com__-Distraction` off the space is moved silently; the focused workspace does not change
- [ ] A popup with a plain `chrome` class whose ancestor is in the slice is moved; with an unreadable cgroup file it falls back to class matching
- [ ] A `chrome-web.whatsapp.com__-Default` window is closed once and `distractions open WhatsApp` is launched once for that address; a failing `open` leaves it moved by class with one log line
- [ ] Opened banner raised once per entry per 60 s when the person is elsewhere, never on the space
- [ ] `_scan` on start applies the same layers to existing clients
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes


## Done summary
The three containment layers land in `ds/hypr.py` as one decision function, `classify(klass, pid)`, and one actor, `contain(client)`, which `_handle_event` and `listener._scan` both call (R5, R6). The window banner is gone; every landing goes through `feedback.opened(name)` (the Opened half of R10).

### What changed (commits 3edb4b8, ca147e0, b8887b7; base 4f66e04)
- `apply_rules`: one named rule `omarchy_ds_profile` matching `^[a-z-]+-.+__-Distraction$` plus one rule per native class; no per-host web rule, old per-host names disabled on the first apply; re-apply on `configreloaded` unchanged.
- `classify`: layer 1 the profile class or a native class; layer 2 `cgroup.ancestor_in_slice(pid)` with an unreadable cgroup counting as outside; layer 3 a listed product's web-app class from any profile other than Distraction.
- `contain`: moves silently; `move_to_space` reports whether Hyprland took the dispatch; a window has landed only when the rule already placed it on the space (fresh window) or the move succeeded; a scan or move event of a window already there announces nothing. Adoption remembers the address first, runs `distractions open <name>` synchronously with a 30 s cap so the exit code decides, closes the window on success, records a refused close as close-pending and retries only the close on the window's next event, and on a failed open moves the window by class with one log line and reports that move.
- Banner: `feedback.opened(name)` after a confirmed landing. Removed from hypr: `BANNER_S`, `_app_banner`, `_banner_at`, `_want_banner`, `_maybe_banner`.
- `ds/listener.py`: `_scan()` calls `hypr.contain` per client; `enforce` starts `feedback` before the scan.
- Imports: `hypr` reaches `launch` and `feedback` through call-time imports because both import `hypr`.
- Tests: `tests/test_hypr.py` one per acceptance line plus refused-close retry, failed move on a scan, rule-placed fresh window, failed open with a refused fallback move; `tests/test_listener.py` `ScanTests`.

### Deviations, recorded on purpose
- Adoption waits on `open` with a timeout instead of detaching it: R6's failed-open fallback needs the exit code, and `open` detaches the launch itself.
- `catalog.pwa_class` and `feedback._maybe_banner` stay; both sit outside this task's Touches and the expansion still carries the pwa pattern for `hold.py`, `launch.entry_hosts`, and `feedback._entry_host`. Task .9 may retire the shim.

### Review
cursor / gpt-5.6-sol-high, three rounds: round 1 NEEDS_WORK (refused close left the adoption done; failed move still announced), round 2 NEEDS_WORK (fresh window announced despite a refused move; fallback move result ignored), round 3 SHIP with R5, R6, R10 met.

### Gates
- baseline: green via handoff (100b1e5f)
- verify: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at b8887b7 on the integrated target, 342 tests, OK; receipt `.flow/tmp/green-receipts/b8887b7d-unittest.json`
- classify: FULL

stage: impl-review - ran (cursor gpt-5.6-sol-high, 3 rounds, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 3edb4b8, ca147e0, b8887b7
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 342 tests at b8887b7 on the integrated target; receipt .flow/tmp/green-receipts/b8887b7d-unittest.json), PATH=/usr/bin:$PATH python3 -m unittest tests.test_hypr tests.test_listener
- PRs: