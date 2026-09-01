---
satisfies: [R5, R7, R8, R11, R12, R13]
---

# fn-3-focus-mode-agent-notification-summary.1 Consent, closed argv table, and picker

## Description
Add plugin consent, default-agent resolve, and the owner-pinned `claude` / `grok` picker (R5, R7, R8, R11, R12, R13). Split from capture and parse so a bad required vector fails before QML or focus-off work.

**Size:** M
**Files:** `distractions`, `focus.json`, `tests/test_summary_agent.py`
**Touches:** [distractions, focus.json, tests/test_summary_agent.py]

## Approach
- Extend `load_config()` keys. `agent_summaries` default false. `summary_agent` default null. Accept only null, `claude`, or `grok`; reject every other id. Atomic temp-file rename. Previous object stays on reject.
- Resolve with `omarchy default agent` when `summary_agent` is null. Empty stdout or any id other than `claude` / `grok` is an unusable empty resolve (R7 then R4 later).
- Implement both exact vectors from parent spec §Architecture. Claude is stdin print mode with no tools, one turn, and `$0.25` maximum budget. Grok is official `-p` / `--single` print mode with the prompt as the final argv token, `--tools ""`, one turn, no plan/subagents/memory/web/update, and the pinned `grok-4.6` model.
- For each Grok invocation, create a mode-`0700` private `GROK_HOME`; copy only `auth.json` at `0600` when present or pass `XAI_API_KEY`; write the controlled config from the parent spec with 512 maximum completion tokens, zero inference retries, one allowed model, and all optional execution surfaces off. Set all listed scanner/tool feature environment disables. Delete the private home after exit. Reject Grok for that invocation if the CLI does not honor every required flag/config control.
- Do not call `omarchy agent` or `omarchy agent prompt`.
- `distractions agent-summaries` and `distractions summary-agent` call `omarchy-menu-select` (select mode, tempfile handshake). Labels from `setup.default.agent.*`. Offer exactly `claude` and `grok`, plus an Omarchy-default row on the override picker. No checkmarks.
- Early proof. Both vectors return stdout or a clear failure. No TUI or tools. For Grok, inspect the effective private configuration and prove the 512-token / zero-retry controls before marking the row usable.

## Investigation targets
**Required** (read before coding):
- `distractions:47-54` — `load_config()` JSON load / malformed → `{}`
- `focus.json` — shipped `log` key to keep
- Parent spec §Architecture closed table and Grok private-home contract

**Optional** (reference as needed):
- `distractions:37-44` — `notify()` for picker-open failure (R12)
- `distractions:200-221` — cancel-safe returncode if menu-select is missing

## Key context
- `omarchy-menu-select` options are `label`, `glyph\tlabel`, or `glyph\tlabel\tsubtext`. Cancel exits 1. Same visual plugin as Setup, not the Setup submenu.
- The closed set is exactly Claude and Grok, even if Omarchy adds or permits other agents.
- A plugin override must not write `~/.config/omarchy/defaults/agent`.
- Grok's `-p` consumes the next token. Put every Grok flag before `-p`, then pass the bounded prompt as the final token.

## Acceptance
- [ ] `agent_summaries` defaults false. Omarchy default agent alone does not enable summaries.
- [ ] Null override reads `omarchy default agent`. Unset or any id other than `claude` / `grok` resolves empty.
- [ ] Override picker lists exactly `claude` and `grok`. Every other id is rejected and the previous setting stays.
- [ ] `omarchy-menu-select` failure keeps the previous setting and notifies.
- [ ] No `omarchy agent` / `omarchy agent prompt` spawn in this task.
- [ ] Claude argv is exact. Grok argv puts the prompt after `-p`, uses a private home, removes tools/config discovery, pins `grok-4.6`, caps completion at 512 tokens and retries at zero, and cleans up the private home. Rejected controls fail closed.
- [ ] Config write is atomic. Rejected write leaves the previous object.
- [ ] `python3 -m py_compile distractions` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` covers both argv mappings, Grok private config/environment/cleanup and rejected-control failure, closed-set reject, default-false opt-in, and reject-unknown-id.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
