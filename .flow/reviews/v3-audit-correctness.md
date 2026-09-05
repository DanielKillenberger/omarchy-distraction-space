## Independent correctness audit — v3 improvements (fn-25/26/27), f0cc79a → 59d70e8

**Scope covered.** Full code diff (`BarWidget.qml`, `distractions`, `distractions-nft`, `ds/{cgroup,hypr,launch,listener,net,setup,state,ui}.py`, all six test files) read against current head source; the three specs' cross-spec contract; all nine prior Fable reviews rechecked against head; `.flow/evidence/fn26-live-validation.json`. fn-27.2 (client-side `check` use) excluded as instructed; docs sync not flagged.

### Blocking findings

None. I found no introduced correctness or security regression with a reachable trigger.

Key verifications that passed on head:
- **Listener ordering/state (fn-27.1).** Single serialized worker: `_launch` is reached only when `busy` is false (`ds/listener.py:340-343, 429-435`); `current()` gates before resolve→apply and inside `_apply` (`:349-350, :100`); stale generations never touch `net.site_block` or waiters (`:405-407`); waiters re-adopted to the newest gen (`:436-442`) so a superseded `reload` still gets its reply. A `reload` that supersedes an in-flight periodic goes through the stale path → `_follow()` → `_launch(latest, "reload")`, preserving the disable→flush ordering (`:365-366`). Shutdown: `stopping` set before `net.shutdown()`, worker polls cancel every 0.1 s in `run_command` (`ds/net.py:44-52`), join ≤3 s.
- **Every child is bounded.** All callers route through `run_command` and catch `(OSError, TimeoutExpired)` (`cgroup.py:88`, `setup.py:1020`, `launch.py:435`, `net.py:308`); the new `OSError("reconciliation stopped")` on cancel is caught on every path.
- **`ping` does no work** (`listener.py:691-692`); `CLIENT_CAP` on accepts is new hardening.
- **Migration (fn-25.2).** `close_window_lua` gone repo-wide; `cmd_migrate` in a fresh CLI process works because `classify` falls back to `expansion.json` via `_current_entries()` (`hypr.py:353-357`); the launched product name comes from `classify`, never from argv, so the notification-supplied `address`/`identity` cannot inject anything. `/proc/<pid>/stat` index 19 after `rpartition(")")` is `starttime`.
- **Browser scope trampoline (fn-26.3).** `app_id` only from allow-listed literals; `"$@"` after `shift 2` is verbatim; missing `systemd-run` now exits 127 inside the settle window → same `False` as before. Live evidence shows Chrome root and audio PIDs inside `app-distraction.slice/app-com.google.Chrome-<pid>.scope`, webapp muted/work unmuted during hold, both unmuted after, new work stream unmuted, cleanup counts 0/0.
- **Health projection (fn-26.1).** `config._read()` merges `DEFAULTS` (`config.py:321`) so the `cfg[...]` lookups in `_health` cannot KeyError on a 2.x config; `hold.push([], True)` returns `"on"` (`hold.py:187`) so a sender-less list does not read as `pending`; `status()` never writes state; `hypr/bindings.lua`'s `"locked": true` grep still matches.
- **`distractions-nft check`.** Reaches `check_policy` only after uid/stdin-cap/address parsing (`:264-282`); fixed `nft` argv; read capped during consumption; `killpg` only when `returncode is None` (`:219-223`).

### Nonblocking findings (ranked)

