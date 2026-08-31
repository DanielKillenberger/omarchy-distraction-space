---
satisfies: [R5, R7, R8, R11, R12, R13]
---

# fn-3-focus-mode-agent-notification-summary.1 Consent, gated argv table, and picker

## Description
Add plugin consent, default-agent resolve, and the offered-table picker only (R5, R7, R8, R11, R12, R13). Split from capture and parse so a bad argv table fails before QML or focus-off work.

**Size:** M
**Files:** `distractions`, `focus.json`, `tests/test_summary_agent.py`
**Touches:** [distractions, focus.json, tests/test_summary_agent.py]

## Approach
- Extend `load_config()` keys. `agent_summaries` default false. `summary_agent` default null. Reject unknown ids. Atomic temp-file rename. Previous object stays on reject.
- Resolve with `omarchy default agent` when `summary_agent` is null. Empty stdout, or a dropped/omitted id (ori, pi, copilot, opencode, crush), is an unusable empty resolve (R7 then R4 later).
- Closed offered argv from parent spec §Architecture. Exact vectors. Shared spawn later uses empty cwd and no yolo flags. This task can unit-test the mapping without spawning a TUI.
- Do not call `omarchy agent` or `omarchy agent prompt`.
- `distractions agent-summaries` and `distractions summary-agent` call `omarchy-menu-select` (select mode, tempfile handshake). Labels from `setup.default.agent.*`. Offer only offered-table ids plus an Omarchy-default row on the override picker. No checkmarks.
- Early proof. One offered argv returns stdout or a clear failure. No TUI.

## Investigation targets
**Required** (read before coding):
- `distractions:47-54` — `load_config()` JSON load / malformed → `{}`
- `focus.json` — shipped `log` key to keep
- Parent spec §Architecture offered table and dropped/omitted rows

**Optional** (reference as needed):
- `distractions:37-44` — `notify()` for picker-open failure (R12)
- `distractions:200-221` — cancel-safe returncode if menu-select is missing

## Key context
- `omarchy-menu-select` options are `label`, `glyph\tlabel`, or `glyph\tlabel\tsubtext`. Cancel exits 1. Same visual plugin as Setup, not the Setup submenu.
- A plugin override must not write `~/.config/omarchy/defaults/agent`.
- `agy -p` can exit 0 with empty stdout on a non-TTY. Empty stdout is failure.

## Acceptance
- [ ] `agent_summaries` defaults false. Omarchy default agent alone does not enable summaries.
- [ ] Null override reads `omarchy default agent`. Unset, dropped, or omitted default is a resolved empty id.
- [ ] Override picker lists only offered-table ids. ori, pi, copilot, opencode, and crush are not offered. Unknown id is rejected. Previous setting stays.
- [ ] `omarchy-menu-select` failure keeps the previous setting and notifies.
- [ ] No `omarchy agent` / `omarchy agent prompt` spawn in this task.
- [ ] Config write is atomic. Rejected write leaves the previous object.
- [ ] `python3 -m py_compile distractions` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` covers argv mapping, default-false opt-in, and reject-unknown-id.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
