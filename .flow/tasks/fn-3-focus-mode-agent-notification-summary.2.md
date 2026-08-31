---
satisfies: [R1, R2, R14]
---

# fn-3-focus-mode-agent-notification-summary.2 Service composition, capture, and session start

## Description
Compose capture into mute's one Quickshell service, own ping-text JSONL, and start `summarize-session` on focus-on (R1 start, R2, R14). Split from XOR and bounds so the P0 service slot is proven before parse cost work.

**Size:** M
**Files:** `NotificationFilter.qml`, `PingCapture.qml`, `distractions`, `manifest.json`, `tests/test_summary_session.py`
**Touches:** [NotificationFilter.qml, PingCapture.qml, distractions, manifest.json, tests/test_summary_session.py]

## Approach
- Keep one `entryPoints.service`. That path is mute's `NotificationFilter.qml`. Do not point the service at `PingCapture.qml`. If `NotificationFilter.qml` is missing because fn-2 has not landed, stop. Do not invent a second service.
- Add child `PingCapture.qml` instantiated by `NotificationFilter.qml`. In the incoming-toast handler, append `{app,title,body,at}` JSONL before mute dismisses or deletes history. Do not dismiss. Do not increment mute counts. Membership is mute's identity map only. If that map is absent, write nothing.
- After mute apply in `enable_focus()`, if `agent_summaries` is true, the service starts `Process { command: [helper, "summarize-session"] }`. Restart that Process if it exits while focus is still on. `enable_focus()` writes a new session id unless a lift-fail catch-up is pending, and reaps leftover agent children from the pidfile.
- `summarize-session` is a flocked long-lived singleton (same flock style as `listen()` at `distractions:244-250`). It watches the JSONL file. It prints nothing about ping-text or the result. `listen()` does not own it.
- R2. No bar property, `IpcHandler`, or CLI reads ping-text, session stdout, or the result while `is_focus()` is true. Files are mode `0600`. Bind stdout on the QML Process to nowhere the UI can show.
- Mid-session enable starts the Process and arms capture on the next toast. Mid-session disable cancels the child, discards unread stdout, and stops capture. Mute counts stay.

## Investigation targets
**Required** (read before coding):
- `BarWidget.qml:1-53` — Quickshell imports, `Process` skip, `localPath`
- `manifest.json:11-16` — add `service` only if mute has not; never replace mute's entry path
- `distractions:180-184` — `enable_focus()` hook after mute apply
- `distractions:237-260` — flock singleton to copy for the session lock
- Planned mute `NotificationFilter.qml` on `fn-2-focus-mode-distraction-notification` @ `1034c134`

**Optional** (reference as needed):
- `hypr/autostart.lua:3` — `listen` is Hyprland-only and stays that way
- Parent spec §Architecture one-service and parser-start sections

## Key context
- Omarchy third-party services load from `shell.json` `plugins[]`. Mute apply already adds that entry. This task does not replace it.
- Planned mute writes `{app-label: int}` only and discards banners. Ping-text is this spec's file.
- Ledger prompt text can be empty until .4 lands. .3 already includes last-20 / 4 KiB pass-through of whatever exists.

## Acceptance
- [ ] `manifest.json` `entryPoints.service` stays `NotificationFilter.qml`. Capture is a child, not a second service.
- [ ] Member toasts while summaries are on append ping-text this spec owns, before dismiss. Mute count file is not treated as a text queue.
- [ ] Focus-on with summaries on starts one `summarize-session` Process. First JSONL record is visible to that session without a kick subcommand.
- [ ] No plugin UI or CLI reads the running parse, ping-text, or result while focus is on (R2). Files are `0600` and session-bound.
- [ ] Identity map miss writes no ping-text. Session is empty for later R4.
- [ ] `python3 -m py_compile distractions` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` covers session flock, focus-on start, pending-catch-up no-reset, mid-session disable discard, and no CLI dump while focus is on.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
