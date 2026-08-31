---
satisfies: [R1, R3, R4, R6, R15, R16]
---

# fn-3-focus-mode-agent-notification-summary.3 Bounded parse, lift XOR, and lift-fail retain

## Description
Run the open one-shot under R15 bounds and choose one catch-up surface after a successful lift (R1 remainder, R3, R4, R6, R15, R16). Do not implement mute, banners, or the grouped-count builder.

**Size:** M
**Files:** `distractions`, `tests/test_summary_parse.py`
**Touches:** [distractions, tests/test_summary_parse.py]

## Approach
- `summarize-session` (started by .2) owns child, debounce, budget, and crash reap. First unseen record starts one open-table one-shot. Prompt is bounded records plus last 20 ledger lines / 4 KiB (empty until .4). Shared spawn. Empty dedicated cwd. Process group. Rlimits from parent spec §Architecture. No yolo flags. Result file mode `0600`, session id, atomic rename.
- Bounds from parent spec §Architecture. One child. 20 s debounce. Max 3 invocations. 40 records. 24 KiB prompt. 64 KiB JSONL. 8 KiB captured stdout. 8 KiB stored result. 800-byte notify body. 60 s then kill. Zero retries. One final parse at `summarize-finish` if unseen records remain and budget remains.
- `notify()` returns success after `omarchy-notification-send` or a successful `notify-send` fallback. Both fail means display failure.
- Focus-off state machine. Valid reason. `summarize-finish`. Lift mute. Lift fail → notify, retain counts / ping-text / result / session id, no XOR, no count-clear (R16). Lift ok + non-empty summary + notify ok → one `notify()` at 12000 ms, then `clear_counts()`. Any other lift-ok outcome → `show_grouped_notice()` (R4, R6). When summaries are off, do not change mute's lift-then-notice order. `focus-off` argv/stdin uses the same chain.
- Extract `show_grouped_notice()` / `clear_counts()` / `lift_notification_block()` if mute inlined them.

## Investigation targets
**Required** (read before coding):
- `distractions:37-44` — `notify()` must return success/failure
- `distractions:187-198` — `disable_focus()` lift-then-notice to wrap
- `distractions:237-260` — flock / pidfile reap pattern
- `distractions:280-284` — `focus-off` argv/stdin path
- Parent spec §Architecture bounds, XOR, and R16

**Optional** (reference as needed):
- Planned mute task `.2` on `fn-2-focus-mode-distraction-notification` — count file and lift-then-notice to extract, not replace
- `BarWidget.qml:26-31` — bar Process skip is not the session flock

## Key context
- `enable_focus()` after lift-fail keeps retained catch-up. New toasts may append. Next successful lift XORs retained plus new state.
- Reason cancel leaves the session running. No XOR.
- Hook order. `summarize-finish`, mute lift, XOR, then network lift if present.

## Acceptance
- [ ] First unseen ping while the session is up starts one background one-shot under R15 bounds. Failure notifies at focus-off (R1).
- [ ] Focus-off shows one summary on success, not each ping (R3). Counts clear only after `notify()` returns success.
- [ ] Off / no usable agent / empty ping-text leaves grouped-count behavior unchanged, including nonempty mute counts (R4).
- [ ] Invoke, timeout, empty stdout, over-limit output, or display failure still calls `show_grouped_notice()` after a successful lift (R6).
- [ ] Lift failure retains counts, ping-text, and result. No summary. No grouped notice. No count-clear. Next successful lift retries XOR (R16).
- [ ] Replacement parses obey debounce, one child, 3 invocations, byte caps, rlimits, 60 s kill, and one optional final parse.
- [ ] `python3 -m py_compile distractions` passes.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` covers bounds, timeout/kill, stdout cap, stale-session reject, XOR fallback, lift-fail retain, notify primary-fail/fallback-ok, and total display failure.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
