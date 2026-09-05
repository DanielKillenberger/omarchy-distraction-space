---
title: argparse read pass-through browser flags as its own; profile dir published befor
date: "2026-09-05"
track: bug
category: runtime-errors
module: ds/launch.py
tags: [open, argparse, pass-through, race, rename, review]
problem_type: runtime-error
symptoms: open -headless printed help and launched nothing; --class Example before the URL became the target; a racing first launch started Chrome before Preferences existed
root_cause: parse_known_args matched -h by single-dash prefix and took a flag's value as the positional; mkdir-then-write exposed an incomplete profile directory
resolution_type: fix
related_to: [bug/runtime-errors/held-record-consumption-split-across-2026-09-02, bug/runtime-errors/hold-subprocess-launches-let-non-enoent-2026-09-02, bug/runtime-errors/mute-release-forgot-streams-whose-2026-09-02, bug/runtime-errors/resolve-the-source-keep-the-destination-2026-09-05]
---

## Problem
`distractions open` grew pass-through browser flags (`--incognito`, `-headless`, `--class Example`) and the first cut ran the tail through argparse with `parse_known_args`. Review reproduced two defects: `-headless` matched argparse's `-h` and printed help with exit 0 (nothing launched), and a flag's separate value before the URL (`--class Example https://x`) became the target while the same tokens after the URL forwarded correctly. Same round: `ensure_profile` did `mkdir` then wrote `Preferences`, so a concurrent first launch saw `FileExistsError`, returned, and started Chrome before the preference existed.

## What Didn't Work
`allow_abbrev=False` on the subparser only governs `--long` prefixes; single-dash tokens still match `-h` with the rest as an attached value. Any argparse route for an opaque tail has this class of hole.

## Solution
`distractions` `main` hands `open`'s tail to `launch.open_target(argv)` unparsed; `-h`/`--help` are matched as exact tokens and the subparser exists for help text only. `launch.split_args` takes `--app` anywhere, the first scheme-carrying token (else the first non-dash token) as the target, and keeps every other token in order (ds/launch.py `split_args`). `ensure_profile` builds the profile in a `mkdtemp` sibling and `os.rename`s it into place; a lost race hits ENOTEMPTY, leaves the winner alone, and removes the sibling.

## Prevention
When a CLI must forward foreign flags verbatim, never let argparse see them: split the tail by hand and test `-h`-prefixed short flags and `--flag value <target>` ordering. When a directory must appear complete to a concurrent reader, publish it by rename of a fully written sibling, never mkdir-then-fill.
