# Focus-mode start popup

> HTML render lens: [.flow/artifacts/fn-6-focus-mode-start-popup/spec.html](../artifacts/fn-6-focus-mode-start-popup/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "we should have a ui popup when entering focus mode that matches the omarchy style to input the purpose of the focus session and the time after which it will be automatically disabled"
> user (edit cycle 1): "why do we always have to handle that things might not launch or whatever? it should just work consistently? why do we need contingency plan for the ui box not opening?"
> user (interview): purpose is required
> user (interview): duration is minutes
> user (interview): "could have a quick popup showing the reason and an optional self evaluation prompt. Can be completely configured to be turned off"
> user (interview): purpose is log only
> user (interview): default 25 minutes, accepted 1 to 240
> user (interview): purpose popup on by default, configurable off
> user (interview): any non-empty purpose is enough
> user (interview): refuse minutes outside 1 to 240
> user (interview): recap appears after focus is off
> user (interview): toggle lives in the same focus settings
> user (interview): "The brief AI summary could be in the same window saying \"Here's what you missed\" if there was smth important or \"You didn't miss anything\" if there's nothing important. So we have the focus mode UI element that closes with what user missed and the question how well they achieved the purpose. This window should be highly customizable (some config file that agents can just edit)."
> user (interview): "but the ai summary was merged already no?"
> user (interview): one closing window; drop the separate summary notification
> user (interview): "should be fully configurable what appears. By default window appears with AI summary (if enabled). Purpose and eval by default yes, can be disabled."
> user (interview): self-eval is optional
> user (interview): helpful / not-helpful on the same window
> user (interview): turning purpose and eval off never hides a shipped summary
> user (interview): keep as one spec

## Overview

Focus-on today is instant. This spec adds one Omarchy-styled start dialog (purpose plus minutes until auto-off) on the production focus-on paths, a wall-clock session timer the Hyprland listener owns, and one closing window after focus is already off that hosts the shipped fn-3 summary instead of the Focus-summary notification plus follow-up helpful dialog.

## Goal & Context
<!-- scope: business -->

The person using this plugin already has a focus-mode lock, a 50-character reason to leave by hand, and a shipped agent summary at focus-off (fn-3, landed PR #3). Turning focus on is instant today. This spec adds a popup at that moment so the user states the purpose of the session and how many minutes it should last before focus turns off by itself. The popup looks and reads like Omarchy's native dialogs.

Winning is one session. It starts only after purpose and minutes are submitted. It ends when the timer elapses or the user leaves by hand. After focus is off, one configurable closing window shows the purpose, the shipped missed-summary (or that nothing important was missed), an optional how-well-did-you-hit-the-purpose prompt, and helpful / not-helpful for that summary. The parser is not rebuilt. The window hosts what fn-3 already produces.

## Architecture & Data Models
<!-- scope: technical -->

The focus-on path shows one helper-owned GTK dialog with two inputs. Purpose is free text. Duration is minutes until auto-off. The minutes control opens at 25. Confirm starts focus. Dismiss leaves focus off.

Session UI flags live in the existing focus settings file beside `agent_summaries`. Live session fields (purpose text, wall-clock deadline) live in helper state next to the other focus runtime files, not in the settings file, so an agent edit of settings cannot clobber a running deadline.

The long-lived Hyprland listener is the timer owner. It compares the persisted wall-clock deadline to wall time on its existing select tick. It must not run the closing window on that thread. Timer expiry starts a detached helper invocation for disable, the same way the bar launches `focus`.

The disable apply step stays the lock, mute lift, XOR, network lift, and "Focus mode off" toast. Timer expiry reaches that step without the 50-character reason check. Hand-off still goes through the existing reason dialog first.

The closing window is a post-disable host of the shipped result plus optional purpose / self-eval / helpful. Copy selection uses only shipped fields (matching session, parse-failed flag, stripped text empty or not). It does not add a parser payload or rebuild ping capture or ledger schema.

## API Contracts
<!-- scope: technical -->

Settings keys in the existing focus JSON, all booleans, missing key means the default:

- `session_start_ui` default true. When false, skip the start dialog and enable with 25 minutes.
- `session_start_purpose` default true. When false and start UI is on, the start dialog is minutes only.
- `session_close_ui` default true. When false, skip the closing window.
- `session_close_purpose` default true.
- `session_close_eval` default true.
- Summary slot follows existing `agent_summaries`. Hiding purpose or eval never hides a shipped summary. If the window has no remaining slots, the summary may use today's Focus-summary notification.

`write_focus_config` / `update_focus_config` accept a session UI flag only when it is a JSON boolean (Python `isinstance(value, bool)`). Integers `0` and `1`, strings, and null are rejected. A rejected write returns false and leaves the previous file.

Live helper state is two private 0600 records, not one.

- **active**: purpose, wall-clock deadline, and current session id for the session that is on. The timer and the disable log read this.
- **recap_pending**: purpose plus session id for the unconsumed closing window. Written on start only when no recap_pending exists for that session id. A later start that reuses the same session id (fn-3 keeps the id while `lift_fail_pending`) does not overwrite it. Deleted only when recap is consumed.

Do not call `prepare_summary_session(force_new=True)` on start during lift-fail. That would drop the shipped retained catch-up.

Start and close UIs are one helper-owned GTK dialog each (PyGObject), not zenity `--forms` and not two sequential zenity `--entry` calls. Zenity `--forms` cannot prefill minutes to 25. Zenity extra buttons do not return form field values. The start dialog has a minutes control that opens with value 25. The close dialog's Helpful / Not helpful / Dismiss buttons all read the current fields. Tests inject the dialog functions. They do not drive zenity argv.

Required purpose is any text that is non-empty after the same whitespace collapse disable already uses. Integers 1 through 240 inclusive are accepted. Anything else, empty purpose, or dismiss leaves focus off.

Timer-expiry log line includes the purpose and a timer marker. It is not required to be 50 characters. Hand-off log line stays the written reason with the active purpose appended. Both disable paths append purpose.

Hosted summary copy, using only shipped result and control fields:

- Host when agent summaries are on, a usable agent is resolved, parse did not fail, and `result.session_id` equals control session id and `recap_pending.session_id`. The purpose pane uses `recap_pending.purpose`, never a newer active purpose for a different start that reused the id.
- Non-empty stripped result text uses "Here's what you missed" plus that text. Skip the Focus-summary notify and the grouped notice.
- Empty stripped result text uses "You didn't miss anything". Skip the Focus-summary notify and the grouped notice.
- Parse failed keeps today's "Could not summarize" notify plus grouped notice. That path does not use "You didn't miss anything".
- Summaries off, or no hostable result, keeps today's grouped notice. The closing window may still show purpose and eval when `session_close_ui` is true.
- When `session_close_ui` is false, skip the closing window. A hostable summary uses today's Focus-summary notification and the old helpful dialog.
- The recap is consumed when the closing window returns, including dismiss. A later XOR retry for that same session id uses today's notify or grouped path. It does not open a second closing window.
- The closing window runs from disable apply after focus is off, including when mute lift fails and XOR is skipped. Purpose/eval still show. The summary pane is empty on that skip. Recap is then consumed. Later XOR uses today's notify or grouped path.
- After a **hosted** recap (summary pane was shown, including dismiss of that window), clear ping counts and delete the result file exactly once, matching today's successful-summary cleanup. Delete recap_pending then too.
- A lift-fail purpose/eval-only window still consumes recap_pending (no second window) and does **not** clear counts or delete the result. Delayed XOR needs those files for today's notify path.

Helpful, Not helpful, and Dismiss are extra buttons on that same closing dialog. Optional note is a field on the same dialog. The chosen helpful bool plus note call the existing ledger append. This path does not open the agent picker or the old post-notify helpful dialog.

## Edge Cases & Constraints
<!-- scope: technical -->

- Whitespace-only purpose is empty after collapse and refuses start.
- Out-of-range minutes refuse start. The dialog may validate before OK. Dismiss does not re-prompt.
- `focus-on` shows the start dialog when `session_start_ui` is true. Agents who need silent on set that flag false.
- Already-on `focus-on` and listen re-apply stay no-op for the start dialog.
- Listener restart resumes the persisted wall deadline. Monotonic helper time is not the deadline clock.
- If the leave-reason dialog is open when the deadline fires, timer disable wins. A later confirm of an already-off session is a no-op.
- Timer expiry from the listener must not block socket2. Detach the disable helper.
- Lift-fail XOR skip (fn-3) still shows the closing window now for purpose / eval when those slots are on. Purpose comes from recap_pending. The summary pane is empty. Recap is consumed on that window. Later XOR uses today's notify/grouped.
- A later successful lift after recap was consumed uses today's notify/grouped, never a second window.
- Parse-failed is not an empty-text "nothing important" session. Empty hosted text with parse not failed is "You didn't miss anything".
- Summaries off or XOR grouped path keeps today's grouped catch-up. R3 only drops the Focus-summary notification and the extra helpful dialog when the closing window hosts the summary.
- Close-window dismiss skips remaining eval / helpful. Focus stays off.
- Self-eval is skippable. If given, append it to the disable log. Do not add a history store.
- Window on with every slot off and summaries off shows nothing extra.
- Bar icon stays the eye. The 2-second bar status poll is not the session timer.

## Approach

- Reuse zenity width and missing-binary abort only for the existing leave-reason dialog. Start and close UIs are helper-owned GTK dialogs (PyGObject). Minutes opens at 25. Close-dialog extra buttons read current fields. Do not use zenity `--forms`. Do not use two sequential `--entry` boxes.
- Reuse `update_focus_config` (reject keeps previous) and `menu_select` pickers beside `agent-summaries` / `summary-agent`. One helper command toggles the session UI flags.
- Reuse `enable_focus` as the apply step after a successful start collect. Do not put the dialog inside apply, so existing enable tests stay valid.
- Reuse `_disable_focus_locked` for mute, XOR, network lift, and the off toast. Add a timer entry that skips `MIN_REASON` and still appends purpose to the log.
- Invoke the closing window from `_disable_focus_locked` after focus is off. `apply_summary_xor` fills the summary pane when host conditions hold. When the window hosts (including empty-text "You didn't miss anything"), skip the Focus-summary notify, the old helpful follow-up, and grouped notice. Keep the shipped result reader, parser, and ledger append. Keep grouped notice on summaries-off, parse-failed, and other non-host paths.
- Persist **active** (purpose, deadline, session id) after every successful start. Persist **recap_pending** only when none exists for that session id. Private atomic 0600 writer. Check active deadline on the listener select loop. Spawn a detached timer-off command rather than calling zenity on the listen thread. Timer-off disarms the deadline. It does not delete recap_pending.
- Tests inject the start and close dialog functions. They do not drive zenity argv for those UIs. Existing enable apply tests stay on `enable_focus()`.
- README on/off paragraphs, the focus.json example, Agent summaries, and manifest descriptions update in the closing-window task.

## Quick commands

```bash
python3 -m py_compile distractions
python3 -c "import ast; ast.parse(open('distractions').read())"
python3 -m unittest discover -s tests -p 'test_*.py'
```

Injected dialog functions cover start confirm, dismiss, empty purpose, out-of-range minutes, and start-UI-off. Timer tests persist a past wall deadline and assert disable without `MIN_REASON`. Hand-off `disable_focus` with a 50-character reason also appends active purpose to the log. XOR tests distinguish hosted non-empty text, hosted empty text, parse-failed grouped, lift-fail purpose-only (result kept), and summaries-off grouped.

## Boundaries
<!-- scope: business -->

- This spec does not change the existing hand-off path that requires a written reason to turn focus off. [user]
- This spec does not rebuild the agent parser, ping capture, or helpful ledger from fn-3. It hosts the shipped summary. [user]
- Session history, analytics, and a purpose archive screen are out of scope. The config file is settings, not a history screen. [paraphrase]
- Network blocking, notification mute, and the distraction-space app list stay sibling specs. [paraphrase]
- Contingency UI for a popup that did not open, or for apply/timer failure, is out of scope. The popup is expected to work. [paraphrase]
- Notification history and per-app mute toggles stay declined in `.flow/memory/declined/notification-extra-ui.md`. The closing window is not that surface.
- Notification allow-list and urgent bypass stay declined in `.flow/memory/declined/notification-exceptions.md`.
- Last-used minutes are out of scope. The start field always starts at 25.
- A public silent-on flag besides `session_start_ui` is out of scope.

## Decision Context
<!-- scope: both -->

### Motivation
<!-- scope: business -->

Entering focus is instant today. The user asked for a popup at that moment, with purpose and auto-disable duration, in Omarchy's native style. The session then needs a single close: purpose, what was missed, optional self-eval, and summary feedback together. Failure-contingency paths for the dialog not opening were rejected. The popup is specified to work. The 50-character reason stays the way to leave early by hand. Timer expiry skips that reason because the end time was already chosen. The agent summary is already shipped. This spec hosts it. It does not specify a second parser.

### Implementation Tradeoffs
<!-- scope: technical -->

Start collect sits on `focus` / `focus-on`, not inside enable apply, so current session tests keep calling apply without a dialog. `focus-on` still shows the popup when start UI is on so R1 holds for every production on-path. Silent scripted on is `session_start_ui` false.

Deadline is wall clock in helper state because listener `now()` is monotonic and resets on restart. The listener detaches timer-off so socket2 does not stall on zenity.

When purpose UI is off, start is minutes-only (or instant 25 minutes if start UI is off). That is how R4 can hide purpose without breaking R1's start gate for users who left start UI on.

Closing window runs from disable apply after focus is off, including lift-fail. XOR only fills the summary pane. Recap_pending keeps the original purpose for a reused session id. Do not call `prepare_summary_session(force_new=True)` on start during lift-fail.

Closing window replaces the summary notify plus helpful dialog only when it hosts, including empty-text "You didn't miss anything". Host vs grouped vs parse-failed is selected from shipped session match, parse-failed flag, and stripped text. Grouped catch-up stays for summaries-off and parse-failed.

Helpful / not-helpful / dismiss live on that same dialog. The agent picker is not a follow-up on this path.

Session UI booleans use `isinstance(..., bool)` so JSON `0`/`1` cannot sneak through the way `agent_summaries` currently can.

Rejected bigger designs: a second settings app, a history/archive screen, two sequential zenity `--entry` boxes, zenity `--forms` for start or close (cannot prefill minutes or return extra-button field values), driving the timer from the bar's 2-second poll, a new parser importance field, `prepare_summary_session(force_new=True)` during lift-fail, and treating this window as declined extra notification UI.

## Resolved via Project Docs

- `README.md`: Turning focus on is instant. Turning focus off opens a zenity field; the reason must be at least 50 characters. Reasons append to the disable log. The bar control is an eye icon.
- `README.md` Agent summaries: Already shipped. Off until enabled. At focus-off the user sees one summary of important things, then can mark it helpful or not helpful. Grouped-count catch-up still runs when summaries are off or fail.
- `.flow/specs/fn-3-focus-mode-agent-notification-summary.md`: Spec status done. Completion review ship. Landed as git `ca3404c` / PR #3. This spec consumes that summary surface. It does not reopen parser work.

## Resolved via Codebase

- Enable apply is instant. Leave-reason is zenity `--entry` width 520 with missing-zenity notify. `focus-on` currently calls enable apply with no dialog.
- Summary XOR notifies "Focus summary" then `collect_summary_feedback` via `omarchy-menu-select`. Grouped catch-up is the other XOR arm. Result payload is `session_id` plus `text`. Control carries `parse_failed`.
- `update_focus_config` already keeps the previous file on reject. `agent_summaries not in (True, False)` accepts integer 0/1. Session UI flags must not copy that check.
- Private atomic 0600 writer already exists for summary control and ledger.
- Pickers already exist for agent summaries.
- Listener select loop already ticks about once a second and re-applies mute while focused. That is the timer check site. Detach disable from that thread.
- Injected zenity lives in the list-editor tests. Enable/disable session tests call apply with a 50-character reason and never `prompt_reason`.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** Before focus turns on, an Omarchy-styled popup takes a required purpose (any non-empty text) and minutes (field starts at 25, accepted 1 to 240, refuse anything outside that range). Confirm starts focus with those values. Dismiss, empty purpose, or out-of-range minutes leaves focus off. Errors: no other error surface. [user]
- **R2:** When the minutes elapse, focus turns off without the 50-character leave reason. Leaving by hand still requires that reason. Purpose is appended to the disable log. The bar stays an eye. Errors: no error surface beyond R1. [user]
- **R3:** After focus is already off (timer or hand-off), one closing window can show the purpose, the shipped missed-summary ("Here's what you missed" or "You didn't miss anything"), an optional how-well-did-you-hit-the-purpose prompt, and helpful / not-helpful. Self-eval may be skipped. When this window shows the summary, do not also show the Focus summary notification or the extra helpful dialog. This spec hosts the shipped fn-3 summary. It does not rebuild the parser. Errors: no error surface beyond R2. [user]
- **R4:** What appears is fully configurable in the existing focus settings, including a config file agents can edit. Defaults: window on, purpose on, self-eval on, summary if agent summaries are on. Purpose and self-eval can each be turned off. That never hides a shipped summary. If the window has no remaining slots, the summary can use today's notification. A rejected config write leaves the previous settings unchanged. Errors: no error surface beyond R3. [user]

## Early proof point

Task fn-6-focus-mode-start-popup.1 proves the start dialog actually gates production focus-on. An injected dialog dismiss leaves focus off. Confirm with a non-empty purpose and minutes opening at 25 turns it on.

If that gate cannot be one dialog with minutes prefilled to 25, re-evaluate the toolkit before the timer or closing window.

## Requirement coverage

| Req | Description | Task(s) | Gap justification |
|-----|-------------|---------|-------------------|
| R1 | Start popup gates production focus-on | fn-6-focus-mode-start-popup.1 | - |
| R2 | Timer auto-off without leave reason, purpose in log, eye stays | fn-6-focus-mode-start-popup.2 | - |
| R3 | One closing window hosts shipped summary | fn-6-focus-mode-start-popup.3 | - |
| R4 | Session UI flags in focus settings, reject keeps previous | fn-6-focus-mode-start-popup.1, fn-6-focus-mode-start-popup.3 | - |

## References

- Shipped summary XOR and ledger: fn-3, PR #3, `ca3404c`
- Declined history / per-app toggles: `.flow/memory/declined/notification-extra-ui.md`
- Test entry: `python3 -m unittest discover -s tests -p 'test_*.py'`
