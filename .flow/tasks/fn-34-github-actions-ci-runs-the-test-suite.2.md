---
satisfies: [R2]
---
# fn-34-github-actions-ci-runs-the-test-suite.2 Make the suite green on the GitHub runner

## Description
TBD

## Acceptance
The tests.yml job is green on ubuntu-latest for both matrix entries. Tests that need a Lua interpreter get it from a documented apt step; tests that need a user systemd bus or another desktop facility the runner lacks are skipped with the facility named, never weakened. The first observed green run on GitHub is the evidence.

## Done summary
The first tests.yml run (34045158842, PR #28) failed on both matrix entries for two reasons the runner exposed and this machine hid: `tests/test_launch.py` never faked a `Telegram` binary, so the two native-target cases passed here only because `/usr/bin/Telegram` is installed (`launch._detached` refuses a launch whose program is not on PATH), and `test_lua_fragment_create_error_is_not_swallowed` was the one Lua case without the `skipUnless(LUA)` guard its three siblings carry, so a missing interpreter raised TypeError from subprocess instead of skipping. The fix fakes `Telegram` beside the browsers in `setUp`, adds the missing guard, installs `lua5.4` through a documented apt step in the workflow so the Lua fragment tests run on CI instead of skipping, and names that step in the README. The "Failed to connect to bus" / "Failed to stop app-distraction.slice" / visudo / nft lines in the log come from tests that already handle a missing facility and passed on the runner; they are untouched. The mechanical edits ran on the grok-4.6 bridge from a diagnosis made here; the diff was reviewed line by line before commit.

Evidence: hiding `lua*` and `Telegram` from PATH and unsetting DBUS_SESSION_BUS_ADDRESS reproduced the runner's exact 2 failures + 1 error locally before the fix; after it the full suite is green both the standard way (451 OK, skipped=1) and runner-like (451 OK, skipped=5: the four Lua cases plus the pre-existing skip). The GitHub run itself is not observable from this session and nothing was pushed, so the first green run on GitHub is still owed as the AC's final evidence.

Follow-up, not built: a test on the runner reaches a real `systemctl --user stop app-distraction.slice` and waits out a 25 s bus timeout ("Connection timed out"); it passes, but costs the job time.

baseline: green via receipt (GATE_SKIPPED:unittest:green-receipt ed590db6 - baseline reused from prior post-gate pass)

stage: impl-review - ran [codex fan-out rid 45e9e61fcc254dbca1150715ac894032, SHIP first round, 0 findings]
## Evidence
- Commits: a79dccbf801bfcfbb969233c5efbde4627962414
- Tests: GATE_SKIPPED:unittest:green-receipt ed590db6 - baseline reused from prior post-gate pass, PATH=/usr/bin:$PATH python3 -m unittest discover -s tests  # post-edit, 451 tests OK (skipped=1), receipt a79dccbf-unittest, env -u DBUS_SESSION_BUS_ADDRESS PATH=<usr-bin-mirror-without-lua*-and-Telegram> python3 -m unittest discover -s tests  # runner-like, 451 tests OK (skipped=5), python3 -m unittest tests.test_hypr.HyprTests.test_lua_fragment_create_error_is_not_swallowed tests.test_launch.LaunchTests.test_native_target_and_unlisted_catalog_name tests.test_launch.LaunchTests.test_app_forwards_an_unlisted_url_as_an_app_window  # red before the fix (2 failures, 1 error) and green after, with Lua and Telegram hidden
- PRs: