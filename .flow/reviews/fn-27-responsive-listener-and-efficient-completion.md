## Scope

Reviewed f0cc79a → 1bacfd0 against spec fn-27 and tasks .1/.2/.3. The range also carries fn-25/fn-26 content (`ds/hypr.py`, `ds/launch.py` scope/audio work, `ds/state.py` health projection, `BarWidget.qml`, `ds/ui.py`). I read those only for cross-spec boundary compliance; they do not touch listener scheduling or state production, so fn-26's "fn-27 alone edits listener scheduling/state production" holds. The one fn-27 edit outside its file list (`launch._default_browser_id` → `run_command`) was conductor-authorized in the .1 receipt.

## R-ID mapping

| R | Implementation | Tests | Live evidence |
|---|---|---|---|
| R1 | `ds/listener.py:346-398` single `ds-reconcile` worker; `ds/net.py:32-86` `run_command` bounds every child (sudo, systemctl, udd, xdg-settings, notification) with cancel + killpg/reap; `ping` at `:693-694` answers without work | `_assert_reconciliation_stall` ×4 tools (ping, window dispatch, hold true→false, due-lock unlock, waiter still pending, single child start); `test_worker_command_timeouts_report_failure_then_recover`; `test_command_deadline_kills_and_reaps_child`; `test_timeout_still_kills_descendant_after_parent_exits` | Controlled stalls are the spec's required evidence (R6); satisfied |
| R2 | `request()` `:333-345` bumps gen/re-adopts waiters, coalesces via `rerun`; `take_result()` `:407-410` discards stale gens without publishing or replying; `current()` re-checked before/after each wrapper call in `_Reconciler.reconcile` `net.py:353-383`; shutdown `:182-186` sets `stopping`, invalidates, kills children, joins ≤3 s | `test_disable_during_apply_orders_flush_and_rejects_obsolete_success` (replace→flush, no early ok, state off); `test_disable_during_check_never_repairs_or_acknowledges_stale_policy`; `test_reconcile_obsolete_check_never_repairs_or_seeds`; `test_stale_generation_dropped`; two shutdown-stall tests (child gone within 4 s) | n/a |
| R3 | `net.py:364-372` equal shortcut requires baseline tuple match **and** fresh `check ds` returning the baseline `(dev, ino)`; baseline written only at `:387` after replace=on and post-check ok; empty policy always flushes and invalidates `:356-363` | `test_reconcile_equal_reordered_policy_checks_every_cycle` (records 3 replaces before → 1 replace + 3 checks after, with reordered/duplicated input); `test_equal_refresh_checks_and_advances_observation_without_replace`; `test_refresh_resolves_without_rereading_config` (changed hosts → replace) | `v3-live-reconcile.json`: real `_Reconciler` + real wrapper + real nft in netns, `["replace","check","check","check"]` over three equal cycles |
| R4 | Check failure/identity mismatch/malformed → invalidate → one replace → one post-check → baseline or `unavailable` + notice `:373-389`; `_check_result` `:319-335` rejects nonzero, non-dict, bool, ≤0 ino, extra keys; wrapper `check_policy` compares full token stream incl. rule order and level-5 path, rejects numeric cgroup fallback, stats slice before/after | `test_reconcile_drift_identity_failure_and_recovery` (missing table, rule drift, changed ino, changed dev, old-wrapper stdout, OSError, timeout); `test_reconcile_failed_apply_or_postcheck_never_seeds_baseline`; `test_reconcile_rejects_malformed_check_and_bounds_repair` (exactly 3 calls); `test_unverifiable_check_reports_error_then_replaces_on_recovery` (listener level); `test_nft.py` drift matrix + slice identity change/missing | Live: extra-rule and deleted-table drift each `["check","replace","check"]`; `LiveNftTests` real nft 1.1.6 listing matched the rendered expectation incl. empty and 4096-address IPv4-only sets. Real slice *recreation* is covered by controlled identity change only (see N4) |
| R5 | `setup.refresh_entries` `:1210-1216` keeps `_entries_lock(0)`, returns `ENTRIES_DEFERRED` to strict callers; `_sync_files` journal/rollback untouched; `strict_cache` only affects return value; listener maps deferred/ok/unavailable `:376-381`, latches the toast once per streak `:420-425` | `test_entries_lock_defers_without_failure_and_recovers`; `test_launcher_failure_notice_once_per_failure_streak`; `test_startup_does_not_claim_entry_refresh`; existing setup ownership/rollback/removal suite | n/a |
| R6 | — | Before/after replacement counts recorded deterministically in `test_reconcile_equal_reordered_policy_checks_every_cycle`; no CPU/latency claim anywhere in README or docs (grep confirmed) | Counts also recorded in `v3-live-reconcile.json` |

