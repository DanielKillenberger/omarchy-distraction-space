---
title: Entry sync dropped a skipped owned entry and ran unlocked beside setup/remove
date: "2026-09-05"
track: bug
category: data
module: ds/setup.py
tags: [setup, listener, sync, lock, backup, review]
problem_type: data
symptoms: "review: malformed regenerated entry restored from stale backup; tick could delete a backup setup was recording"
root_cause: "skip and drop shared one None; no interprocess lock around the manifest transaction, existence check outside it"
resolution_type: fix
---

## Problem
The entry sync in `ds/setup.py` gained two callers this task (the listener's `refresh` and its periodic tick) and a scan that rewrites Omarchy web-app entries. Review found two defects the focused tests missed. First, `_forward_entry` returned the same `None` for "not a web app" and "a web app whose Exec cannot be parsed", so an owned entry Omarchy regenerated with a malformed Exec was logged "left alone" but fell out of the plan, and `_sync_files` treated the path as no longer wanted: it staged the regenerated file and restored the stale backup over it. Second, the listener now ran the manifest/backup transaction from another process with no lock against `setup` and `remove`; a tick that saw a file setup had just moved into `entries-backup/` classified it as a removed launcher and deleted the backup setup then recorded. A third round caught the manifest-existence check sitting outside the lock, so a remove finishing in that window let the sync recreate `entries.json` from an empty record.

## What Didn't Work
Testing the unparseable case only for entries the plugin had never owned; treating "skipped" and "dropped from the plan" as the same absence; adding the interprocess lock but leaving the pre-lock existence check in place.

## Solution
`_forward_entry` returns a `KEEP` sentinel for an entry it cannot rewrite, `_plan` carries an owned one with `text=None`, and `_sync_files`/`_unchanged` neither write nor restore over it (ds/setup.py `_forward_entry`, `_plan`, `_sync_files`). `_entries_lock` (flock on `distraction-space.entries.lock` under the runtime dir) wraps `sync_entries`, `remove_entries`, and `refresh_entries`; setup and remove wait up to `ENTRIES_LOCK_TIMEOUT`, the listener gives way at once, and the manifest-existence decision happens inside the lock in `_refresh_entries`. Tests: `test_an_owned_web_app_regenerated_with_a_malformed_exec_is_left_alone_and_still_recorded`, `test_one_entries_transaction_at_a_time_across_setup_remove_and_the_listener`, `test_the_listener_sync_keeps_nothing_a_remove_finished_before_it_took_the_lock` in tests/test_setup.py.

## Prevention
When a plan/sync step gains a "skip this item" outcome, enumerate the three states (want, skip, drop) explicitly and test the skip case on an item that is already owned. When a periodic caller is added to a transaction another process also runs, add the interprocess lock in the same change and put every read the decision depends on inside it; test it by holding the lock from a second open file description in-process.