1. **Periodic forced hold push re-asserts keys the person un-silenced by hand during a hold** — `ds/listener.py:471-474` now calls `sync_hold(force=True)` every 60 s on the loop; `hold.push(keys, on=True)` adds every key not currently in the shell's silenced list (`ds/hold.py:169`). Before this diff the forced push ran only at start/reload. Trigger: hold active, person un-silences a plugin sender in the shell; ≤60 s later it is silenced again. Impact: silent behavior change not required by the contract (which only needs `observed_at.notification_hold` re-observed). `Mute.sync` is safe by contrast (user-unmuted streams are skipped, `hold.py:611-615`). Fix: re-observe without re-asserting (stamp `observed_at` from a read-only `_read_silenced()` compare, or force only on effective-hold/key change), or document the re-assertion as intended.
2. **`PING_TIMEOUT = 0.2` produces transient false "unresponsive"** — `ds/state.py:217` (carried from fn-26.1 #1, not fixed). Trigger: the 30 s bar poll or a menu `state.status()` landing while the loop is inside `hold.push` IPC (`hold.py:98-103`, 10 s bound), `ui.notify` (5 s bound), or `apply_rules`/`_scan` during a reload. Impact: momentary degraded dot; also the post-toggle "Settings saved" detail (`ui.py:267`) can report "application pending: listener is unresponsive" when the reload's synchronous part outlasts `request_reload`'s 2 s. Fix: raise to ~1–2 s, relax the `< 0.6` assertion in `test_listener_ping_deadline_even_with_dripping_reply`.
3. **Strict launcher refresh fails forever when `update-desktop-database` is absent** — `ds/setup.py:1032-1036` adds `apps` to `_cache_pending` before `shutil.which`, so every strict refresh returns 1 → `reload`/`refresh` answer `error` (`listener.py:425-427`) although config and firewall applied; one toast per listener life. Carried residual from fn-27.1 re-review. Fix: treat a missing tool as "nothing to do" (return True / don't mark pending).
4. **Reply gated on `links_ok`** — `listener.py:425`: `xdg-settings get` failing makes `reload` print "Reload failed" though everything applied. Carried; confirm intended.
5. **Offer may never arrive / identity computed before class is populated** — `hypr.py:719-727, 611, 620`. If `openwindow` precedes the client listing (fallback `{"address"}`), or the listed client still has an empty `class`, the identity is `None` (no offer) or differs from the later recomputation in `_migration_target` (→ "disappeared or changed"). Recovers on the next `movewindow`/rescan. Carried from fn-25 #1. Fix: one bounded client re-fetch after a successful move.
6. **`HYPRLAND_INSTANCE_SIGNATURE` in the identity is live-only** — `hypr.py:596`; the evidence file has no `migrate` action smoke. Safe failure mode (nothing launched or closed). Carried.

Accepted limitations, not counted: explicit-wrapper-only scope mapping (unknown/forking wrappers), pre-muted streams not claimed, distraction `PULSE_PROP` inherited by a `forward()` cold-started from inside the distraction tree (fn-26.3 #1). Note-only: `run_command`'s retry after a 0.1 s `communicate` timeout cannot resume unsent stdin (CPython gates stdin registration on the per-call `input`), but that needs >64 KB of addresses (≈3800+ IPv4) to be reachable — not a realistic list.

### Prior-finding recheck

| Prior | Status on head |
|---|---|
| fn-27.1 #1 toast/lock contention | fixed (`setup.py:1213-1216`, `listener.py:376-377, 419-423, 427`, `_ask` `:62-65`) |
| fn-27.1 #2 ensure_slice silent | fixed (`listener.py:97-99`) |
| fn-27.1 #5 `ok` after start, #6 weak hold assert | fixed (`:374`; test asserts hold True→False) |
| fn-27.1 #3, #4 | not fixed, carried as #4, #1 |
| fn-27.3 #1 real-namespace test | fixed (`tests/test_nft.py:476-543`, opt-in; matches the "1 optional skip") |
| fn-27.3 #2 killpg after reap | fixed (`distractions-nft:219-223`) |
| fn-25.2 #1 unanswerable question | fixed (`hypr.py:620 elif identity`) |
| fn-25.1/.2 docs | fixed in README/internals |
| fn-26.1 #2 empty-host `off` | fixed (`state.py:280-285`, tested) |
| fn-26.1 #5 coverage | partly: healthy-overall and unknown-workspace tests added; text `Health:` lines still untested |
| fn-26.1 #3 Timer, #4 `updated` meaning | recorded in README/internals |
| fn-26.1 #1 ping timeout | not fixed, carried as #2 |

### Recommendation

No introduced blocking correctness or security regression; boundaries (process group, no window closing, bounded privileged wrapper, no bar-side privileged probing) hold on head, and the conductor's live evidence is consistent with the code paths as written. Item 1 is the only genuinely new behavioral change and is a judgment call rather than a defect; items 2–6 are carried, non-fatal edges with safe failure modes.

<verdict>SHIP</verdict>