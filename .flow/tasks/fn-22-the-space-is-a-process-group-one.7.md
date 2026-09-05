---
satisfies: [R12, R13]
---
# fn-22-the-space-is-a-process-group-one.7 Mute keys on slice membership first; locking on the space leaves it

## Description
Two small behavior changes on the hold and lock paths (R12, R13), combined because both are S-sized and disjoint from every other task.

**Size:** S
**Files:** `ds/hold.py`, `ds/lock.py`, `tests/test_audio.py`, `tests/test_lock.py`
**Touches:** [ds/hold.py, ds/lock.py, tests/test_audio.py, tests/test_lock.py]

### Approach
- `ds/hold.py` `attribute_stream(item, table, proc)`: before the `_is_browser` guard, read `application.process.id` and call `cgroup.in_slice(pid, proc)`; a member is muted regardless of class (the person's decision on 2026-09-05). `OSError` or a missing pid falls through to the existing catalog matching unchanged. `muted.json` identity and `release()` safety rules untouched (memory `bug/runtime-errors/mute-release-forgot-streams-whose-2026-09-02`: forward `now=` through the seams you touch).
- `ds/lock.py` `lock()`: when `hypr.on_space()` is True, run the same cycle `leave()` uses before writing the lock; when no other workspace is occupied, stay, as `leave` does today.

### Investigation targets
**Required** (read before coding):
- `ds/hold.py:452-504` — `_cmdline_host`, `pwa_name`, `attribute_stream`
- `ds/hold.py:507-663` — `Mute`, `muted.json`, `release`
- `ds/lock.py:154-192` — `enter`, `leave`, `lock` and their `cmd_*`
- `ds/cgroup.py` — helper from task 1

**Optional:**
- `tests/test_audio.py` — `pactl` JSON fixtures

## Acceptance
- [ ] A sink input whose pid's cgroup is in the slice is muted while the hold is in effect, even with a bare browser class; released on the space
- [ ] A sink input outside the slice follows the v2 catalog rules exactly (existing tests unchanged)
- [ ] An unreadable cgroup file falls through to catalog matching
- [ ] `distractions lock` while on the space lands on the previous workspace; with no other workspace occupied it stays
- [ ] Parked unknown on PipeWire `application.process.id` checked on this machine with the distraction browser playing sound; result recorded in the done summary
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes


## Done summary
Sound mute now keys on slice membership first: `attribute_stream` reads `application.process.id` and asks `cgroup.in_slice` before the bare-browser guard, so a stream from any process in `app-distraction.slice` is muted while the hold is in effect regardless of window class, and an unreadable or missing cgroup file falls through to the v2 catalog rules (R12). `lock()` runs the `leave` cycle when the person is on the space and stays when no other workspace is occupied; the lock is written either way (R13). `muted.json` identity and the release safety rules are untouched.

### What changed (commit ce6f89b, base 6455a98)
- `ds/hold.py`: slice check ahead of `_is_browser`; OSError and missing pid fall through.
- `ds/lock.py`: `lock()` leaves the space first when on it.
- Tests: `test_attribute_stream_slice_member_first_then_catalog`, `test_scan_mutes_a_bare_browser_stream_in_the_slice_and_release_unmutes_it`, `test_lock_on_the_space_leaves_it_and_locks`, `test_lock_on_the_space_stays_when_no_other_workspace_is_occupied`, `test_lock_off_the_space_switches_nothing`. `LockTests.setUp` installs the `test_enter` fake `hyprctl` so no lock test reaches the real compositor.

### Review
cursor / gpt-5.6-sol-high, one round, SHIP; R12 and R13 met.

### Left open, recorded here on purpose
- The live PipeWire check (distraction browser playing sound; `pactl -f json list sink-inputs` shows `application.process.id`, and `cgroup.in_slice(pid)` is true) needs a desktop session and has been handed to the person; its result goes into the spec's Parked unknowns.

### Gates
- baseline: green via handoff (6a1f7011)
- verify: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at ce6f89b, 314 tests, suite_rc=0; receipt `.flow/tmp/green-receipts/ce6f89b5-unittest.json`
- classify: FULL

stage: impl-review - ran (cursor gpt-5.6-sol-high, 1 round, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: ce6f89b5c84d8f039274494bdb0354a1afb57f0b
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 314 tests at ce6f89b; receipt .flow/tmp/green-receipts/ce6f89b5-unittest.json)
- PRs: