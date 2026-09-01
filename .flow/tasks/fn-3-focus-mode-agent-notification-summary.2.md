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
- Add child `PingCapture.qml` instantiated by `NotificationFilter.qml`. In the incoming-toast handler, send bounded `{app,title,body,at}` JSON on stdin to a silent `distractions capture-ping` helper before mute dismisses or deletes history. The helper takes short-held `summary-state.lock` with a 250 ms bounded blocking timeout, rejects stale/nonfocused sessions, allocates `seq` from durable `next_seq`, appends complete `{seq,app,title,body,at}` JSONL, and trims oldest records under that same lock without renumbering survivors. Lock timeout is an explicit append failure. QML never reads or rewrites the JSONL. Do not dismiss. Do not increment mute counts. Membership is mute's identity map only. If that map is absent, write nothing.
- Focus-on briefly takes `summary-state.lock`, writes new session/control state, releases it, and reaps leftover agent children before flipping the focus flag unless a lift-fail catch-up is pending. After mute apply succeeds it publishes a current session-ready marker under that short lock. A 250 ms QML timer observes ready/session id and starts `Process { command: [helper, "summarize-session"] }` within 500 ms only from that marker, not from the focus flag alone.
- On an unexpected exit while focus is still on, immediately start `summarize-session --restart`. That Python entry takes dedicated lifetime `summarize-session.lock`, briefly takes `summary-state.lock`, atomically increments `parser_restarts`, refuses values above two, and sleeps 1 s or 4 s according to the reserved restart number before initialization. The service neither increments nor sleeps. On Quickshell startup, an uncleared parser-active marker for a current ready session selects the same restart path. A clean finish, disable, or finish-request marker clears active/ready state and never restarts.
- `summarize-session` holds `summarize-session.lock` for its lifetime as a nonblocking singleton guard (same style as `listen()` at `distractions:244-250`) but never holds `summary-state.lock` beyond short state mutations. It watches records with a session-monotonic `seq`. A mode-`0600` session control file owns durable `next_seq`, `invocations`, `last_consumed_seq`, `parser_restarts`, parser-active/session-ready state, and finish-request state. It prints nothing about ping-text or the result. `listen()` does not own it.
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
- [ ] Member toasts while summaries are on call silent `capture-ping` before dismiss. It assigns durable monotonic `seq`, appends and trims under the short lock, times out after 250 ms, never renumbers survivors, and leaves mute counts unchanged. Capture still appends while `summarize-session` holds its separate lifetime guard. QML does not mutate JSONL directly.
- [ ] Focus-on prepares the new session before the focus flag, publishes ready only after mute apply, and the 250 ms service timer starts one `summarize-session` Process from ready state within 500 ms. The process binds the new session. First JSONL record is visible without a parser-kick subcommand.
- [ ] Unexpected exits use only two durable `--restart` entries. Python alone increments the counter and owns testable 1 s / 4 s sleeps; service/Quickshell restart cannot reset or double-count it. Clean finish/disable does not restart.
- [ ] No plugin UI or CLI reads the running parse, ping-text, or result while focus is on (R2). Files are `0600` and session-bound.
- [ ] Identity map miss writes no ping-text. Session is empty for later R4.
- [ ] `python3 -m py_compile distractions` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` covers separate singleton/state locks, capture while parser guard is held, 250 ms timeout, locked append/trim, monotonic `seq`, stale capture rejection, focus-on ordering/new-session binding, durable restart counter values and mocked 1 s / 4 s sleeps, cap across Quickshell restart, clean-exit no-restart, pending-catch-up no-reset, mid-session disable discard, and no CLI dump while focus is on.
- [ ] Manual Quickshell service smoke observes a newly published ready marker within 500 ms, starts exactly one parser, and selects `--restart` once after a forced unexpected exit; Python tests cover the backoff delay and cap.

## Done summary
# fn-3.2 done

One Quickshell service still owns mute. Capture is a child. Session prepare happens before the focus flag. Mute always applies on focus-on, including when summaries are off. Ready, capture, and summarize-session start only after mute apply succeeds for this session and summaries are enabled. Mid-session enable re-applies mute before publishing ready. Later listen/focus retries share the same refresh gate.

Host impl-review (gpt-5.6-sol-high) SHIP. Lineage #13 closed. Picker remains claude+grok only.

stage: impl-review - ran (model: gpt-5.6-sol-high)
baseline: green
focused: tests.test_summary_session 35 OK
## Evidence
- Commits: b34717f31ccbea3e79c5643e92ece27c8709a005, 1a33485b14f6af8dd040c760afe84f2ebe5fe6e8, 6bda85a4898ddf23609b4e73a5a5fb98fb960528, 4d99e20279373b9298a5e68ccf1bba375aa23e5a, dd5d542b7a2a600ac560c0a82be9c557f32fdbe7, f91f5d6aad64c6700debe726f9d92a02a06df079, 771ee833d7ea56aa95de3601dfbc5b6d52ef25e2, f6715231ac112720e83152fc9125e48120f8844f
- Tests: python3 -m py_compile distractions, python3 -m unittest tests.test_summary_session, python3 -m unittest discover -s tests -p 'test_*.py'
- PRs: https://github.com/DanielKillenberger/omarchy-distraction-space/pull/3