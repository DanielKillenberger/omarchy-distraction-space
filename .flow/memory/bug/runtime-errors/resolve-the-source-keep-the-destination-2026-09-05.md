---
title: "Resolve the source, keep the destination lexical: path aliases bypassed running "
date: "2026-09-05"
track: bug
category: runtime-errors
module: ds/profile.py
tags: [profile, symlink, resolve, review, running-check]
problem_type: runtime-error
symptoms: a relative or symlinked --from skipped the source browser running check; resolving dst then moved a symlink's target on --replace
root_cause: one side of each path comparison was canonical and the other lexical
resolution_type: fix
related_to: [bug/runtime-errors/held-record-consumption-split-across-2026-09-02, bug/runtime-errors/hold-subprocess-launches-let-non-enoent-2026-09-02, bug/runtime-errors/mute-release-forgot-streams-whose-2026-09-02]
---

## Problem
ds/profile.py derived the source's user-data directory from the lexical `src.parent` while the overlap check used `src.resolve()`, so a relative or symlinked `--from` reached a different directory for the running-browser and SingletonLock checks than the one that was live. The first fix resolved both ends, which moved the bug: a symlinked `Distraction` was then checked against its target's parent instead of the `--user-data-dir` that `open` passes, and `--replace` would have renamed the target instead of the link.

## What Didn't Work
Resolving every path uniformly. Which side is canonical depends on who owns the path: the source is the person's, so its real location decides which browser is running; the destination is the plugin's own launch argument, so its lexical spelling is the one the browser process carries.

## Solution
ds/profile.py import_profile(): `src` is `expanduser().resolve()` and drives user_data_dir_of(), the process names, and the SingletonLock; `dst` stays lexical for the running check, the backup rename, and the sibling; only the containment check compares `dst.resolve()`. is_running() resolves both the argument and each `--user-data-dir=` value before comparing.

## Prevention
When a check compares a path a running process carries against a path this code derives, resolve both to the same normal form and state in a comment which of the two directories is the canonical one and why. A test per alias: relative path, symlinked source, symlinked destination.
