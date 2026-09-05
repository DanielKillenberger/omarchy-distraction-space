---
satisfies: [R1, R2, R5, R6]
---
# fn-27-responsive-listener-and-efficient.1 Move reconciliation work off the listener event loop

## Description
Introduce bounded serialized side-effect work for firewall apply/flush, slice setup, and entry/cache reconciliation. Listener owns generation/order/result publication and refresh/reload waiter completion. Preserve setup/remove locks and no resurrection after removal. Publish cross-spec observed_at timestamps plus ping. Existing hold/notification work must remain functional; audit other synchronous checks for responsiveness.

**Files:** ds/listener.py, ds/net.py, ds/cgroup.py, ds/setup.py, ds/launch.py (only _default_browser_id cancellable execution), tests/test_listener.py, tests/test_net.py
**Touches:** ds/listener.py, ds/net.py, ds/cgroup.py, ds/setup.py, ds/launch.py (only _default_browser_id cancellable execution), tests/test_listener.py, tests/test_net.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_listener tests.test_net tests.test_setup tests.test_launch
## Acceptance
- Parent R1/R2/R5/R6 covered by controlled stalls proving event, hold and lock progress before child completion.
- Subprocess deadlines terminate/reap children and bound shutdown; missing binaries/all OSError degrade without killing listener.
- No stale apply result overrides disable or current policy; callers wait for actual applicable outcomes.
- Cross-spec observed_at and ping contract works with unchanged top-level fields.
- Keep existing reconciliation every period until separate optimization task.

## Done summary
Implemented serialized, cancellable reconciliation outside the listener event loop. Only applicable generations publish network/link/browser results and complete reload/refresh waiters; entry transactions retain the existing setup/remove exclusion and under-lock manifest check.

Task: fn-27-responsive-listener-and-efficient.1
Status: in_progress; conductor owns integration, Fable review, and completion.
Workspace: /home/daniel/Projects/omarchy-ds-worker-27

Baseline: green, 95 tests in 90.757s (pre-edit). Final Quick command gate: green, 106 tests in 95.703s. The classifier required full verification. Additional launch/shutdown verification passed 18 tests; focused timeout/cgroup verification passed 9 tests. git diff --check passed.

R1/R6: controlled stalled sudo, systemctl, desktop-cache and xdg checks prove ping, window movement, hold transition and due lock expiry finish before the stalled command, while waiters remain pending. Multiple refresh requests remain one active command and one coalesced rerun. The original firewall stall test failed red with ping timing out, then passed after implementation.
R2/R6: disable during apply ends with serialized flush and current off state; obsolete completion cannot acknowledge success. Timeout tests cover error replies, unavailable state, child reaping and successful retry for firewall, slice and cache. Shutdown tests cover both apply and browser lookup; browser lookup failed red because its child survived exit, then passed with cancellation. Client deadlines remain bounded across adopted generations.
R5: the existing setup ownership/rollback/removal tests remain green. Listener-only strict cache/lock failures return errors; pending cache work retries without changing ownership or replaying the file transaction. Setup/remove retain their existing best-effort cache semantics.

The conductor approved one additional ownership-limited edit: ds/launch.py::_default_browser_id uses the shared bounded command runner, preserving browser selection. No adoption-specific code or tests changed. Existing _assert_links_never_asks now waits for completed observed_at.links before taking its query-count baseline; its equality assertion is unchanged.

Cross-spec/docs implications: observed_at contains actual completed ISO observation timestamps for site_block, notification_hold and links, including periodic unchanged observations. Ping responds ok\n without scheduling work. Additive launcher_refresh reports entry reconciliation results. Reload/refresh may wait through bounded reconciliation rather than acknowledging scheduling; command deadlines are network 10s, slice 30s and cache 60s, with bounded cleanup and a two-generation client budget. Browser/default checks also run outside the loop and support shutdown cancellation. No live configuration was changed.

Periodic firewall replacement remains enabled; fn-27.2 owns verified no-op reconciliation. No CPU or latency improvement claims were made, and no review verdict is claimed.

stage: impl-review - skipped(policy: parallel-wave / host-deferred - conductor owns the gate)

Logs: /tmp/fn27-baseline.log, /tmp/fn27-red.log, /tmp/fn27-browser-red.log, /tmp/fn27-final-gate.log, /tmp/fn27-browser-green.log, /tmp/fn27-timeouts.log. Intermediate gate failures were resolved; final gate exit code was 0.

Follow-up integration fix: the combined suite exposed the existing exact apply(addresses) signature contract. That test was reproduced red. The public function now delegates to _apply_result and publishes its result; listener uses the internal helper. No signature metadata was forged and the contract assertion was unchanged. Follow-up gate passed 140 tests in 101.053s: PATH=/usr/bin:$PATH timeout 600 python3 -m unittest tests.test_net tests.test_status tests.test_listener tests.test_setup tests.test_launch. Log: /tmp/fn27-contract-gate.log.

Fable NEEDS_WORK correction (review /tmp/fable-fn-27-responsive-listener-and-efficient.1-b82c5984/review.md): setup refresh now distinguishes lock deferral (ENTRIES_DEFERRED) from actual failure. Listener publishes launcher_refresh=deferred and replies deferred when other requested checks succeeded. CLI exits 1 with “Refresh deferred”/“Reload deferred” and a retry explanation, never acknowledging unfinished work as ok or presenting a false failure toast. Periodic retry stays at the existing interval; no retry loop, queue growth, or deadline changes were introduced. Actual launcher/cache failures notify once per streak, including a missing tool, and the latch resets only on successful entry reconciliation. Startup publishes off because it skipped entry refresh. Failed slice startup now emits the existing unavailable notice while retaining unavailable/error outcomes. The controlled-stall helper explicitly verifies initial hold=true before final hold=false.

Lock deferral and startup tests reproduced red before the correction. Four focused regressions then passed; the full requested listener/setup/net/status gate passed 127 tests in 98.681s. Log: /tmp/fn27-review-gate.log. Existing API signature checks and failed-operation assertions remain unchanged. Aggregate links_ok error semantics are retained intentionally: a requested observation that could not finish is not a successful complete reconciliation; completed network state remains accurately published. Periodic hold IPC remains loop-owned and bounded, with actual completed re-observation required for timestamp freshness; moving hold ownership is outside this correction.

Documentation addition: explain deferred as a retryable nonzero outcome while setup/remove owns launcher updates; launcher_refresh states now include deferred. Re-review and lifecycle completion remain conductor-owned; this handover claims no SHIP verdict.

Conductor integrated implementation cd5108f, signature fix b82c598, and review fix0251539. Fable via Claude CLI returned SHIP after correcting deferral/notification behavior. Integrated focused136tests passed. Combined full426tests passed at2eb905f in172.461s; /tmp/v3-preoptimization-suite.log.
stage: impl-review - ran (model: claude-fable-5-1)
## Evidence
- Commits: cd5108f1803206a3023d371cd31ba8acc4fb795f, b82c598492c709d1cb9a5202240a5af9876f6d08, 02515398f7022a7bff6777149204e7f301ecc211
- Tests: PATH=/usr/bin:$PATH python3 -m unittest tests.test_listener tests.test_setup tests.test_net tests.test_status (136 passed), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (426 passed at2eb905f), git diff --check
- PRs: