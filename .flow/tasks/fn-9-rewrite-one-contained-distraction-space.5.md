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
`ds/lock.py` implements the `ds.lock` contract: `is_locked()` with lazy `until` expiry, `lock()` / `unlock()` writing `lock.json` under a runtime flock so transitions are serialized and each hook fires once, `unlock` enforcing `reason_min_chars` and appending the audit line before clearing the lock (an unwritable log keeps the lock and returns 1), `expire_if_due()` true once per transition, `run_hook()` detached with the `DS_*` env, `enter()` with the lock check, optional confirm through `ui.confirm_enter`, the non-blocking confirm flock, lock re-check after the dialog and fail-open on `ui.Unavailable`, plus `leave`, `toggle`, and the real `lock`/`unlock`/`enter`/`leave`/`toggle` commands (the foundation's stub test was updated). Config is read through the validated loader with a defaults fallback. Implemented by cursor-agent (cursor-grok-4.6-high) in an isolated worktree; the conductor committed and integrated.

stage: impl-review - ran [round 1 NEEDS_WORK (3 findings fixed in 556dba8), round 2 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)

Record repair 2026-09-02: status replayed from this task's own Done summary and evidence after PR #9 merged; the fn-9 run's flow-state never reached main.
## Evidence
- Commits: 39fef48d31fd109b83451e02b8dd59f1f5ffe054, d9cd03929227f8c9c12f6f23ebedff913a25d66a, 556dba8a3dc218d7bf54c5688914b1efe1b6cef6
- Tests: python3 -m unittest discover tests, python3 -m unittest tests.test_lock tests.test_enter tests.test_status tests.test_config tests.test_hypr
- PRs: 9