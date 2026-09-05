I have everything needed; nothing further depends on unresolved results.

## Review: fn-28-room-for-the-early-leave-reason.1

**Scope reviewed:** `e3ebaee..7d9272b` — `ds/ui.py`, `tests/test_ui.py`, `README.md`.

### Correctness against the native contract

- `ds/ui.py:73-78` builds `["omarchy-menu-input", prompt, "--width", "900"]`. The installed `/usr/bin/omarchy-menu-input:11-30` takes `$1` as the prompt and scans the remainder for `--width <value>`, so positional-then-flag ordering is exactly what the command expects. The value is passed as `int()` into the payload (`:44`), and `str(900)` satisfies that.
- `width` is keyword-only with `None` default; when omitted, argv is byte-identical to the pre-change form. `_run`, `rstrip("\r\n")`, timeout and `Unavailable` paths are untouched (`ds/ui.py:40-51`).
- Both reason entry points route through `prompt_reason`: menu `ds/ui.py:316` and CLI `ds/lock.py:237`. Every other `input(...)` caller (`Minutes` :110, `Purpose` :122, `Site or app` :182, integer settings :288) omits width. R1's "other prompts remain unchanged" holds.
- `_cli_unlock` (`ds/lock.py:228-244`) still hands the prompted text to `unlock()`, which owns min-length validation; `tests/test_lock.py:217-230` covers refusal keeping the lock and hooks unfired. No lock-engine or persisted-data change.

### Tests

- `tests/test_ui.py:180-197`: text/cancel/timeout/missing exercised for both `width=None` and `width=900`.
- `tests/test_ui.py:254-266`: UTF-8 (CJK, em dash, emoji, 40× Greek) reason round-trips for `min_chars=0` and `50`; exact argv asserted via the stub's `sys.argv[1:]` log (`["input", prompt, "--width", "900"]`); a plain `ui.input("Name")` immediately after asserts `["input", "Name"]` with no width leak.
- Quick command covers `tests.test_lock`, so the refusal test is in the gate.

### Documentation and boundaries

- `README.md:10` states the prompt is wider, clamps to the screen, remains single-line and elides long text — matches the spec's edge-case wording.
- No version bump, no Omarchy file edits, no new dependency. Conductor evidence: native width 300 and 900 both `returncode 0` with text preserved, `lock_unchanged: true`, branch helper reports exact reason round-trip and Escape → `None`.

### Findings

**Blocking:** none.

**Nonblocking (cosmetic):**
1. `tests/test_ui.py:254` — test name `..._preserves_utf8_ordinary_input_unchanged` reads as one clause; it actually verifies two properties. Optional rename or docstring; no behavior impact.
2. `ds/ui.py:128` — the literal `900` could be a module constant so the value is named once, but with a single caller this is preference, not a defect.

Nothing in the task's acceptance criteria (R1–R3) is unmet by this change; visual smoke, Fable review and Flow completion are explicitly conductor-owned and are evidenced above rather than assumed.

<verdict>SHIP</verdict>