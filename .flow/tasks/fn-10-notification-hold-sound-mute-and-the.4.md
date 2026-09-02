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
Added `ds/summary.py` and wired the "While you were away" notice onto every hold boundary. `resolve_command` maps `summary.command`: `auto` takes `claude -p --output-format text` when `claude` is on PATH, else `grok -p`, else the grouped count; `off` never asks; an argv array runs as given. The prompt (one or two second-person sentences on whether anything needs attention, then the `held.jsonl` records as JSON lines) goes in on stdin through a temp file; stdout and stderr are read through pipes capped at 64 KiB and 4 KiB and the child is killed at `summary.timeout_seconds`; the reply is collapsed to one line and clipped to 800 bytes. A non-zero exit, a timeout, an empty reply, or `off` falls back to `Telegram 2 · Discord 1` (most held first). Zero records show nothing.

Ownership rule that came out of review: whoever marks a boundary claims the records. `summary.take()` renames `held.jsonl` away (the claim) before reading, so a failed claim leaves the file and shows nothing, a second boundary during a slow agent call has nothing to repeat, and pings held meanwhile wait. `distractions unlock` claims, hands `DS_HELD` counts to its hook, and shows the notice itself (the command returns after it); the listener claims on a lock expiry (hook `unlock` with counts) and on space entry (hook `enter` with counts), running the command on a thread so the select loop never stalls. `status --json` now carries `hold`, `held`, and `notification_hold` from the last listener write (`tests/test_status.py` pins the ten keys). `BarWidget.qml` shows the held total after the glyph, widens the slot for it, stops dimming while pings wait, and names the count in the tooltip. README: the hold, sound mute, and summary sections replace "What fn-10 adds later"; setup documents the clone step; the state-file table gains `held.jsonl`, `muted.json`, `clone.json` and the three `state.json` keys; hooks and CLI rows updated.

Edits outside the declared Files, each named here: `ds/state.py` and `tests/test_status.py` (conductor-authorized status keys); `ds/lock.py` (`unlock` claims records for `DS_HELD`, and per the review fix also shows the notice: the smallest design in which counts and notice come from one atomic claim and a lock ended between listener ticks still summarizes); `tests/test_hold.py` (two lines: its listener fixture sets `summary.command` to `off`, since with `auto` the suite would have invoked the person's real `claude`, and its on-space assertion now expects the two records consumed at entry, the behaviour R5 declares, with the on-space ping still not recorded). No dispatcher change: no new verb was needed.

Tests: `tests/test_summary.py` covers the resolution order, prompt on stdin with the records, custom argv, the 800-byte clip and the read cap, the fallback table (exit 1, timeout, empty, off, missing), a flooding agent, `take()` including an unclaimable file, zero records, the unlock command's hook counts and notice, and two listener passes (space entry with the agent line, hook counts, cleared file, no repeat; manual unlock then expiry with the count fallback). Confirmed red first (module missing, status key set). Full suite: 222 tests OK at 8d4aaaf (`PATH=/usr/bin:$PATH python3 -m unittest discover -s tests`), GREEN_RECEIPT .flow/tmp/green-receipts/8d4aaafe-unittest.json.

Live check (`distractions setup`, a held Telegram or Chromium web-app ping producing no banner and a `held.jsonl` line, the "While you were away" notice on entering the space, the bar count): deferred to the conductor, to be performed with the user after merge; nothing in this worktree touched the live shell, the bus, PulseAudio, `~/.config`, or a real agent CLI. The QML change could not be rendered here; the live check covers the bar.

Follow-ups noted, not built: a manual `unlock` blocks for up to `summary.timeout_seconds` while an agent answers (the bar button is non-interactive meanwhile); a detached notice would need a verb the spec does not name. A daemon-thread notice in the listener is dropped on listener exit.

baseline: green via handoff (verified at 206e13e by fn-10-notification-hold-sound-mute-and-the.3; 214 tests)
gate: unittest full suite 222 OK at 8d4aaaf; GREEN_RECEIPT .flow/tmp/green-receipts/8d4aaafe-unittest.json
stage: impl-review - ran [round 1 NEEDS_WORK (P2: manual-unlock counts and notice from separate reads; unbounded capture_output; unlink-after-read could repeat a notice) -> fixed in 8d4aaaf -> round 2 SHIP], backend cursor, model gpt-5.6-sol-high
memory: bug/runtime-errors/held-record-consumption-split-across-2026-09-02 captured

### Live check (conductor, 2026-09-02, this machine)

- `distractions setup` on the branch cloned `daniel.notifications` and applied the patch; `clone.json` recorded the first-party hashes. The rescan reloaded the clone's files but the running service still answered "Function not found." until `omarchy restart shell`; setup now probes and restarts (commit after 74f963a). After the restart `silencedSenders` answered `[]`.
- First push reported `notification_hold: unavailable`: `qs ipc call` splits a `[...]` argument, so `setSilencedSenders '<json>'` never arrived intact. Fixed in 74f963a (one `silence`/`unsilence` call per key). Afterwards the shell list held all 18 plugin keys and status read `notification_hold: on`, `hold: true` off the space.
- Five `notify-send -a "Telegram Desktop"` pings while off the space: each appended one line to `held.jsonl` and raised `state.json.held` (`{"Telegram": 1}` then `2`). The user confirmed no banner appeared for the last one and that the bar eye showed the held count of 1.
- Entering the space consumed the records and the user saw the "While you were away" notification; it arrived late because `summary.command` is `auto` and `claude -p` ran up to the 60 s timeout.
- Not exercised live: sound mute (no listed app was playing audio).

stage: impl-review - ran (model: gpt-5.6-sol-high via cursor backend; 2 rounds, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 1b9060c33bd4db83c93fb28ee8a9876b364dc54d, 8d4aaafecf195be7fb5370eb92c4adfe246b7707, 7424c94b5eaa739b68b8b80336edc76b1004891f, 74f963a, fbde108
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (222 tests OK at 8d4aaaf), PATH=/usr/bin:$PATH python3 -m unittest tests.test_summary tests.test_status tests.test_lock tests.test_hold tests.test_enter (60 tests OK), python3 -m unittest discover -s tests
- PRs: