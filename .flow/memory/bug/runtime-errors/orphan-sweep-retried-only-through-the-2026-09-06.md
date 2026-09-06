---
title: Orphan sweep retried only through the owned record; a failed list with nothing o
date: "2026-09-06"
track: bug
category: runtime-errors
module: ds/hold.py
tags: [hold, mute, pactl, retry, lifecycle, review]
problem_type: runtime-error
symptoms: a pactl list failure at listener start or hold end left an orphaned slice mute stuck until the next hold transition
root_cause: "the sweep's retry lived in tick's owned-record condition, so an empty record meant no retry at all"
resolution_type: fix
---

## Problem
The orphaned-mute sweep in `Mute.release()` (ds/hold.py) listed the streams on every release and unmuted every muted slice stream, record or no record. When the `pactl list` itself failed with nothing owned, `release()` restored an empty `owned`, `tick()` had nothing to retry, and later hold-off `sync()` calls skipped release because the start sweep had already run. A transient audio-server outage at listener start or hold end left the orphan muted until the next hold transition. All three review draws (correctness, contracts, integration) reproduced it.

## What Didn't Work
Deliberately leaving a failed sweep to the next release to avoid a `pactl` call every 16 seconds during an outage. R1's "leaves the stream for the next retry" is the retry contract; a hold transition that may be hours away is not a retry. The retry cost is the one an owned record already pays, and `_fail` logs once per streak, so the saving was not worth the stuck stream.

## Solution
`Mute.sweep` marks a release whose listing failed (ds/hold.py `Mute.release`: `self.sweep = streams is None`), `tick()` retries while `self.owned or self.sweep`, and `retry_at` is stamped for either. A successful listing clears it, so a listed sweep is never owed twice. `test_failed_listing_without_a_record_retries_the_sweep_from_tick` was confirmed red before the flag and green after.

## Prevention
When a release/cleanup step gains a new obligation (here: the slice sweep), walk every failure of that step and ask what retries it. An obligation retried only through state that a different obligation owns (`owned` for the records) is lost the moment that state is empty; give the new obligation its own retry marker or fold it into the existing one explicitly. A focused test with the failure injected and nothing else owed catches it.
