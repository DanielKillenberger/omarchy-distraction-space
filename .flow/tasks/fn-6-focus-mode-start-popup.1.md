---
satisfies: [R1, R4]
---
# fn-6-focus-mode-start-popup.1 Start popup and session UI flags

## Description
Gate production focus-on with the start dialog and land the session UI flags in the existing focus settings (R1, R4). Split from the timer and close window because those share disable/XOR and this task must prove the on-path gate first.

**Size:** M
**Files:** distractions, focus.json, tests/test_focus_start.py, tests/test_summary_agent.py
**Touches:** [distractions, focus.json, tests/test_focus_start.py, tests/test_summary_agent.py]

### Approach
- Collect purpose and minutes on `request_focus_toggle` (off branch) and `focus-on` before calling `enable_focus()`. Leave `enable_focus()` as the apply step so `tests/test_summary_session.py` can keep calling it.
- One helper-owned GTK start dialog (PyGObject). Minutes control opens at 25. Confirm returns purpose plus minutes. Dismiss returns without enable. Do not use zenity `--forms`. Do not use two sequential `--entry` calls. Tests inject this dialog function.
- Collapse purpose whitespace the way `disable_focus()` does. Empty after collapse, out-of-range minutes, or dismiss returns without calling enable.
- When `session_start_ui` is false, skip the dialog and enable with 25 minutes. When start UI is on and `session_start_purpose` is false, minutes only.
- Persist **active** (purpose, ISO wall-clock deadline, session id from `enable_focus()` / `prepare_summary_session`) after every successful start via `write_private_atomic` (0600). Persist **recap_pending** (purpose, session id) only when none exists for that session id. Do not call `prepare_summary_session(force_new=True)` during lift-fail. A start that reuses the session id must not overwrite recap_pending. The listener tick is fn-6.2. A corrupt or truncated record is treated as absent.
- Extend `load_config` / `write_focus_config` with `session_start_ui`, `session_start_purpose`, `session_close_ui`, `session_close_purpose`, `session_close_eval` (JSON booleans, default true). Reject with `isinstance(value, bool)` so integers `0`/`1`, strings, and null fail. Do not copy the `agent_summaries not in (True, False)` check.
- One helper picker command beside `cmd_agent_summaries` for those flags. `update_focus_config` false keeps the previous file.
- Already-on `focus-on` stays a no-op with no dialog.

### Investigation targets
**Required** (read before coding):
- `distractions:3918-3933`  - enable apply to leave untouched as the on-hook
- `distractions:3996-4027`  - zenity `--entry` and `request_focus_toggle` off-to-on
- `distractions:4123-4127`  - `focus` / `focus-on` argv
- `distractions:266-328`  - `load_config` / `write_focus_config` / `update_focus_config`
- `distractions:390-422`  - `menu_select` picker pattern
- `tests/test_edit_list.py:21-31`  - injected zenity
- `distractions:2428`  - `prepare_summary_session` session id to store after enable

**Optional:**
- `tests/test_summary_agent.py:28-169`  - config defaults and reject-keeps-previous
- `BarWidget.qml:26-31`  - bar left-click runs `focus` (no QML change required here)

### Key context
Existing session tests call `enable_focus()` directly. Do not put the dialog inside that function.
## Acceptance
- [ ] `focus` / `focus-on` with injected dialog confirm (non-empty purpose, minutes opening at 25) turns focus on and stores active purpose, wall deadline, and session id, and writes recap_pending when none exists for that session id (R1)
- [ ] A second start that reuses the same session id (lift-fail pending) updates active and does not overwrite recap_pending
- [ ] Dismiss, whitespace-only purpose, or minutes 0 / 241 leave focus off (R1)
- [ ] Minutes field starts at 25; 1 and 240 are accepted
- [ ] `session_start_ui` false skips the dialog and enables with 25 minutes (R4)
- [ ] `session_start_purpose` false with start UI on collects minutes only (R4)
- [ ] Already-on `focus-on` does not open the dialog
- [ ] Missing keys default true; `0`, `1`, `"true"`, and null writes are rejected and the previous file remains (R4)
- [ ] Stored purpose/deadline file is mode 0600 after a successful confirm; a truncated file is treated as absent
- [ ] Session picker cancel leaves previous flags
- [ ] `python3 -m unittest tests.test_focus_start tests.test_summary_agent tests.test_summary_session` is green
- [ ] `python3 -m py_compile distractions` is green
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
