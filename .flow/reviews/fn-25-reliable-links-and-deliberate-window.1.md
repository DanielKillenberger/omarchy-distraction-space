I have what I need; no further reads are required.

## Review: fn-25.1 — explicit URL delivery vs. named-product reuse

**Change under review** (`83e32f6` → `e1f1b18`): `ds/launch.py` adds `Target.explicit_url`, sets it in `resolve_target` for scheme-bearing arguments, and gates `focus_existing` on `not target.explicit_url` in `_open_web`. Tests: named-reuse fixture switched to `open YouTube`, a new same-host deep-link test, and a matching window added to the failed-launch test.

### Correctness check against the code paths

- **Explicit URL bypasses reuse, argv preserved** — `ds/launch.py:190` sets `explicit_url=True`; `ds/launch.py:565` skips `focus_existing`; `profile_flags(target.url)` at `:572` passes the raw argument, so path/query/fragment/percent-encoding survive untouched. R1 satisfied at the invocation boundary (the task's stated success criterion).
- **Named-product reuse remains** — `_entry_target` (`:172`) leaves `explicit_url=False`, so `open YouTube` still goes through `focus_existing`. The fixture class change to `chrome-youtube.com__-Distraction` is correct, not a test weakening: `_entry_url` uses `hosts[0]`, and `catalog.json:53` lists `youtube.com` first, so that is the exact class `profile_class` matches. R2 reuse satisfied.
- **Failure reporting** — with a matching window present, `test_launch_reports_a_browser_that_did_not_start` now exercises missing binary (exit 1, no scope) and non-zero settle exit (exit 1). This is the R1 "no success from discovery alone" clause.
- **Forwarding/malformed/absent-launcher untouched** — `forward()` never reads `explicit_url`; `_url_host` refusals precede the flag; `pick_browser is None` path unchanged. Existing tests for those paths still run unmodified.
- **Focus/lock semantics for the new launch path** — a fresh explicit-URL window is routed by the standing `PROFILE_RULE` (`ds/hypr.py:288-289`, effect `name:distraction silent`), so it lands on the space without switching the person's workspace, which the new test asserts via absence of a workspace-focus dispatch. Release/snap-back is listener-owned and not touched here.
- **No other callers** of `focus_existing` or `Target(` exist outside `launch.py`, so no hidden regression surface.

### Findings

**Blocking:** none.

**Nonblocking**

1. **Documentation now out of date, must be recorded for final integration** — `docs/internals.md:19` ("Before launching, `open` looks for a window of that class for the same host … Either way nothing is launched twice") and `README.md:152` ("or focus its existing window") describe the pre-change host-only reuse for all targets. The task acceptance asks to "record documentation implications"; the diff contains no such record and the task's Done summary is still `TBD`. The cross-spec contract defers doc edits to post-integration, so not editing is fine, but the done summary should name these two locations and the new rule (name → may reuse; explicit URL → always delivered). Cannot verify from the diff alone.

2. **Test could assert non-interaction with the existing window** — `tests/test_launch.py:328-361` proves the launch occurred but does not assert that no `hl.dsp.focus`/`hl.dsp.window.move` for `0xabc` was dispatched in the `existing=True` case. Low value given the code path is an early `if`, but it would make the "no reuse shortcut" claim explicit. Optional.

### Verdict

The task's acceptance criteria (R1, R2, R5 portion for same-host deep links and named reuse) are met by the code and covered by focused tests; no introduced correctness bug or regression found. Remaining items are documentation bookkeeping owned by the integration step.

<verdict>SHIP</verdict>