## Review: fn-26-visible-health-and-accessible-v3.2 (3ab9232 → 308e1d5)

### Scope reviewed

The range bundles fn27.1/fn27.3/fn26.3 work that the conductor has gated separately. I concentrated on what this task owns — `README.md`, `docs/internals.md`, `.flow/evidence/fn26-live-validation.json`, `ds/state.py`, `ds/hypr.py`, `tests/test_status.py`, `tests/test_hypr.py` — and cross-checked each doc claim against the code in the tree.

### fn26.2-owned code

**`ds/state.py:246-285` — empty-host site block is healthy idle.** Correct. `_expansion_hosts` returns `[]` only for a well-formed expansion with no hosts, `None` for missing/malformed. The listener always writes `{"list": [...], ...}` (`listener.py:563-579`), so the `list` key lookup matches production shape. Downstream: `hosts == []` → `expected="off"` → healthy "Idle…"; `None` → `expected=None` → "unknown" via the existing `expected is None` branch at line 301; nonempty hosts → `pending`. `disabled`/`unavailable`/`stale` precedence is unchanged because those branches run first. `test_site_block_off_expansion_shapes_health` covers all nine paths including malformed-not-dict, malformed-list, malformed-hosts, and stale-empty.

**`ds/hypr.py:620-627` — no migration question without identity.** Correct. Previously an unavailable identity produced a notification with `action=None`, i.e. an unanswerable prompt. Now the offer is skipped; the window is still moved and the "opened" banner still fires (`_feedback().opened` at line 569 runs on `landed`). `test_adopt_skips_migration_offer_when_identity_is_unavailable` asserts the move, no `open` call, no close, and no "Keep your"/"separate" text. Dedup record `(identity, failed)` still stores `(None, False)`, so a later identity read can still produce an offer — sensible.

### Documentation accuracy (checked against code)

| Claim | Source | Result |
|---|---|---|
| Menu lists status/lock/enter-leave/release/list/settings | `ui.py:331-338` | matches |
| Settings labels (three quoted strings) | `ui.py:17-19` | matches |
| Bar refreshes every 30 s, dot + tooltip on non-healthy | `BarWidget.qml:119-145` | matches |
| `ping` 0.2 s deadline, 121 s stale | `state.py:216-217`, `:295` | matches |
| `migrate ADDRESS IDENTITY` command | `hypr.py:644` | exists |
| `_reload_wait()`, `ping` verb, `deferred` reply | `listener.py:19, :691, :426` | matches |
| `_detached` settle semantics | `launch.py:510-540` | matches |
| App-id map / `PULSE_PROP` append | `launch.py:38-63, :554-596` | matches |
| `status --json` key preservation, `updated`/`response_at` | `state.py:338-357` | matches |
| Reconciliation reuses table only after `check ds` | `ds/` has no `check ds` caller | **not in this tree** — fn27.2 concurrent, conductor-acknowledged |

### Live-evidence honesty

The evidence JSON and both docs correctly separate: deployed-wrapper HTTPS contrast (not branch wrapper), namespace apply/check/drift of the branch wrapper, actual-helper audio probe with hashes, the inherited-mute INCONCLUSIVE, the "existing work stream checked separately" caveat, and the explicit non-claim of a global leave/unlock transition. The `pre_fix_browser_scope: FAIL` and `pre_audio_identity_fix` sections preserve the failures that motivated fn26.3. I cannot verify the recorded SHA256s or `source_commit` in a read-only review; that is a limitation of this review, not a finding.

### Nonblocking findings

1. **`docs/internals.md` (Browser profile §) vs `README.md` limitations — forwarded cold work browser inherits the distraction `application.id`.** Internals states it; the README limitation bullets do not. Trigger: a person inside a distraction web app clicks an unlisted link → Chrome invokes the URL handler with its env → `launch.forward()` runs `_detached(..., env=None)` (`test_native_and_forward_leave_env_alone` pins this) → a not-yet-running work browser inherits `PULSE_PROP=…application.id=io.github.danielkillenberger.distraction-space` → WirePlumber gives it the distraction restore key, which is precisely the startup-order mute bleed the identity fix was meant to eliminate. Impact: work browser can start muted. Fix: either strip the plugin's `application.id` token from `PULSE_PROP` in `forward()`/`launch_in_slice()` (code owned by fn26.3), or at minimum add one sentence to the README limitations. Not blocking for a docs task since the residual is reported in internals.

2. **`README.md:1345`, `docs/internals.md:1621` describe fn27.2 reuse behavior not present at 308e1d5.** Conductor already flagged this as ordering to confirm before `done`. Ensure the final combined suite runs on a tree where the listener actually calls `check ds`; otherwise these paragraphs overstate.

3. **`docs/internals.md:124` state table shows `launcher_refresh: "ok"` but never enumerates `off | ok | unavailable | deferred`.** The `deferred` value is new in this range (`listener.py:418-427`). One-line doc gap.

4. **Pre-existing, not introduced:** with `site_block.enabled: true`, nonempty hosts, and an empty applied set (all addresses subtracted by `keep_reachable`, or a batch failure with no last-good set), health reports `pending` with a "reload or check setup" reason. Arguably a false-degraded, but the task explicitly scoped only the empty-host case.

5. **Test gap (minor):** no test asserts that `_health` reads `expansion.json` only on the `site_block == "off"` path; not needed for correctness, noted for completeness.

### Verdict

Both owned fixes are correct and regression-tested; documentation matches the implementation everywhere I could check, and the live-evidence prose distinguishes exercised from unverified. No blocking defect.

<verdict>SHIP</verdict>