Cross-spec contract: `observed_at` carries exactly `site_block`/`notification_hold`/`links`, each stamped after its own check completes (`:288`, `:369`, `:386`), including periodic (`test_periodic_observations_advance_without_policy_changes`); `ping` returns `ok\n` without scheduling; existing top-level keys preserved, `launcher_refresh` additive. Sudoers grant is path-only (`install/sudoers…:3`), so `check ds` needs no install change.

## Correctness traces performed

- **Baseline/disable interleaving.** The only window where the worker can write a baseline after a disable is `net.py:382→387` racing `request()` `:337-341`. `take_result` for that generation is necessarily stale (gen was bumped) and invalidates at `:408` before any subsequent `reconcile` can run, because `_launch` is only reachable from `request()` when idle or from `_follow` after `busy` clears. Unreachable in practice.
- **Periodic coalescing.** Periodic-while-busy sets `rerun` without bumping gen; the non-stale path calls `_follow(periodic=True)` → fresh `request("periodic")`. A stale path always implies an explicit request bumped gen, so `_launch(self.latest, self.reason)` runs the right generation. No lost or duplicated cycles.
- **`result is None` on a non-stale path.** `reconcile` returns `None` only when `current()` is false; `gen == latest` at take time implies it was true throughout (gen is monotonic) and `stopping` is only set after the loop exits. So `net.site_block = result or "unavailable"` never publishes a fake `unavailable` for the current gen.
- **Empty-set rendering.** `_elements([])` emits no `elements` line, matching nft's omission; the live 4096 case is IPv4-only (empty v6) and the count=0 case is both-empty — both passed against real nft, so v4-only production policies verify.
- **Wait budget.** `_reload_wait()` = 2·(10+30+30+60+15)+5 = 295 s; matches docs and the worst-case worker path (resolve, systemctl, check+replace+check, udd, xdg-settings get, browser lookup).
- **Shutdown under stall.** `_kill_children` terminates tracked children; `run_command` observes `cancel` every 0.1 s, then SIGTERM/0.2 s/SIGKILL/reap; later worker steps short-circuit on `current()`. Bounded by the 3 s join.

## Findings

No blocking findings. Nonblocking, ranked:

**N1 — `ds/net.py:350-352`: an unparsable cached address raises `ValueError` out of `reconcile`.** Trigger: hand-edited `addrs.json` (only path; `_write_cache` stores parsed addresses). Impact: `listener.py:370-373` reports `unavailable` with the "Network update failed" notice instead of the wrapper's "Site block unavailable". End state correct, message differs. Fix: catch `ValueError` in normalization and route through `_notice_unavailable()`.

**N2 — `ds/listener.py:353-395`: `work()` has no outermost guard.** Every risky call is inside a `try`, but if a future edit lets an exception escape before `self.pending = item`, `busy` stays `True` forever and every later request coalesces into a `rerun` that never fires. Fix: wrap the body in `try/finally` that always publishes an `unavailable` item.

**N3 — `_reload_wait()` 295 s is also the CLI socket timeout (`listener.py:49`).** Under compound stalls `distractions reload`/`refresh` can block for minutes. Documented in `docs/internals.md`; a shorter client-side cap with a "still working" reply would be a UX improvement, not a correctness issue.

**N4 — Real slice recreation is not exercised live.** Both live probes keep the host slice; recreation is proven only with controlled identity changes (`test_check_missing_changed_slice_and_failed_listing`, changed-ino/dev cases in `test_reconcile_drift_identity_failure_and_recovery`). R6 explicitly permits "changed enforcement identities" as test evidence, and a real recreation would touch the host user manager, so this is an acknowledged limit rather than a gap.

**N5 — `v3-live-reconcile.py` monkeypatches `run_command` to bypass `sudo -n`.** The evidence file states this. `check ds` is covered by the path-only grant by construction, but the branch listener has not made a real sudo `check ds` call end to end. Consistent with the "no deploy until marketplace admission" constraint.

**N6 — `_notice_unavailable` (2 s) is not in the wait-budget arithmetic.** Cosmetic; the 5 s slack covers it.

**N7 — `state.json` is rewritten every period** because `observed_at` is part of the change key (`listener.py:519`). Required by the fn-26 timestamp contract; noted for the bar's file-watcher cost only.

## Verdict

All six requirements map to implementation, deterministic tests, and (for R3/R4) real-kernel evidence with recorded replacement counts. Ordering, cancellation, baseline seeding, and drift repair trace correctly; no introduced regression or unmet task criterion remains.

<verdict>SHIP</verdict>