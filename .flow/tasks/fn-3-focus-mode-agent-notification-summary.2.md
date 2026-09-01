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
- Add child `PingCapture.qml` instantiated by `NotificationFilter.qml`. In the incoming-toast handler, send bounded `{app,title,body,at}` JSON on stdin to a silent `distractions capture-ping` helper before mute dismisses or deletes history. The helper takes the session flock, rejects stale/nonfocused sessions, allocates `seq` from durable `next_seq`, appends complete `{seq,app,title,body,at}` JSONL, and trims oldest records under that same lock without renumbering survivors. QML never reads or rewrites the JSONL. Do not dismiss. Do not increment mute counts. Membership is mute's identity map only. If that map is absent, write nothing.
- Focus-on takes the session lock, writes a new session id/control state and reaps leftover agent children before flipping the focus flag unless a lift-fail catch-up is pending. After mute apply succeeds it publishes a current session-ready marker. The service starts `Process { command: [helper, "summarize-session"] }` only from that marker, not from the focus flag alone.
- On an unexpected exit while focus is still on, start `summarize-session --restart` at most twice, after 1 s and 4 s. That Python entry path takes the session flock and atomically increments `parser_restarts` before initialization, refusing values above two. The service reads but never writes the counter. On Quickshell startup, an uncleared parser-active marker for a current ready session selects the same restart path. A clean finish, disable, or finish-request marker clears active/ready state and never restarts.
- `summarize-session` is a flocked long-lived singleton (same flock style as `listen()` at `distractions:244-250`). It watches records with a session-monotonic `seq`. A mode-`0600` session control file owns durable `next_seq`, `invocations`, `last_consumed_seq`, `parser_restarts`, parser-active/session-ready state, and finish-request state. It prints nothing about ping-text or the result. `listen()` does not own it.
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
- [ ] Member toasts while summaries are on call silent `capture-ping` before dismiss. It assigns durable monotonic `seq`, appends and trims under one flock, never renumbers survivors, and leaves mute counts unchanged. QML does not mutate JSONL directly.
- [ ] Focus-on prepares the new session before the focus flag, publishes ready only after mute apply, and starts one `summarize-session` Process from ready state. An immediate service reaction binds the new session. First JSONL record is visible without a parser-kick subcommand.
- [ ] Unexpected exits use only two durable 1 s / 4 s `--restart` entries. Python alone increments the counter under lock; service/Quickshell restart cannot reset or double-count it. Clean finish/disable does not restart.
- [ ] No plugin UI or CLI reads the running parse, ping-text, or result while focus is on (R2). Files are `0600` and session-bound.
- [ ] Identity map miss writes no ping-text. Session is empty for later R4.
- [ ] `python3 -m py_compile distractions` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` covers locked capture append/trim, monotonic `seq` across trimming and Quickshell restart, stale capture rejection, focus-on ordering/new-session binding, durable restart counter values and cap/backoff across Quickshell restart, clean-exit no-restart, pending-catch-up no-reset, mid-session disable discard, and no CLI dump while focus is on.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
