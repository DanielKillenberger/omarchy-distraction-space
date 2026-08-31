---
satisfies: [R9, R10]
---
# fn-3-focus-mode-agent-notification-summary.3 Summary ledger and README

## Description
After a shown summary, record helpful / not-helpful plus an optional note, and document the opt-in path (R9, R10). Finalization (README + shipped `focus.json`) lives here, not as a fourth task.

**Size:** S
**Files:** `distractions`, `focus.json`, `README.md`
**Touches:** [distractions, focus.json, README.md]

### Approach
- After the focus-off summary notice, zenity question (helpful / not) then optional entry for a note. Follow `prompt_reason()` cancel-safe returncodes. Cancel or reject does not append. Earlier lines stay (R9).
- Append one JSONL object `{at, helpful, note}` under `~/.local/state/omarchy/`. Notify on write failure. Keep the summary already shown (R10).
- `.2` already includes the ledger file in the next prompt. Confirm that pass-through reads new lines.
- README: new Agent summaries section between Use and Commands. State R13 consent, default vs override, headless-only picker, focus-off one summary, ledger, and fallback to the mute grouped count. Document `agent-summaries` and `summary-agent`. Extend the `focus.json` example with the two new keys defaulting off / null.
- Do not add a history screen or per-app toggles.

### Investigation targets
**Required** (read before coding):
- `distractions:200-221` — zenity `--entry` cancel / missing-binary pattern
- `README.md:43-66` — Use table, `focus.json` example, Commands list
- `.flow/memory/declined/notification-extra-ui.md` — no history / per-app toggles

**Optional** (reference as needed):
- `distractions:57-61` — `log_path()` mkdir-parents pattern for the ledger file
- `manifest.json` — leave bar-widget description unless the README change requires a one-line description bump

### Acceptance
- [ ] After a shown summary, helpful / not-helpful plus optional note can be stored. Rejected notes are not written.
- [ ] A failed ledger write notifies. The summary stays. Next parse may lack the new line.
- [ ] The next one-shot prompt includes stored ledger lines.
- [ ] README documents enable, picker, one summary, ledger, and grouped-count fallback. `focus.json` example includes the new keys.
- [ ] `python3 -m py_compile distractions` passes.

## Acceptance
- [ ] After a shown summary, helpful / not-helpful plus optional note can be stored. Rejected notes are not written.
- [ ] A failed ledger write notifies. The summary stays. Next parse may lack the new line.
- [ ] The next one-shot prompt includes stored ledger lines.
- [ ] README documents enable, picker, one summary, ledger, and grouped-count fallback. `focus.json` example includes the new keys.
- [ ] `python3 -m py_compile distractions` passes.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
