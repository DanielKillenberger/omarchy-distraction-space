## Review: fn-26 …v3.1 (744d2ef → 7981bbe)

**Scope checked:** `ds/state.py` health projection + ping, `ds/ui.py` menu/settings/status action, `BarWidget.qml`, and the new tests, against task acceptance and the parent's cross-spec contract. Read-only inspection; no tests run.

### What holds up

- **R2 / "don't stamp on read":** `status()` now returns the listener's own `updated` (or `None`), adds `response_at`, and passes `observed_at` through untouched (`ds/state.py:335-337`). `test_health_observation_states_and_saved_provenance` asserts the state file's bytes are unchanged across a read. Legacy state without `observed_at` → every enabled service `unknown` (`ds/state.py:275-276`), covered by `test_missing_malformed_and_legacy_state_are_unknown`.
- **Contract fidelity:** stale threshold is `> 121 s` (`ds/state.py:216,277`); ping is `ping\n` expecting `ok\n`, bounded by a monotonic deadline that survives a dripping reply (`ds/state.py:224-239`, tested with a real drip server); the listener producer is untouched; `_health` derives from saved values + configured intent + timestamps + ping exactly as the contract lists. `status()` reads config via `config._read()` not `load()`, so it never creates the config file (existing `test_status_json_ignores_missing_and_malformed_config` still asserts that).
- **Expected-hold logic matches the producer:** `_health`'s `expected` for `notification_hold` (`ds/state.py:263-266`) mirrors `hold.effective_hold` (`ds/hold.py:87-91`) for `off-space`, `locked`, `never`; `hold.push` returns `on/off/unavailable` (`ds/hold.py:187`), which is what the comparison consumes.
- **R3 menu:** `hypr.active_window()` is captured before the first `select` (`ds/ui.py:324`), verified by call-order assertion in `test_release_captures_window_before_menu_focus_and_uses_saved_duration`. The release line is byte-identical to `cmd_release` (`ds/listener.py:41` vs `ds/ui.py:361`), so no-window and no-listener refusals reuse the existing paths. Cancel/`Invalid`/`OSError` leave the file unchanged and never emit "Settings saved" (`test_v3_setting_failed_write_and_validation_do_not_report_saved`). The `open_links_in_space` toggle correctly reads through `c.get(key, DEFAULTS[key])` because `config.update` strips the unanswered key (`ds/config.py:367-369`); this also marks the question answered, consistent with `config set`.
- **Bar (R1):** malformed/absent `health` → `"unknown"` via an exhaustive shape check (`BarWidget.qml:52-61`); healthy-with-everything-disabled shows no dot; lock/held behaviour is unchanged. `hypr/bindings.lua:11`'s `grep -F '"locked": true'` still matches the emitted JSON.
- **Live listener interaction:** the pre-fn-27 listener answers `ping` with `error\n` (`ds/listener.py:660`) and performs no work, so `test_listener.py`'s `status --json` calls against a live listener can neither hang nor perturb it.

### Findings (all nonblocking)

1. **`PING_TIMEOUT = 0.2` will produce transient false "unresponsive" on a healthy listener** — `ds/state.py:217`. The listener's main loop is single-threaded and runs synchronous subprocesses per tick (`hyprctl activeworkspace` each second, `omarchy-shell` IPC up to 10 s in `sync_hold`, `xdg-settings` every 60 s in `check_links`, `_scan` on every reload). A ping landing mid-call waits for the loop to return to `select`. The bar now reads on every `state.json` write plus every 30 s, so over a session the dot will flip to "degraded: Listener did not respond…" and back with no real fault, which undercuts R2's stopped/unresponsive/working distinction and the "quiet indicator" decision. The contract only requires "short finite"; raising to ~1–2 s (and relaxing the `< 0.6` assertion in `test_listener_ping_deadline_even_with_dripping_reply`) removes almost all of this without changing semantics. I cannot show runtime evidence for the rate; this is a design-risk judgement from the loop structure.

2. **Enabled `site_block` with an empty address set reads as "pending / check setup"** — `ds/state.py:285-288`. `docs/internals.md:127` documents `site_block: off` as the legitimate result of "an empty address set" (list with no hosts). With `enabled: true`, a fresh `off` observation is classified `pending` → overall `degraded`, and the menu/status surfaces "Saved choice does not match the last observation; reload or check setup," which is untruthful for that configuration. Edge case (default list has hosts), so nonblocking; a fix would consult the expansion's host set (e.g. `_hosts(state.read_expansion())`) and expect `off` when it is empty.

3. **Bar poll timer reverses an earlier explicit decision** — `BarWidget.qml:119-124`; the prior test asserted `assertNotIn("Timer", qml)` and fn-9 R12 framed the bar as file-watch-driven. The reversal is justified here (a dead listener never writes `state.json`, and staleness is a function of elapsed time), and the poll is unprivileged so it stays inside the parent's boundary. Record the rationale in the deferred docs pass so it isn't reverted as drift.

4. **`status()["updated"]` changed meaning (response time → state-write time, may be `None`)** — `ds/state.py:335`. No in-repo consumer depends on the old meaning and `response_at` carries it, but it is an interface change under "preserve the existing status interface"; note it in the integration docs.

5. **Missing test coverage worth adding:**
   - No test asserts the fully healthy end-to-end projection (all three enabled, fresh `on` observations, responsive) yields `state == "healthy"` with empty `reasons`; the existing healthy assertions are per-service only.
   - `off-space` policy with `on_space is None` (hyprctl unavailable) → `unknown` (`ds/state.py:266,283`) is untested.
   - `cmd_status` text output's new `Health:` lines are untested (JSON path is).

### Explicitly out of scope / deferred

- Until fn-27 lands `ping`, every real read shows listener `unresponsive` and the bar dot. That is the contract's integration order, not a defect here.
- R4 live firewall/audio evidence belongs to task .2. QML behaviour is verified only by source-string assertions, which is the only offline option.

No introduced correctness bug or unmet acceptance criterion blocks this task; the items above are tuning, an edge-case truthfulness gap, and coverage gaps.

<verdict>SHIP</verdict>