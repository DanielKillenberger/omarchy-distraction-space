---
title: Ownership record accepted any JSON and a failed clone step stranded a live clone
date: "2026-09-02"
track: bug
category: data
module: ds/setup.py
tags: [setup, clone, lifecycle, ownership, rollback]
problem_type: data
symptoms: setup could delete a hand-made clone or leave a half-made enabled clone that later reads as foreign
root_cause: isinstance(dict) as ownership proof; clone-tool/patch/record failures after creation returned without rollback
resolution_type: fix
---

## Problem
The clone lifecycle in `ds/setup.py` treated any JSON object in `clone.json` as proof that the `<user>.notifications` clone was plugin-created, so a stale or empty record could make setup delete a clone the person made by hand. Creation was also not transactional: `omarchy-plugin-clone` can exit nonzero after it has created and enabled the clone (its closing notification failing does that), and a patch or record-write failure after cloning left the enabled clone in place with no record, so the next run classified it as foreign and never touched it again.

## What Didn't Work
`isinstance(record, dict)` as the ownership test, and returning 1 straight from the clone-tool failure branch.

## Solution
`_read_record()` (ds/setup.py) returns the record only when it names this exact clone id and path and carries the fingerprint schema; anything else follows the foreign-clone path. `_finish_clone()` wraps patch + record write and, on any failure, runs `_remove_clone()` (shell `setPluginEnabled <id> false`, then rmtree) before exiting 1; the clone-tool failure branch removes a directory the tool left behind the same way.

## Prevention
For any step that creates an externally visible resource then records ownership: one focused test per failure point after creation (tool fails late, post-processing fails, record write fails) asserting the resource is gone, and a subTest table of malformed ownership records asserting the foreign path is taken.
