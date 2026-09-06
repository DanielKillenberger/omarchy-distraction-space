---
title: Shared cleanup method deleted the hold key on the missing-pactl path while the h
date: "2026-09-06"
track: bug
category: runtime-errors
module: ds/hold.py
tags: [hold, mute, wireplumber, lifecycle, review]
problem_type: runtime-error
symptoms: sync(True) with pactl missing set the hold key and release() deleted it at once; the hook stopped muting
root_cause: release() serves both hold-end and reactive-backend-failed; the key deletion was hung on it
resolution_type: fix
---

## Problem
`Mute.release()` is reached from two callers with different meanings: `sync(False)` when the hold ends, and `sync(True)` when pactl has gone missing and the reactive side is being released while the hold is still on. Adding the hold-key deletion to `release()` therefore deleted the key on the missing-pactl path, disabling the working WirePlumber hook exactly when the reactive fallback had failed. Every review draw reproduced it as `[hold(True), hold(False)]`.

## What Didn't Work
Treating `release()` as "the hold is over": it is only "stop muting reactively".

## Solution
`release()` never touches the key; the key follows the desired hold state in `sync(on)` and is deleted in the new `Mute.stop()` the listener calls at shutdown (ds/hold.py, ds/listener.py:189). Regression: `tests/test_audio.py::test_a_missing_pactl_never_deletes_an_active_hold_key`.

## Prevention
Before hanging a new state change on an existing cleanup method, list its callers and the state each one is in; a method shared by "the thing ended" and "the backend failed" cannot own a flag that means "the thing is on". A regression test that drives the failure path with the state fake in place catches it.
