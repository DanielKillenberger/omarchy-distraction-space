---
satisfies: [R4, R5, R6, R7, R13]
---
# fn-9-rewrite-one-contained-distraction-space.5 Lock, log, hooks, and the entry confirm

## Description
Implement `ds/lock.py` to the spec's `ds.lock` contract: `is_locked()` with lazy `until` expiry, `lock(minutes, purpose)` and `unlock(reason)` which write `lock.json` and run the `lock`/`unlock` hooks (they are the hooks' owners), `unlock` enforcing `reason_min_chars` and appending to `log`, `expire_if_due()` returning true once per transition for the listener tick (the listener, not this module, runs the expiry hook), `run_hook(name, env)` detached with `DS_*` env. Implement `enter()`: lock check, optional confirm through `ui.confirm_enter(timeout=30)` treating `stay` as no-op and `unavailable` as fail-open with one notice, non-blocking flock on `distraction-space.confirm`, lock re-check after the dialog. `enter`, `leave`, `toggle` never run hooks; the listener owns `enter`/`leave` hooks. Implement `toggle`, `leave`, `next`, `prev` on top of `hypr`. `lock`/`unlock` with no args call `ui.prompt_lock(cfg)` / `ui.prompt_reason(min_chars)` exactly as contracted; on `ui.Unavailable` they report the missing prompt and require the argument form. Tests monkeypatch the wave 1 `ds.ui` stubs and use fake `hyprctl`; fixtures live in `tests/test_lock.py` and `tests/test_enter.py` only.

**Files:** `ds/lock.py`, `tests/test_lock.py`, `tests/test_enter.py`.

**Touches:** [ds/lock.py, tests/test_lock.py, tests/test_enter.py]
## Acceptance
- A lock with `until` in the past reads as unlocked everywhere; `expire_if_due()` returns true exactly once per transition.
- `lock` runs the `lock` hook once and `unlock` runs the `unlock` hook once; `enter`/`leave`/`toggle` run no hook.
- Short reason refuses and keeps the lock; `reason_min_chars` 0 needs no prompt.
- Confirm: `enter` switches; `stay` (Stay, Escape, timeout) stays; second Super+D during a dialog is a no-op; lock flipped mid-dialog shows the lock notice; `unavailable` enters with one notice.
- Hooks run detached with the documented env and never affect the action.
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
