---
satisfies: [R5, R8]
---
# fn-10-notification-hold-sound-mute-and-the.4 Agent one-liner with count fallback, bar held count, README

## Description
Implement `ds/summary.py`: `resolve_command(config)` (`auto` → claude / grok / count), prompt builder over `held.jsonl` records, bounded subprocess (stdin prompt, stdout reply, `timeout_seconds`, 800-byte clip), the 'While you were away' notice with the grouped-count fallback, record clearing, `DS_HELD` for the `unlock` and `enter` hooks. Wire into the listener on lock end and space entry. Extend `BarWidget.qml` with the held total and `status --json` with the three new keys. README section for holding, sounds, the summary command, and the clone step of setup. Perform the live check on this machine after `distractions setup`: a held Telegram or Chromium web-app ping produces no banner, appears in `held.jsonl`, and the notice appears on entering the space; record the result in the done summary.

**Files:** `ds/summary.py`, `ds/listener.py`, `BarWidget.qml`, `README.md`, `tests/test_summary.py`.

## Acceptance
- `auto` picks claude, then grok, then count, per PATH; a custom argv gets the prompt on stdin.
- Failure, timeout, empty reply, and `off` all produce the grouped count; zero records produce nothing; records clear after the notice.
- Hooks receive `DS_HELD` with the counts.
- Live check recorded with the observed banner, `held.jsonl` line, and notice.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
