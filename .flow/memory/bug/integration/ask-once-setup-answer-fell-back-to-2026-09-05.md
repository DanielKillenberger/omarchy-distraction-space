---
title: Ask-once setup answer fell back to memory on a failed write; --yes left the sudo
date: "2026-09-05"
track: bug
category: integration
module: ds/setup.py
tags: [setup, prompt, persistence, "yes", sudo, review]
problem_type: integration
symptoms: setup continued on an unpersisted link answer; --yes still prompted for a sudo password
root_cause: "persistence failure handled as a warning; the never-prompt flag was applied to one prompt, not the command's whole path"
resolution_type: fix
---

## Problem
Setup's one-time link question (fn-24.3) shipped with two contract gaps the review caught. First, when writing the answer to the config file failed (config lock busy, unwritable file), `ask_links` caught the error and returned the answer in memory, so setup went on to register the handler on a choice that was never persisted; a later `setup --yes` would default to true and reverse a recorded "no". Second, `--yes` was documented as "never prompt" but only skipped the link question: the root transaction still ran plain `sudo`, which asks for a password on a first install.

## What Didn't Work
Treating the persistence failure as a soft warning ("used for this run, asked again next time"), and narrowing the `--yes` help text to "answers the link question instead of asking" while leaving the sudo prompt in place. The reviewer held to the spec's "suppresses every prompt": a wording fix does not satisfy a behavioural contract.

## Solution
`ask_links` returns None when `config.set_links` raises and `install` exits 1 before the root transaction (`ds/setup.py`, the `--yes` and persistence paths in `install`); nothing has been installed at that point, so the question simply returns next run. `_root_transaction(..., prompt=False)` under `--yes` runs `sudo -n` and the failure line names the flag. Tests: `test_an_answer_that_cannot_be_recorded_stops_setup_before_the_root_transaction`, `test_yes_never_asks_for_a_password_either` in `tests/test_setup.py`.

## Prevention
A "never prompt" or "ask once" flag is a contract over every prompt in the command's path, sudo included: grep the command's whole path for `input(`, `readline`, and bare `sudo` before claiming it. A persistence step that decides later behaviour (ask-once, opt-in) never falls back to memory; a failed write is an exit before side effects, with a test that asserts nothing downstream ran.
