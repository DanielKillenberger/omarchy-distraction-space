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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
