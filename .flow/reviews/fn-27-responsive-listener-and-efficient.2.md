I have what I need; no further reads are required. Final analysis follows.

## Scope reviewed

Change `ae9b3e9d..8edafdba` (diff at `/tmp/fable-fn-27-responsive-listener-and-efficient.2-8edafdba/diff.txt`): `ds/net.py` (`_check_result`, `_Reconciler`, `run_command` cleanup, notice text), `ds/listener.py` (reconciler wiring, waiter budget, `_ask` text), `docs/internals.md`, `tests/test_net.py`, `tests/test_listener.py`. Sibling task .3's `check ds` verb is present in `distractions-nft:248-282` and is treated as an available dependency, not re-reviewed.

## Correctness walkthrough (verified against source)

**Baseline rules (R3).** `ds/net.py:347-389`: the baseline is written only at line 387, after `_apply_result` returned `"on"` *and* `_check_result` returned a validated identity *and* `current()` still holds. The equal-policy shortcut (line 365-372) requires both a matching normalized tuple and a fresh check whose `(dev, ino)` equals the stored identity. Equal addresses alone never return `"on"` without a check. Normalization dedupes and sorts by `(version, int)`; `test_reconcile_equal_reordered_policy_checks_every_cycle` records the before/after counts (3 replaces legacy → 1 replace + 3 checks), satisfying R6's measurement requirement.

**Drift/identity/failure (R4).** Nonzero check, changed `ino`, changed `dev`, malformed JSON, `OSError`, and `TimeoutExpired` all yield `None` from `_check_result` (lines 319-335; note `type(...) is not int` correctly rejects JSON booleans) and take the invalidate → replace → check path, bounded to exactly one replacement per cycle. A failed post-check notifies and reports `unavailable` without seeding a baseline (lines 384-386). Covered by `test_reconcile_drift_identity_failure_and_recovery`, `test_reconcile_failed_apply_or_postcheck_never_seeds_baseline`, `test_reconcile_rejects_malformed_check_and_bounds_repair`, and the listener-level `test_unverifiable_check_reports_error_then_replaces_on_recovery`.

**Sudoers permits `check ds`.** I specifically checked this because a verb-enumerated grant would have made every verification fail in production. `install/sudoers.omarchy-distraction-space:3` grants `NOPASSWD:` on the wrapper path with no argument restriction, so no grant change is needed.

**Generation/disable ordering (R2 preservation).** `listener.py:337-338` invalidates before bumping `gen` when blocking is disabled; `take_result` (line 407-409) invalidates on any stale generation; `work()`'s exception path (line 371) and shutdown (line 183) invalidate. I traced the one interleaving that could set a baseline after a disable: worker passes `current()` at `net.py:382`, main thread invalidates and bumps `latest`, worker writes baseline at line 387. Because the worker is serialized on `busy` and `take_result` for that generation is necessarily stale (→ invalidate) before any subsequent `reconcile` can run, the stale baseline is unreachable. `test_disable_during_check_never_repairs_or_acknowledges_stale_policy` and `test_reconcile_obsolete_check_never_repairs_or_seeds` pin this.

**Waiter budget.** `_reload_wait` now includes `3 * COMMAND_TIMEOUT`; with `SYSTEMCTL_TIMEOUT=30`, `UDD_TIMEOUT=60`, the docs' 295 s figure is arithmetically correct. The stall test now asserts exactly three network commands for `sudo` (stale check + repair + post-check), which matches the traced behavior.

**`run_command` cleanup change.** `completed` gating (`net.py:44-76`) skips `killpg` only after `communicate` returned; the timeout path still kills the group even when the leader has exited. Both cases have focused tests. Conductor-authorized; no regression identified.

## Findings

No blocking findings. Nonblocking observations, ranked:

1. **`ds/net.py:350-352` — invalid cached address surfaces as the wrong notice.** Trigger: a hand-edited `addrs.json` entry that `ipaddress.ip_address` rejects (only reachable through manual edits; `_write_cache` only stores parsed addresses). Impact: `ValueError` propagates to `listener.py:370-373`, producing state `unavailable` plus the "Network update failed / Keeping the current site block" notice, whereas pre-change the wrapper refusal produced "Site block unavailable". End state is identical; only the message differs. Optional fix: catch `ValueError` in normalization and route it through `_notice_unavailable()` → `"unavailable"`.

2. **`ds/listener.py:66` — `_ask` error text now slightly wrong for `release`.** A refused `release` (past deadline / window gone) now reads "could not complete all requested work". Cosmetic; consider branching the message on the verb.

3. **Behavior change: disabled/empty policy flushes every periodic cycle** (`net.py:356-363`, `test_site_block_disabled_flushes_each_refresh_and_keeps_hold`). This replaces the prior flush-once shortcut. It is justified by task .3's summary (check cannot certify table absence) and `destroy table` is idempotent, but it is one privileged `sudo` call per minute while disabled. Documented at `docs/internals.md:79`. Acceptable within the spec's "no cache shortcut" boundary.

4. **Test gap (minor):** the listener-level fake `sudo` always returns `{"dev":1,"ino":2}`, so recreated-slice identity change is exercised only at unit level with mocked `run_command`. Given that unit coverage exists, this is a suggestion, not a requirement.

5. **Design note:** any refresh/reload arriving during an in-flight equal-policy check discards the baseline and forces a replace on the coalesced rerun (visible as the 3-command count in the stall test). Safe and bounded; slightly more work than strictly necessary.

## Acceptance check

- Reordered equal addresses, modified policy/table, missing table, recreated slice, failed apply/check, recovery — covered.
- Periodic verification remains; explicit refresh/reload completion stays truthful (`observed_at.site_block` advances only after a real check/flush; `test_equal_refresh_checks_and_advances_observation_without_replace`).
- Before/after replacement counts recorded deterministically.
- No new privileged surface: only the fixed `check ds` verb via the same wrapper path and bounded stdin; wrapper validation untouched.

<verdict>SHIP</verdict>