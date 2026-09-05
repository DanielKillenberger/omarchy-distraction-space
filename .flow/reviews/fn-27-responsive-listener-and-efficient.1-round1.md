I have what I need: the full diff, the post-change `listener.py`/`net.py`/`cgroup.py`, the entries-lock and `_sync_files` paths in `setup.py`, `hold.push`/`Mute.sync` costs, the setup `install`/`remove` flow, and the new and neighbouring tests. No further reads are required.

## Review: fn-27-responsive-listener-and-efficient.1 (cc6a601 → b82c598)

### What the change does

`ds/listener.py:337-387` moves resolve, slice start, wrapper apply/flush, entry refresh, link observation and browser pick into one serialized `ds-reconcile` worker per generation; `request()` (`:324-336`) coalesces while busy, `take_result()` (`:388-414`) discards stale generations, publishes `site_block`/`observed_at`/`links`/`browser`/`launcher_refresh`, then replies to waiters, then reruns. `net.run_command` (`ds/net.py:31-82`) gives every child a new session, a deadline, a cancel event and killpg/reap cleanup; `systemctl_user`, `_xdg_settings`, `_update_desktop_database`, `_default_browser_id` and the wrapper call all route through it. `ping` is answered without work (`:677-678`); shutdown sets `stopping`, kills children, joins the worker (`:175-178`).

### Verified

- **R1 responsiveness:** four stall tests (sudo, systemctl, update-desktop-database, xdg-settings) prove ping, window event dispatch, lock-deadline unlock and unread-reply while the child is gated; `run_command` bounds every invoked child; `test_worker_command_timeouts_report_failure_then_recover` shows timeouts reach state and the caller as `error` without killing the listener and recover afterward.
- **R2 ordering:** single worker; `current()` checked before resolve→apply and again after `ensure_slice` (`:90-94`); stale results are logged `stale` and never touch `net.site_block` or waiters (waiters are adopted to the latest generation in `_adopt_waiters`). `test_disable_during_apply_orders_flush_and_rejects_obsolete_success` asserts `replace` then `flush`, state `off`, and no early `ok`. Shutdown tests confirm the stalled child is gone within 4 s.
- **R5:** `refresh_entries` still takes `_entries_lock(0)`; `_sync_files` journal/rollback untouched; `strict_cache` only changes the return value and retries a pending cache refresh on an otherwise unchanged plan.
- **Cross-spec contract:** `observed_at` has the three keys, each set only after its check; periodic re-observation test passes timestamps forward; top-level fields unchanged, `launcher_refresh` added.
- Existing reconciliation still runs every period (`:457-460`), per acceptance.

### Findings

**1. Blocking — launcher-refresh failure is reported as a user-facing toast on every cycle, and "stepped aside for setup/remove" counts as a failure.**
`ds/listener.py:409-411` notifies "Launcher refresh failed" every time `entries_ok` is false, unlike every other listener notice (`_note_invalid`, `_note_resolve`, `_note_hold`, links), which latch once. `ds/setup.py:1209-1210` returns `int(strict)` = 1 when the entries lock is held, and `ds/setup.py:995-1010` adds `apps` to `_cache_pending` before checking `shutil.which`, so a missing tool makes every subsequent strict refresh return 1.
Triggers: (a) a periodic tick or a user `refresh` landing while `distractions setup`/`--remove` holds the entries lock (it holds it across `xdg-settings set`, "several seconds on this machine", `setup.py:1232-1233`, `:1275`, `:1284`); (b) `update-desktop-database` missing, persistently failing, or hanging past `UDD_TIMEOUT` — the old docstring explicitly tolerated a missing/slow cache refresh as "changes nothing".
Impact: (a) a false "Launcher refresh failed" toast during the person's own setup, `launcher_refresh: unavailable` in state (which fn-26 will render as unhealthy) until the next period, and `reload`/`refresh` replying `error` although config and firewall applied; (b) a toast every 60 s indefinitely and `distractions reload` printing "Reload failed" forever.
Fix: distinguish deferred from failed in `refresh_entries` (e.g. return 0 or a sentinel when `held` is false and let `launcher_refresh` say `deferred`), and latch the toast (once per failure streak, reset on success) the way the sibling notices do.

**2. Nonblocking — a failed `ensure_slice` now silently skips the wrapper.** `ds/listener.py:92-93` returns `unavailable` without calling `net._notice_unavailable()`; the old `_apply` docstring deliberately still called the wrapper because a failed `systemctl start` is not proof the cgroup is missing. Trigger: `systemctl --user` hung or erroring while the slice already exists. Impact: `site_block: unavailable` with no notice and no replace until the next period. Fix: either still attempt the wrapper (it refuses safely) or call `_notice_unavailable()` on this path.

**3. Nonblocking — reply gating on `links_ok`.** `ds/listener.py:413` makes `reload`/`refresh` answer `error` when `xdg-settings get` cannot answer, even though the config and firewall applied; the CLI then shows "Reload failed" in addition to the links notice. This is a deliberate-looking semantic change; confirm it is wanted.

**4. Nonblocking — periodic forced hold push on the loop.** `ds/listener.py:459` adds at least one synchronous `omarchy-shell silencedSenders` IPC (10 s bound, `hold.py:98-111`) plus a pactl scan every period on the event loop. Bounded and hold ownership is loop-side by design, but it is a new synchronous per-period cost the task asked to audit.

**5. Nonblocking — `launcher_refresh` reads `ok` after `start`** (`:367`, `:411`) although no entry refresh ran. Cosmetic state accuracy.

**6. Nonblocking — test strength.** `_assert_reconciliation_stall` asserts `hold` is `False` at the end, which is also its initial value, so the "hold transition before child completion" claim rests on the workspace/lock flow rather than an observed changed value. Consider asserting the intermediate hold state or `notification_hold` timestamp movement.

**7. Note only.** `run_command` sends `killpg(SIGKILL)` to the child's pgid after a normal exit (`ds/net.py:69-72`); on an already-reaped, empty group this is ESRCH and harmless, but pgid reuse is theoretically possible. `_reload_wait()` is now ~255 s, so a CLI `reload` is bounded but can block for minutes under compound stalls.

Finding 1 is an introduced regression on a normal workflow (setup) and on a previously tolerated environment; the rest are judgment calls or future-task material (R3/R4 no-op refresh and repair belong to `.2`).

<verdict>NEEDS_WORK</verdict>