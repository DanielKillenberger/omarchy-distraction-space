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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
