---
title: Held-record consumption split across unlock command and listener; unbounded agen
date: "2026-09-02"
track: bug
category: runtime-errors
module: ds/summary.py
tags: [summary, hold, listener, subprocess, review]
problem_type: runtime-error
symptoms: manual unlock hook counts and notice came from different reads; a lock ended between ticks gave no notice; capture_output buffered a flooding agent
root_cause: consumption owned by the listener while the unlock command only counted; unlink after read; capture_output=True
resolution_type: fix
related_to: [bug/runtime-errors/hold-subprocess-launches-let-non-enoent-2026-09-02, bug/runtime-errors/mute-release-forgot-streams-whose-2026-09-02]
---

## Problem
Review of `ds/summary.py` and the listener wiring found the held-record lifecycle split across owners. `distractions unlock` counted `held.jsonl` for its hook while the listener later consumed the same file for the notice, so a ping landing between the two showed in the summary but not in `DS_HELD`, and a lock that began and ended between two listener ticks produced no notice at all. `take()` read the file and then unlinked it, so a failed unlink re-summarized the same records at every later boundary. `subprocess.run(capture_output=True)` buffered the agent's whole stdout before the 800-byte clip.

## What Didn't Work
Having the listener detect a manual unlock as a `locked` True to False transition on its one-second tick, with the command computing counts separately before writing `lock.json`.

## Solution
One rule: whoever marks a boundary claims the records. `summary.take()` renames `held.jsonl` away first (the rename is the claim; failure returns nothing and leaves the file), then reads. `lock.unlock()` claims, hands the counts to its hook, and shows the notice itself; the listener claims on expiry and on space entry (ds/summary.py `take`, ds/lock.py `unlock`, ds/listener.py `summarize`). `summary.ask()` feeds the prompt through a temp file and reads stdout and stderr through pipes closed at 64 KiB and 4 KiB caps, killing the child at the deadline.

## Prevention
For a consumable spool shared by two processes, make the claim an atomic rename and put the claim in the same process that emits the event's side effects; a test that chmods the state dir read-only pins the failed-claim path. For any child whose output is only partly used, never `capture_output=True`; cap the read and test with a fake that floods stdout.
