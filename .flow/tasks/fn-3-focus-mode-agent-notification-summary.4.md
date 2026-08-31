---
satisfies: [R9, R10]
---

# fn-3-focus-mode-agent-notification-summary.4 Summary ledger and README

## Description
After a shown summary, record helpful / not-helpful plus an optional note with a three-state claim, and document the opt-in path (R9, R10). Finalization (README + shipped `focus.json`) lives here.

**Size:** S
**Files:** `distractions`, `focus.json`, `README.md`, `tests/test_summary_ledger.py`
**Touches:** [distractions, focus.json, README.md, tests/test_summary_ledger.py]

## Approach
- After the focus-off summary notice, `omarchy-menu-select` with Helpful and Not helpful. Exit 1 (cancel) does not append. Then optional zenity `--entry` for a note. Do not copy `prompt_reason()` as the helpful/not-helpful control.
- Append one JSONL object `{at, helpful, note}` at `~/.local/state/omarchy/focus-summary-ledger.jsonl`. Notify on write failure. Keep the summary already shown (R10).
- `.3` already includes the ledger file in the next prompt (last 20 lines / 4 KiB). Confirm that pass-through reads new lines. `.2` shipped with an empty-ledger stub.
- README. New Agent summaries section between Use and Commands. State R13 consent, default vs override, open-table picker (`claude`), gated-closed ids including `omp`, focus-off one summary, ledger, and fallback to the mute grouped count. Document `agent-summaries` and `summary-agent`. Extend the `focus.json` example with the two new keys defaulting off / null.
- Do not add a history screen or per-app toggles.

## Investigation targets
**Required** (read before coding):
- `distractions:200-221` — zenity `--entry` cancel / missing-binary pattern (note only)
- `README.md:43-66` — Use table, `focus.json` example, Commands list
- `.flow/memory/declined/notification-extra-ui.md` — no history / per-app toggles

**Optional** (reference as needed):
- `distractions:57-61` — `log_path()` mkdir-parents pattern for the ledger file
- `manifest.json` — leave bar-widget description unless the README change requires a one-line description bump

## Key context
- Helpful and not-helpful must remain distinguishable from cancel. A two-button zenity question that returns nonzero for both Not helpful and cancel is a fail.
- Ledger path is `~/.local/state/omarchy/focus-summary-ledger.jsonl`.

## Acceptance
- [ ] After a shown summary, helpful / not-helpful plus optional note can be stored. Cancel skips the entry. Rejected notes are not written.
- [ ] A failed ledger write notifies. The summary stays. Next parse may lack the new line.
- [ ] The next one-shot prompt includes stored ledger lines (capped).
- [ ] README documents enable, picker, one summary, ledger, and grouped-count fallback. `focus.json` example includes the new keys.
- [ ] `python3 -m py_compile distractions` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` covers helpful, not-helpful, and cancel (no append).

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
