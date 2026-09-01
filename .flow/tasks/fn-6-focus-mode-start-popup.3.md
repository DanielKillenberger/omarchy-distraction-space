---
satisfies: [R3, R4]
---
# fn-6-focus-mode-start-popup.3 Closing window hosts shipped summary

## Description
After focus is off, show one configurable closing window that hosts the shipped fn-3 summary, optional purpose and self-eval, and helpful / not-helpful (R3, remaining R4). Docs land here.

**Size:** M
**Files:** distractions, README.md, manifest.json, focus.json, tests/test_summary_session.py, tests/test_summary_parse.py
**Touches:** [distractions, README.md, manifest.json, focus.json, tests/test_summary_session.py, tests/test_summary_parse.py, tests/test_summary_ledger.py, BarWidget.qml]

### Approach
- Invoke the closing window from `_disable_focus_locked` after focus is off, including when `apply_summary_xor` is skipped because mute lift failed. Purpose/eval still show. The summary pane is empty on that skip. Do not rebuild the parser, do not add an importance field, and do not change ledger JSON shape.
- Fill the summary pane from `read_summary_result` only when host conditions hold: summaries on, usable agent, parse did not fail, and `result.session_id` equals control session id and `recap_pending.session_id`. Purpose pane uses `recap_pending.purpose`. Non-empty stripped `text` shows "Here's what you missed" plus that text. Empty stripped `text` shows "You didn't miss anything". Both skip `notify("Focus summary")`, `collect_summary_feedback`, and grouped notice.
- After a **hosted** summary pane returns, including dismiss, mark recap consumed, delete recap_pending, `clear_counts()`, and delete the result file exactly once.
- A lift-fail purpose/eval-only window still consumes recap_pending and does not clear counts or delete the result.
- Parse-failed keeps today's "Could not summarize" notify plus grouped notice. Summaries-off and other non-host paths keep grouped notice.
- `session_close_ui` false skips the window. A hostable summary then uses today's Focus-summary notify plus `collect_summary_feedback`.
- A later XOR retry after recap was consumed uses today's notify/grouped, never a second window.
- Lift-fail disable still shows purpose/eval from recap_pending when those slots are on. Grouped catch-up stays on summaries-off and XOR-grouped paths. Keep the "Focus mode off" toast.
- One helper-owned GTK close dialog (PyGObject). Helpful / Not helpful / Dismiss all read current fields (purpose display, self-eval, optional note). Map Helpful/Not helpful to `append_ledger_entry`. Do not use zenity extra-buttons. Do not call `menu_select` / `collect_summary_feedback` on this path. Tests inject this dialog function.
- Purpose pane follows `session_close_purpose`. Self-eval follows `session_close_eval` and is skippable. Append a given self-eval to the disable log. Dismiss skips remaining eval / helpful; focus stays off.
- `session_close_ui` false skips the window. Purpose/eval off never hides a shipped summary. If the window has no remaining slots, the summary may use today's notification. Window on with every slot off and summaries off shows nothing extra.
- Lift-fail XOR skip still allows purpose / eval when those slots are on. Grouped catch-up stays on summaries-off and XOR-grouped paths. Keep the "Focus mode off" toast.
- Update README on/off paragraphs, focus.json example, Agent summaries, and both manifest descriptions. Tooltip may mention the start dialog. Icon stays the eye.

### Investigation targets
**Required** (read before coding):
- `distractions:3036-3062`  - `apply_summary_xor` notify plus `collect_summary_feedback`
- `distractions:2827-2846`  - three-state helpful plus `prompt_ledger_note`
- `distractions:2798-2824`  - `append_ledger_entry`
- `distractions:3949-3993`  - post-disable XOR / grouped / off toast
- `tests/test_summary_parse.py:411-442`  - XOR summary vs grouped assertions
- `distractions:3239`  - `clear_counts` after successful host

**Optional:**
- `README.md:84-118`  - on/off copy and Agent summaries
- `manifest.json:8` / `manifest.json:21`  - plugin descriptions
- `.flow/memory/declined/notification-extra-ui.md`  - do not add history or per-app toggles

### Key context
Helpful / not-helpful / dismiss are buttons on the GTK close dialog and must still read the current fields. A zenity extra-button path cannot. Update `tests/test_summary_ledger.py` if the helpful entry point moves. Tooltip may mention the start dialog; icon stays the eye.
## Acceptance
- [ ] After timer or hand-off off, one window can show purpose, hosted summary copy, optional self-eval, and helpful / not-helpful (R3)
- [ ] Non-empty hosted text uses "Here's what you missed"; empty hosted text with parse not failed uses "You didn't miss anything"; parse-failed does not use that empty copy (R3)
- [ ] Hosted summary skips the Focus-summary notification, the extra helpful dialog, and grouped notice (R3)
- [ ] Hosted recap, including dismiss of a hosted summary pane, clears counts and deletes the result exactly once (R3)
- [ ] Lift-fail purpose/eval-only window does not clear counts or delete the result (R3)
- [ ] Lift-fail disable (XOR skipped) still shows the closing window with purpose/eval and an empty summary pane (R3)
- [ ] Recap consumed for a session id blocks a second closing window; XOR retry then uses today's notify or grouped path (R3)
- [ ] `session_close_ui` false uses today's Focus-summary notify plus helpful dialog for a hostable summary (R4)
- [ ] `read_summary_result` / parser / ledger schema are reused; no new parser importance field (R3)
- [ ] Self-eval skip and window dismiss leave focus off
- [ ] Purpose/eval off still shows a shipped summary when summaries are on (R4)
- [ ] Empty remaining slots may fall back to today's summary notification (R4)
- [ ] Grouped catch-up still runs when summaries are off
- [ ] README, focus.json example, and manifest describe start popup, timer, and closing window
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` is green
- [ ] `python3 -m py_compile distractions` is green
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
