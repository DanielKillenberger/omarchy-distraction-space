---
satisfies: [R5, R7, R8, R11, R12, R13]
---
# fn-3-focus-mode-agent-notification-summary.1 Consent, agent identity, and headless picker

## Description
Add plugin consent and agent identity only (R5, R7, R8, R11, R12, R13). Split from the focus-on parse so the invoke path can fail before mute wiring.

**Size:** M
**Files:** `distractions`, `focus.json`
**Touches:** [distractions, focus.json]

### Approach
- Extend `load_config()` keys: `agent_summaries` default false, `summary_agent` default null. Reject unknown ids and leave the previous object unchanged.
- Resolve the agent with `omarchy default agent` when `summary_agent` is null. Empty stdout means no default (R7 → R4 later).
- Closed argv table from the parent spec Architecture section. Do not call `omarchy agent` or `omarchy agent prompt`.
- `distractions agent-summaries` and `distractions summary-agent` call `omarchy-menu-select` with Setup > Defaults > Agent labels. Offer only closed-table ids plus an Omarchy-default row on the override picker.
- Early proof: one table argv returns stdout or a clear failure, no TUI.

### Investigation targets
**Required** (read before coding):
- `distractions:47-54` — `load_config()` JSON load / malformed → `{}`
- `focus.json` — shipped `log` key to keep
- Parent spec §Architecture closed table and §API Contracts shapes

**Optional** (reference as needed):
- `distractions:200-221` — zenity cancel-safe returncode pattern if menu-select is missing
- `distractions:37-44` — `notify()` for picker-open failure (R12)

### Key context
- `omarchy-menu-select` options are `label`, `glyph\tlabel`, or `glyph\tlabel\tsubtext`. Cancel exits 1.
- A plugin override must not write `~/.config/omarchy/defaults/agent`.
- `agy -p` can exit 0 with empty stdout on a non-TTY. Empty stdout is failure.

### Acceptance
- [ ] `agent_summaries` defaults false. Omarchy default agent alone does not enable summaries.
- [ ] Null override reads `omarchy default agent`. Unset default is a resolved empty id.
- [ ] Override picker lists only closed-table ids. Unknown id is rejected. Previous setting stays.
- [ ] `omarchy-menu-select` failure keeps the previous setting and notifies.
- [ ] No `omarchy agent` / `omarchy agent prompt` spawn in this task.
- [ ] `python3 -m py_compile distractions` passes.

## Acceptance
- [ ] `agent_summaries` defaults false. Omarchy default agent alone does not enable summaries.
- [ ] Null override reads `omarchy default agent`. Unset default is a resolved empty id.
- [ ] Override picker lists only closed-table ids. Unknown id is rejected. Previous setting stays.
- [ ] `omarchy-menu-select` failure keeps the previous setting and notifies.
- [ ] No `omarchy agent` / `omarchy agent prompt` spawn in this task.
- [ ] `python3 -m py_compile distractions` passes.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
