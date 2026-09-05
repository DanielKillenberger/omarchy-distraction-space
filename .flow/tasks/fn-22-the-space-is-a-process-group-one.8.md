---
satisfies: [R17, R18]
---
# fn-22-the-space-is-a-process-group-one.8 Release verb and the containment.snap_back policy

## Description
The escape hatch for working with a chat app on a work workspace (R17) and the policy for manual moves (R18). Depends on the windows task because it hooks into the same three layers.

**Size:** M
**Files:** `ds/listener.py`, `ds/hypr.py`, `ds/lock.py`, `distractions`, `hypr/bindings.lua`, `tests/test_listener.py`, `tests/test_hypr.py`
**Touches:** [ds/listener.py, ds/hypr.py, ds/lock.py, distractions, hypr/bindings.lua, tests/test_listener.py, tests/test_hypr.py]

### Approach
- `distractions release [minutes]`: default `containment.release_minutes`; non-positive → exit 2; read the focused window with `hyprctl activewindow -j`; none → exit 1 with one notice; send `release <address> <until-iso>` over the listener socket (same protocol as `reload`); no listener → exit 1.
- `ds/listener.py`: `released: {address: until}` on the context, written into `state.json`; prune on `closewindow` events and on each tick when past `until`; when an exemption expires and `snap_back` is true, re-run the containment layers for that address once.
- `ds/hypr.py`: the three layers and `_scan` skip addresses in the exempt set; `movewindow`/`movewindowv2` handling is gated by `containment.snap_back` (true reverts moves off the space of an unreleased contained window; false ignores move events).
- `hypr/bindings.lua`: a commented suggested binding for `release`; README wiring lands in task 9.

### Investigation targets
**Required** (read before coding):
- `ds/listener.py:24-52` — socket protocol and reply
- `ds/hypr.py:447-491` — event handling after task 6
- `ds/lock.py:183-192` — `cmd_*` shape to mirror for `cmd_release`
- `hypr/bindings.lua` — binding style

**Optional:**
- `ds/state.py:193-211` — `status()` `released` field from task 2

## Acceptance
- [ ] `release` with a focused contained window records `{address: until}` in state; `status --json` shows it; a `movewindow` of that window off the space is not reverted and an `openwindow` re-scan leaves it
- [ ] The exemption is pruned on `closewindow` and after `until`; with `snap_back: true` an expired window is moved back once
- [ ] `snap_back: false` ignores `movewindow` events for unreleased windows; `true` reverts them (v2 behavior kept)
- [ ] `release 0` exits 2; no focused window or no listener exits 1 with one notice
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes


## Done summary
`distractions release [minutes]` exempts the focused window from all three containment layers until a deadline or until it closes (R17), and `containment.snap_back` decides whether a manual move of an unreleased contained window off the space is reverted on its `movewindow` event or left alone (R18).

### What changed (commits e932fa3, f5bc1d4; base 1f67be2)
- `ds/hypr.py`: the exempt set `_released` (`{address: until}`) beside `_adopted`; `contain` returns None for a released address before `classify`; `closewindow` forgets it; `expire_released()` drops past deadlines; `hypr.snap_back` gates `movewindow`/`movewindowv2`; `active_window()`; `contain_address()` re-runs the layers once an exemption ends.
- `ds/listener.py`: `cmd_release` (default `containment.release_minutes`) sends `release <address> <until>`; `_Ctx.release` refuses a past or unreadable deadline and, after review, an address `hyprctl clients` no longer lists; `expire_released` runs each tick and with `snap_back` on contains each expired window once; `enforce` sets `hypr.snap_back` from the config; `state.json` `released` reads `hypr.released()`.
- `distractions`: `release` subcommand; after review its `minutes` type is bounded by `config.RELEASE_MAX_MINUTES` (one week), which the config validator shares.
- `ds/lock.py`: `until_iso` public. `hypr/bindings.lua`: commented `SUPER + CTRL + SHIFT + E` binding.
- Tests: `tests/test_hypr.py` released window skips every layer, snap_back off ignores moves, closewindow forgets, expiry re-contains once; `tests/test_listener.py` CLI release against the running listener, status, prune, expiry snap-back exactly once, error replies including a window Hyprland no longer lists, parser bound; `tests/test_config.py` the bound.

### Deviation, recorded on purpose
- The exempt set lives in hypr as module state rather than on the listener context: `tests/test_status.py` pins `hypr.handle_event(line)`, so the set and the policy cannot travel as parameters. The listener owns record, expiry, and state, and reads the set back through `hypr.released()`.

### Review
cursor / gpt-5.6-sol-high, two rounds: round 1 NEEDS_WORK (unbounded duration overflowed the deadline; a closed window could keep an exemption nothing prunes), round 2 SHIP with R17 and R18 met.

### Gates
- baseline: green via handoff (b8887b7d)
- verify: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at f5bc1d4 on the integrated target, 345 tests, OK; receipt `.flow/tmp/green-receipts/f5bc1d46-unittest.json`
- classify: FULL

stage: impl-review - ran (cursor gpt-5.6-sol-high, 2 rounds, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: e932fa3, f5bc1d4
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 345 tests at f5bc1d4 on the integrated target; receipt .flow/tmp/green-receipts/f5bc1d46-unittest.json), PATH=/usr/bin:$PATH python3 -m unittest tests.test_hypr tests.test_listener tests.test_config
- PRs: