---
title: Sandbox leaves XDG_DATA_HOME unset; a test wrote into the real Chrome profile
date: "2026-09-05"
track: bug
category: data
module: tests/harness.py
tags: [tests, sandbox, xdg, profile, data-loss]
problem_type: data
symptoms: tests asserting on launch.profile_dir() reported /home/daniel/.local/share paths and wrote fixture files into the live Distraction profile
root_cause: "Sandbox.env() overrides HOME and three XDG vars but not XDG_DATA_HOME, which the Omarchy session exports"
resolution_type: fix
---

## Problem
tests/harness.py Sandbox overrides HOME, XDG_CONFIG_HOME, XDG_STATE_HOME, XDG_RUNTIME_DIR, and PATH, but not XDG_DATA_HOME. Omarchy sessions export XDG_DATA_HOME=/home/daniel/.local/share, so launch.data_home() and launch.profile_dir() resolve to the real ~/.local/share/omarchy/distraction-space/browser inside a test. A new test that built fixtures at launch.profile_dir() / launch.PROFILE wrote fixture files into the live Chrome profile, overwrote its Preferences, and truncated its open Cookies database (Chrome razed it: the profile's logins were lost).

## What Didn't Work
Trusting Sandbox.apply_env() as full isolation. It sandboxes the home directory, so Path.home() is safe, but any module that honors XDG_DATA_HOME escapes when the session sets it.

## Solution
tests/test_profile.py sets os.environ["XDG_DATA_HOME"] to a path under the sandbox in setUp and asserts every fixture path is inside the sandbox before a test body runs (`self.box.home.parent in path.parents`). tests/test_launch.py, test_clone.py, test_setup.py, and test_listener.py override XDG_DATA_HOME the same way.

## Prevention
Any test that touches launch.profile_dir(), launch.data_home(), or _share_dirs() overrides XDG_DATA_HOME and asserts the resulting path sits under the sandbox before writing. Fixing this in harness.py itself (add XDG_DATA_HOME to _ENV_KEYS and env()) is the durable fix and is outside fn-23's declared files.
