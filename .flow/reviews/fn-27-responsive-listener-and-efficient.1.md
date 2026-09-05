All reads are complete; nothing else is needed. Writing the re-review now.

## Re-review: fn-27-responsive-listener-and-efficient.1 (cc6a601 → 0251539)

### Scope note

This range is wider than the prior pass (…→b82c598). Besides the task's files it carries `ds/hypr.py:620-628` (skip the migration offer when identity is unreadable), `ds/state.py:246-285` (`site_block: off` health shaped by the saved expansion), matching tests, and README/docs text for fn-25/fn-26. Those are outside this task's `Files` list and look like parallel-task content brought into the integration branch. I read them; none introduces a defect, and neither touches listener scheduling or state production.

### Prior findings

1. **Launcher-refresh toast every cycle; lock contention counted as failure — fixed.** `ds/setup.py:1196,1213-1216` returns `ENTRIES_DEFERRED` to strict callers on lock contention; `ds/listener.py:374-377` maps it to `deferred`, `:418-423` latches "Launcher refresh failed" once per failure streak and resets on `ok`, `:425-427`/`:444` reply `deferred` to waiters, and `_ask` (`:62-65`) turns that into a "Refresh deferred" notice rather than "failed". `test_entries_lock_defers_without_failure_and_recovers` and `test_launcher_failure_notice_once_per_failure_streak` cover both halves. `config.py:380` ignores `request_reload`'s result, so the new reply word breaks no other consumer.
   Residual, nonblocking: `ds/setup.py:997-1000` adds `apps` to `_cache_pending` before `shutil.which`, so on a machine without `update-desktop-database` the listener's strict refresh returns 1 forever once it has written an entry, and every `reload`/`refresh` answers `error` though config and firewall applied. The toast is now latched, and the tool ships with `desktop-file-utils` on Omarchy, so this is a docstring/behaviour mismatch ("best effort") rather than a regression on a real target.
2. **Failed `ensure_slice` skipped the wrapper silently — fixed.** `ds/listener.py:97-99` now calls `net._notice_unavailable()` on that path. Cosmetic: the notice text still names the wrapper/sudo, not the slice.
3. **Reply gated on `links_ok` — not fixed, nonblocking.** `ds/listener.py:425` unchanged; still a deliberate-looking semantic choice.
4. **Forced hold push every period on the loop — not fixed, nonblocking.** `ds/listener.py:473`; bounded IPC, hold ownership is loop-side by design.
5. **`launcher_refresh` read `ok` after `start` — fixed.** Worker skips entries when `reason == "start"` (`:374`), state carries `off`; `test_startup_does_not_claim_entry_refresh`.
6. **Weak hold assertion — fixed.** `_assert_reconciliation_stall` now asserts `hold` is `True` before the stall and `False` after the workspace event while the child is still gated.
7. **killpg after normal exit / 255 s CLI wait — note only, unchanged.**

### Re-verified on the current head

- Single serialized worker: `request()` (`ds/listener.py:331-343`) coalesces while busy for both periodic and explicit requests; `_launch` is reached only from `request()` when idle or from `_follow` after `busy` is cleared, so `self.worker` and `self.pending` are never contended by two workers.
- Ordering: `current()` checked before resolve→apply and again inside `_apply` (`:100`); stale generations never touch `net.site_block` or waiters (`:405-407`); waiters are re-adopted to the newest generation (`:436-442`). The listener is the only writer of `net.site_block` (`net.apply` survives only in `tests/test_net.py`).
- Deadlines/cleanup: `run_command` (`ds/net.py:31-82`) bounds every child, checks cancel every 0.1 s, kills the group and reaps; all callers catch `(OSError, TimeoutExpired)` (`cgroup.py:90`, `setup.py:729`, `setup.py:1008`, `launch.py:405`, `net.py:333`). Shutdown sets `stopping`, runs `net.shutdown()`, joins the worker ≤3 s (`:181-184`).
- Contract: `observed_at` holds exactly the three keys, each stamped after its own check; `ping` answers without work (`:691-692`); top-level fields unchanged, `launcher_refresh` added and documented in `docs/internals.md`.
- Periodic reconciliation still runs every period (`:471-474`), per acceptance.

### New observations (nonblocking)

- With the block disabled and already flushed, a non-reload generation records `site_block: off` and stamps `observed_at.site_block` (`:365-368`) without invoking the wrapper. The health projection reports `disabled` in that case regardless of the timestamp, so no user-visible effect, but it is a timestamp without an observation. R3/R4-style verification belongs to `.2`/`.3`.
- `ENTRIES_LOCK_TIMEOUT` (90 s) comment still assumes the listener's sync costs at most one `UDD_TIMEOUT`; that remains true.

No introduced blocking defect remains.

<verdict>SHIP</verdict>