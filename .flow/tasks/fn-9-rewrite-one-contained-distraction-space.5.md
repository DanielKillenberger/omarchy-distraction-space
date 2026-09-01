---
satisfies: [R4, R5, R6, R7, R13]
---
# fn-9-rewrite-one-contained-distraction-space.5 Lock, log, hooks, and the entry confirm

## Description
Implement `ds/lock.py`: `is_locked()` with lazy `until` expiry, `lock(minutes|None, purpose)`, `unlock(reason)` enforcing `reason_min_chars` and appending to `log`, `expire_if_due()` for the listener tick, `run_hook(name, env)` detached with `DS_*` env. Implement `enter()`: lock check, optional confirm through `ui.confirm` with 30 s timeout treated as Stay, flock on `distraction-space.confirm`, lock re-check after the dialog, fail-open when menu tooling is missing. Implement `toggle`, `leave`, `next`, `prev` on top of `hypr`. `lock`/`unlock` with no args call `ui` prompts (duration menu, purpose input, reason input) defined by task 6; this task ships them against a stub `ui` interface and the fake `omarchy-menu-select`/`omarchy-menu-input` binaries.

**Files:** `ds/lock.py`, `tests/test_lock.py`, `tests/test_enter.py`.

## Acceptance
- A lock with `until` in the past reads as unlocked everywhere; the listener tick fires the unlock hook once.
- Short reason refuses and keeps the lock; `reason_min_chars` 0 needs no prompt.
- Confirm: Enter switches; Stay, Escape, timeout stay; second Super+D during a dialog is a no-op; lock flipped mid-dialog shows the lock notice; missing menu tool enters with one notice.
- Hooks run detached with the documented env and never affect the action.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
