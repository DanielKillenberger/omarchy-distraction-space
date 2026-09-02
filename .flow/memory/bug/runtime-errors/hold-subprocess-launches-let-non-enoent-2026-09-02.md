---
title: Hold subprocess launches let non-ENOENT OSError reach the listener; keys over-in
date: "2026-09-02"
track: bug
category: runtime-errors
module: ds/hold.py
tags: [hold, subprocess, listener, sender-keys, review]
problem_type: runtime-error
symptoms: PermissionError on omarchy-shell or busctl would stop the listener; listing X silenced twimg hosts
root_cause: only FileNotFoundError caught around launches; hosts treated as sender identity for catalog entries
resolution_type: fix
---

## Problem
Review of `ds/hold.py` found two ways the optional hold feature reached past its own boundary. The `omarchy-shell` and `busctl` launches caught only `FileNotFoundError`, so a `PermissionError` or `EMFILE` on either subprocess would escape into the listener's select loop and stop containment, the site block, and the lock tick along with it. Separately, `sender_keys()` folded every catalog `hosts` entry into the pushed keys, so listing X silenced `pbs.twimg.com` and sixteen other resource hosts although the spec contract names only catalog `senders` plus the PWA host for catalog entries, with hosts reserved for plain and custom hostname entries.

## What Didn't Work
`except FileNotFoundError` as the only launch guard, and treating the expansion's `hosts` list as sender identity for every entry regardless of where the entry came from.

## Solution
`_shell()` catches `OSError` and reports `unavailable`; `Capture._start()` catches `OSError`, closes a half-made process, and schedules the same 1/4/16 s backoff an exit takes (ds/hold.py). `_entry_keys()` adds `hosts` only when the entry name is not a catalog product; catalog entries contribute `senders` plus the host parsed out of their `pwa_class` pattern.

## Prevention
For a subprocess behind an optional feature inside a long-lived loop, catch `OSError` (not just `FileNotFoundError`) and write one focused test that mocks `subprocess.run`/`Popen` with `PermissionError`; a non-executable fake on PATH does not work because lookup falls through to the real binary. When a spec contract enumerates identity sources per entry kind, test one entry of each kind and assert the exact key list, including an entry with many catalog hosts.
