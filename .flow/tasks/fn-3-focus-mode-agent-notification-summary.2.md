---
satisfies: [R1, R2, R3, R4, R6, R14, R15]
---

# fn-3-focus-mode-agent-notification-summary.2 Ping capture, bounded parse, focus-off XOR

## Description
Own ping-text capture, run the offered one-shot under R15 bounds, and show one summary or the mute grouped count (R1, R2, R3, R4, R6, R14, R15). Do not implement mute, banners, or the grouped-count builder.

**Size:** M
**Files:** `distractions`, `PingCapture.qml`, `manifest.json`, `tests/test_summary_parse.py`
**Touches:** [distractions, PingCapture.qml, manifest.json, tests/test_summary_parse.py]

## Approach
- Add plugin service `PingCapture.qml` that observes member toasts while focus is on and `agent_summaries` is true. Append one `{app,title,body,at}` JSONL line this spec owns. Do not dismiss. Do not increment mute counts. Reuse mute's identity map if present. Otherwise match shipped `hypr/windows.lua` apps. Arm `kinds` with `service` in `manifest.json` if missing. Load via `plugins[]` only as needed for the service to run.
- Hook `enable_focus()` after mute apply (when present). Cancel leftover children. Discard unread stdout. First new ping-text record starts one offered one-shot (prompt = bounded records + last 20 ledger lines / 4 KiB). Shared spawn. Empty dedicated cwd. Process group. No yolo flags. Result file mode `0600`, session id, atomic rename, flock like `listen()`.
- Bounds from parent spec §Architecture. One child. 20 s debounce. Max 3 invocations per session. 40 records. 24 KiB. Oldest dropped first. 60 s then kill. One final parse at focus-off if unseen records remain and budget remains.
- No CLI or notify reads ping-text or result while `is_focus()` is true (R2). Delete result on focus-on, focus-off, cancel, and startup recovery.
- Focus-off state machine. Valid reason. Lift mute. Wait/kill. Optional final parse. Success and non-empty summary → one `notify()` at 12000 ms, then `clear_counts()`. Any fail, off, empty ping-text, or unusable agent → `show_grouped_notice()` (R4, R6). Never call lift then wait after the grouped notice has already fired. When summaries are off, do not change mute's lift-then-notice order. Empty ping-text with nonzero counts still shows the grouped notice. `focus-off` argv/stdin uses the same chain.
- Extract `show_grouped_notice()` / `clear_counts()` / `lift_notification_block()` if mute inlined them.

## Investigation targets
**Required** (read before coding):
- `distractions:180-198` — `enable_focus()` / `disable_focus()` hooks
- `distractions:237-260` — flock singleton pattern
- `distractions:280-284` — `focus-off` argv/stdin path
- `BarWidget.qml` — Quickshell imports and Process skip
- Parent spec §Architecture capture contract, bounds, and XOR

**Optional** (reference as needed):
- `hypr/windows.lua` — shipped member apps if mute's map is absent
- `manifest.json` — add `service` kind beside `bar-widget`
- Planned mute task `.2` on branch `fn-2-focus-mode-distraction-notification` — count file and lift-then-notice to wrap, not replace

## Key context
- Planned mute writes `{app-label: int}` only and discards banners. If ping-text is absent, treat it as empty and keep grouped-count catch-up. Do not invent a second mute buffer.
- Ledger prompt text can be empty until .3 lands. .3 appends lines this task already passes through.
- fn-1 may also hook `enable_focus` / `disable_focus`. Insert after mute apply/lift. Do not take over the network block.

## Acceptance
- [ ] Member toasts while summaries are on append ping-text this spec owns. Mute count file is not treated as a text queue.
- [ ] First ping while summaries are on starts one background one-shot under R15 bounds. Failure notifies at focus-off (R1).
- [ ] No plugin UI or CLI reads the running parse, ping-text, or result while focus is on (R2). Result is `0600`, session-bound, and deleted on reset.
- [ ] Focus-off shows one summary on success, not each ping (R3). Counts clear only after that notify succeeds.
- [ ] Off / no usable agent / empty ping-text leaves grouped-count behavior unchanged, including nonempty mute counts (R4).
- [ ] Invoke, timeout, empty stdout (including `agy -p` on a pipe), or display failure still calls `show_grouped_notice()` after lift (R6).
- [ ] Replacement parses obey 20 s debounce, one child, 3 invocations, 40/24KiB caps, 60 s kill, and one optional final parse.
- [ ] `python3 -m py_compile distractions` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` covers bounds, timeout/kill, stale-session reject, XOR fallback, and success count-clear.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
