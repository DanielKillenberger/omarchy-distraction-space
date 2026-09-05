Nothing further needed; all the context required is in hand.

## Re-review: fn-28-room-for-the-early-leave-reason.1 (`e3ebaee..f75e837`)

### Prior findings

1. Test name `test_prompt_reason_width_preserves_utf8_ordinary_input_unchanged` (cosmetic) — **not-fixed**, remains nonblocking; no behavior impact.
2. Literal `900` in `ds/ui.py:128` could be a constant (cosmetic) — **not-fixed**, remains nonblocking; single caller.

Both were explicitly optional and do not gate the verdict.

### What changed since 7d9272b

- `tests/test_status.py:427-430`: the `StubContractTests` signature contract now expects `["prompt", "timeout", "width"]`, asserts `width` is `KEYWORD_ONLY` with `None` default. `_params` (`:418-419`) lists every parameter including keyword-only, so the expected list is correct and the contract would have failed at the previous head without this update — the follow-up is a required fix, not drift.
- Task file now names `tests/test_status.py` and widens the Quick command to include `tests.test_status.StubContractTests`.
- `.flow/evidence/*.json|png`, `.flow/reviews/*`, spec JSON: conductor-owned receipts, authorized per the handoff. Nothing in them alters runtime.

### Correctness recheck

- `ds/ui.py:73-78`: `["omarchy-menu-input", prompt, "--width", "900"]` matches the installed script (`/usr/bin/omarchy-menu-input:11-30`): `$1` is the prompt, remainder scanned for `--width <value>`, value passed through `int()` at `:44`. With `width=None` argv is byte-identical to before. `_run` (`:40-51`) untouched: timeout → `None`, `OSError` → `Unavailable`, rc 1 → `None`, other rc → `Unavailable`. `rstrip("\r\n")` retained.
- Only `prompt_reason` (`:128`) passes width; `Minutes` (`:110`), `Purpose` (`:122`), `Site or app` (`:182`), settings (`:288`) do not. Both reason entry points — menu (`ds/ui.py:316`) and CLI (`ds/lock.py:237`) — route through `prompt_reason`, so R1 holds for both.
- `lock.py:228-244` unchanged; `unlock()` still owns min-length. `tests/test_lock.py:217-230` covers refusal keeping lock, no hook, no log entry.
- Mock compatibility: the only patch of `ds.ui.input` (`tests/test_ui.py:246`) is a `MagicMock(return_value=None)`, which accepts the new `width=` kwarg. `prompt_reason` patches (`test_ui.py:496`, `test_lock.py:235,321`) are unaffected since its signature is unchanged (`test_status.py:441` still asserts `["min_chars"]`).

### Tests

- `tests/test_ui.py:180-197`: text/cancel/timeout/unavailable for `width` in `(None, 900)`.
- `tests/test_ui.py:254-266`: the INPUT stub (`:51-77`) logs `sys.argv[1:]` verbatim and echoes the queued text, so the exact-argv assertion `["input", prompt, "--width", "900"]` and the UTF-8 round-trip (CJK, em dash, emoji, 40× Greek) are genuine end-to-end checks through a real subprocess with `encoding="utf-8"`. Trailing `ui.input("Name")` confirms `["input", "Name"]` — no width leak.
- Contract test updated as above. The conductor-reported red-then-green for the width test and the 43/25-test gate logs are consistent with what the diff would produce; I did not re-run anything.

### Documentation / boundaries

`README.md:78` adds one sentence pair: wider prompt, fits within screen edges, single-line, long text elided. No version bump, no Omarchy file edits, no new dependency.

### Findings

**Blocking:** none.

**Nonblocking:**
- Prior items 1 and 2 stand as cosmetic.
- Observation, not a defect: on an Omarchy build whose `omarchy-menu-input` predates `--width`, unrecognized args would be ignored by a permissive parser or could fail. The spec's Decision Context pins the installed native command as the base and accepts this; out of scope here.

R1–R3 are met within the task boundary; native visual smoke is evidenced in `.flow/evidence/fn-28-room-for-the-early-leave-reason.json` (width 300/900 rc 0, `lock_unchanged: true`) rather than assumed.

<verdict>SHIP</verdict>