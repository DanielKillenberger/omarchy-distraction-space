---
title: Mute release forgot streams whose unmute failed and never retried a failed list
date: "2026-09-02"
track: bug
category: runtime-errors
module: ds/hold.py
tags: [hold, mute, pactl, lifecycle, review]
problem_type: runtime-error
symptoms: a failed pactl unmute left a stream muted with muted.json deleted; a failed list kept records nobody retried
root_cause: release was one-shot and the listener's edge-triggered sync_hold was assumed to retry
resolution_type: fix
---

## Problem
Review of the sound mute in `ds/hold.py` found that a stream release could fail silently and never recover. `Mute.release()` unmuted the recorded indexes and then deleted `muted.json` whatever each `pactl set-sink-input-mute` returned, so one failed unmute left the stream muted with no record of it. When the `pactl list` itself failed the records were kept, but nothing retried them: the listener's `sync_hold` short-circuits while hold state and keys are unchanged, so the retained ownership sat in the file until the next hold transition.

## What Didn't Work
Treating release as a one-shot: list, unmute what matches, clear the file. The listener's transition-driven sync was assumed to be a retry path, but it is deliberately edge-triggered.

## Solution
`Mute.release()` keeps the identity of every stream whose listing or unmute failed and stamps `retry_at`; `Mute.tick()` (already called once a second by the listener) retries the release while hold is off and something is still owned, spaced by `RELEASE_RETRY` (16 s); `muted.json` clears only once nothing is left (ds/hold.py `Mute.release`, `Mute.tick`). The fake `pactl` gained `DS_PACTL_STUCK` so one index can refuse to unmute, and two focused tests drive both recovery paths with synthetic `now` values.

## Prevention
Any lifecycle that hands external state back on an edge (hold off, exit) needs an answer to "what if the hand-back fails?": keep the record and put the retry on the loop's existing tick rather than on the next edge. When a `sync(..., now=)` seam exists for tests, forward `now` into every call it makes — a nested call that reads the real clock makes a synthetic-time test pass or fail by accident.
