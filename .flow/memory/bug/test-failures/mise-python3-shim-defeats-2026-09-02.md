---
title: mise python3 shim defeats tests/harness.py fake binaries; ~112 phantom failures
date: "2026-09-02"
track: bug
category: test-failures
module: tests/harness.py
tags: [tests, path, mise, harness, environment]
problem_type: test-failure
symptoms: python3 -m unittest discover -s tests fails ~112 cases (20/27 in test_hypr) while PATH=/usr/bin:$PATH passes 239/239
root_cause: "harness prepends its fake-binary dir to PATH, but a mise python3 shim makes the child resolve the real hyprctl/getent instead of the fakes"
resolution_type: fix
---

## Problem
`python3 -m unittest discover -s tests` reports around 112 failures on this machine while the same suite passes 239/239. The failures cluster in `tests/test_hypr.py` (20 of its 27 cases) with assertions like `assertTrue(any("hl.dsp.window.move" in j ...))` finding nothing recorded, which reads as a real containment regression.

## What Didn't Work
Reading the failures as product bugs. Nothing in `ds/hypr.py` is wrong, and the same commit is green in the recorded baseline.

## Solution
`tests/harness.py` `Sandbox.env()` puts its fake-binary directory at the front of `PATH` (`path = str(self.bin) + os.pathsep + os.environ["PATH"]`) so the plugin's subprocess calls hit fake `hyprctl`, `getent`, `busctl`, and `pactl`. When `python3` resolves through a mise shim (`~/.local/share/mise/shims/python3`), the child process ends up resolving the real `hyprctl` instead of the fake, and every assertion that inspects recorded fake-binary calls fails.

Run the suite with the system interpreter first on PATH:

```bash
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
```

That is the invocation recorded in the flow baseline and the one documented in README.md "Contributing" as of fn-16.

## Prevention
Any agent or human reporting a mass test failure in this repo checks `which python3` before filing it. A shim path under `~/.local/share/mise/` (or asdf, pyenv) means re-run with `PATH=/usr/bin:$PATH` before treating the failures as real.
