Nothing further is needed; the last batch closed every open question, so I'm ready to write up.

## Review: fn-29-type-focus-minutes-directly.1 (recheck of prior SHIP)

### Prior reviewer output — rechecked
The prior review reported no findings. I confirm each contract check it made, with one write-up correction: the prior text quotes the native argv as `["input", "Minutes (e.g. 25; 0 = until unlock)"]`, but the reviewed commit actually passes `width=500` (`ds/ui.py:103`), and both the tests (`tests/test_ui.py:215,229`) and the conductor evidence (`"width": 500`) agree on `["input", "Minutes (e.g. 25; 0 = until unlock)", "--width", "500"]`. That is a description slip in the prior review, not a defect in the change. The two nonblocking observations it made (permissive `int()` parsing of `"+5"`/`"1_000"`; `notify` asserted via mock rather than fake binary) stand as nonblocking and pre-existing.

### What I verified

**R1 — direct entry, no list.** `ds/ui.py:97-119`: `prompt_lock` goes straight to `input(...)`, no `select`. Zero maps to `None` at `:113-114`. Empty/whitespace returns `None` before the purpose prompt at `:104-105`. `tests/test_ui.py:209-218` asserts the exact argv for `"37"`, `" 12 "`, `"0"` and that `_calls("select") == []`. The fake `omarchy-menu-input` (`tests/test_ui.py:51-77`) logs `sys.argv[1:]`, so `--width 500` is genuinely observed, not mocked. `ui.input`'s `width` kw-only param (`ds/ui.py:73-76`) predates this change and is pinned by `tests/test_status.py:427-430`.

**R2 — invalid/empty/cancel cannot lock; CLI unchanged.** `tests/test_ui.py:234-253` drives the real `_lock_action(False)` (`ds/ui.py:303-316`) with `ds.lock.lock` patched, asserts not-called, `is_locked()` false, exactly one input invocation, one queue item left (`_qlen` exists at `:467`), and the notice only for `-1`/`2.5`/`nope`. `ds/lock.py` untouched: `_cli_lock` `:203-225` (`forever`→`None`, `int()` + `<0` rejection) and `lock()` `:39-41` (`None` → no deadline) are unchanged, so UI `0→None` lands on the same until-unlock path as CLI `forever`. Default fallback: `type(default) is not int or default < 0 → 25` (`:101-102`) covered for `-1`, `True`, `"40"`, `None`, `2.5` at `:220-230`. Purpose opt-out (`ask_purpose: False`) and purpose-cancel (`→ ""`) at `:225-232`. Timeout and Unavailable at `:255-265`.

**fn28 preservation.** `prompt_reason` (`ds/ui.py:122-123`) still `width=900`; its width test (`tests/test_ui.py:280-292`) untouched.

**Callers/contracts.** `tests/test_lock.py:288-329,450` patch `prompt_lock` with tuple/`None`/`Unavailable` — signature-compatible. `tests/test_status.py:440` `["cfg"]` holds.

**Stale wording.** Grep for `Lock for|Other…|offers first|duration menu|preset|50 minutes|90 minutes|Until I unlock` outside `.flow/` returns nothing. README updated in three places (`README.md:78,140,162`).

**Boundaries.** No new deps, no version bump, no lock-engine or persistence change. The `.flow/specs/*.json` churn in the diff is flowctl bookkeeping.

### Findings
No blocking findings.

Nonblocking (not required):
- `default_minutes: 0` renders `Minutes (e.g. 0; 0 = until unlock)` (`ds/ui.py:103`, exercised at `tests/test_ui.py:221`). Technically correct per spec (0 is a valid non-negative int), just a slightly redundant hint. Taste only.

### R3 — conductor-owned
Full-suite pass, Fable review, and local install are outside this diff. Supplied evidence (`prompt_lock` only; `lock_unchanged: true`; typed `37`→`(37,"")`, `0`→`(None,"")`, cancel→`None`) matches the code paths above. I did not run anything.

<verdict>SHIP</verdict>