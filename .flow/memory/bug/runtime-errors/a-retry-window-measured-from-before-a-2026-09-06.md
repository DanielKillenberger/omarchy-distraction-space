---
title: A retry window measured from before a blocking call is spent before it returns
date: "2026-09-06"
track: bug
category: runtime-errors
module: ds/listener.py
tags: [listener, hold, retry, timing, lifecycle, review]
problem_type: runtime-error
symptoms: a bounded retry window opened before a 10s-timeout push retried nothing; an answered failure reopened an exhausted episode
root_cause: "the clock was sampled before the blocking call, and the episode was ended by any non-transport outcome rather than by a push that got through"
resolution_type: fix
related_to: [bug/runtime-errors/argparse-read-pass-through-browser-2026-09-05, bug/runtime-errors/held-record-consumption-split-across-2026-09-02, bug/runtime-errors/hold-subprocess-launches-let-non-enoent-2026-09-02, bug/runtime-errors/mute-release-forgot-streams-whose-2026-09-02, bug/runtime-errors/resolve-the-source-keep-the-destination-2026-09-05]
---

## Problem
The bounded retry episode added to `_Ctx.sync_hold` for a late `omarchy-shell` was wrong in three ways that a reading of the diff alone did not surface, and all three are the same shape: a window is only as good as the two facts it rests on, when it starts and what ends it.

The window opened at a `time.monotonic()` sampled BEFORE `hold.push()`. One shell call blocks for up to `IPC_TIMEOUT` (10 s) — the same span as the window — so a first push that timed out returned with its deadline already spent and retried nothing: the exact outage the window existed for got zero retries.

The episode was ended by any non-transport outcome rather than by a push that got through, so an answered failure mid-outage cleared the marker and let the next per-period transport failure open a second window during one unbroken unavailable spell. R1 says the per-period push does not reopen an exhausted episode.

The mute sync ran whenever a retry SUCCEEDED, on the reasoning that a recovery is a transition worth one audio scan. The spec had already ruled on it: a short retry re-runs only the shell push. The scan is another blocking call in the tick, delaying publication of the very recovery it followed.

## What Didn't Work
Sampling the clock once at the top of a method that then makes a blocking subprocess call, and treating "the outcome changed" as equivalent to "the outage ended".

## Solution
`ds/listener.py` `sync_hold` keeps the pre-call `now` for scheduling (is this attempt due?) and takes a second reading after `hold.push` returns for recording (when did this failure happen?); the `now=` test seam makes both readings the injected value so synthetic-time tests stay deterministic. `hold_outage_until` is cleared only by a push that got through; an answered failure sets it to the current instant, which both ends the short retries and leaves the outage marked so nothing reopens a window. The mute sync now runs on `force or changed or not short`, with the result deliberately absent from the condition.

## Prevention
When a retry window wraps a call that can block for a comparable span, measure the window from the call's RETURN, and write the test that makes the call consume its own timeout (advance a mocked clock inside the mocked callee) — a synthetic-time test that injects one instant cannot see this class at all.

For any episode/outage state machine, name the one event that closes it and check every other branch leaves it alone: "cleared on anything that is not the failure kind that opened it" reopens the episode through the side door. Sibling lesson to `mute-release-forgot-streams-whose-2026-09-02`: both are lifecycle state that only one specific event may retire.
