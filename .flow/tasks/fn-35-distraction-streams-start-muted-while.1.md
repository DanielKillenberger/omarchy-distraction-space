---
satisfies: [R1, R2, R3, R4, R5, R6]
---
# fn-35-distraction-streams-start-muted-while.1 Implement distraction streams start muted while the hold is on

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
Distraction-browser streams are decided at creation by a WirePlumber hook: `setup` installs `install/distraction-space-hold-mute.lua` under `~/.local/share/wireplumber/scripts/` (where WirePlumber 0.5 looks) and a `required` fragment under `~/.config/wireplumber/wireplumber.conf.d/`, script before fragment and removed in reverse; the hook reads a `hold` key on its own metadata object (the Lua sandbox has no file access) and mutes or unmutes each new stream carrying the plugin's `application.id` after `node/restore-stream`, whatever WirePlumber saved. The listener asserts the key through `pw-metadata` on every `Mute.sync` (hold start, hold end, its own start, once per period) and deletes it in `Mute.stop` at shutdown; forwards strip the identity from `PULSE_PROP` the way libpulse reads the line. Continuation of the partial cut in 58aff49; the file flag, the config-dir script, and the optional feature are gone.

Live checks on this machine (WirePlumber 0.5.15): one WirePlumber restart, after which the metadata object appeared within about two seconds. R2/R4: a `paplay` stream tagged with the identity was muted at first sight in `pactl -f json list sink-inputs` with the key set and unmuted at first sight with the key deleted, in both directions against the saved per-identity state (saved `mute:true` when the unmuted stream appeared). Probe: scratchpad `mute-probe-key.sh`, log `fn35-probe.log`. libpulse's `PULSE_PROP` grammar (quotes, ticks, escapes, spaces around `=`, key after a closing quote) was probed live before the parser was written. R1's live check of a fresh browser stream was not re-run in this continuation; the earlier cut's record stands. The stale first-cut script the earlier worker left at `~/.config/wireplumber/scripts/` was removed (WirePlumber never read it). The plugin under `~/.config/omarchy/plugins` was not touched.

Mechanical rework was bridged to grok-4.6 from the worktree with a self-contained brief; its diff was reviewed here against the spec. Review round 1 (codex fan-out, gpt-6-astra) found two real defects, both fixed and captured to memory: `release()` deleted the key on the missing-pactl path while the hold was on (now `Mute.stop` owns the deletion), and the forward stripper collapsed quoted whitespace and missed a quoted identity (now a libpulse-grammar parser). Round 2: SHIP.

baseline: green (`PATH=/usr/bin:$PATH python3 -m unittest discover -s tests`, 482 tests OK, 1 skipped, at 58aff49/a44b403). Verify: 487 tests OK, 1 skipped, at 41bd24a; green receipt written for HEAD. Tests: `tests/test_wp.py` (paths, `hold`, Lua harness with `io`/`os`/`require`/`load` nilled, red-checked against the old script), `tests/test_audio.py` (key at transitions and per period, reappeared object, once-per-streak logs, pw-metadata failure, missing-pactl regression, listener integration), `tests/test_setup.py` (data-dir script, install and remove order), `tests/test_launch.py` (parser table, quoted identity on both forward paths).

stage: impl-review - ran [round 1 fan-out NEEDS_WORK -> round 2 SHIP] (model: codex gpt-6-astra medium)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 58aff49d0d1564d9a8a60f8be84c7079d0edf20f, a44b403234637c2a4c6cb130a3de991a74a5263f, 0b5c93127a2e56064a69028e19a515ed7be68350, 41bd24a9912011d70e08baf000e03f57df50a7a3, 46d5df1959d58b2fa1a718a384c1e1b9fbcd060c
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (baseline: green, 482 OK 1 skipped), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 487 OK 1 skipped, receipt 41bd24a9-unittest), PATH=/usr/bin:$PATH python3 -m unittest tests.test_launch tests.test_audio tests.test_wp tests.test_setup tests.test_listener, live: scratchpad/mute-probe-key.sh (key set: muted at first sight; key deleted: unmuted at first sight against saved mute:true; 1 WirePlumber restart)
- PRs: