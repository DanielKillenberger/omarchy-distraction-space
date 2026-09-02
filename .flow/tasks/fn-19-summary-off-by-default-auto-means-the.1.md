---
satisfies: [R1, R2, R3]
---
# fn-19-summary-off-by-default-auto-means-the.1 Implement summary off by default and the Omarchy default agent for auto

## Description
Change `summary.command`'s default from `auto` to `off` in `ds/config.py` DEFAULTS and in README.md (the config table row and the "One line when you come back" paragraph). Make `auto` resolve through Omarchy's default agent: read `~/.config/omarchy/defaults/agent` (one of pi|omp|opencode|claude|codex|grok|gemini|copilot|crush) and map it in `ds/summary.py` to a headless one-shot argv that reads the prompt on stdin and answers on stdout: grok -> `grok -p`, claude -> `claude -p --output-format text`, codex -> `codex exec -s read-only --skip-git-repo-check -`, gemini -> `gemini -p`, opencode -> `opencode run`, copilot -> `copilot -p`. pi, omp, crush, an unknown value, an absent file, or a binary missing from PATH fall back to the grouped count with one state-log line each. Remove the old PATH-order probe (claude then grok). Keep the settings menu values (`auto`, `off`, custom argv), the prompt building and clipping, and the hooks' DS_HELD unchanged. The per-app count notice still appears at lock end and space entry when the command is `off`. Tests cover the default, grok, claude, codex, an unsupported agent, a missing file, and a missing binary (the last three falling back with a log line); the suite stays offline via tests/harness.py fake binaries.

**Touches:** ds/config.py, ds/summary.py, README.md, tests/test_summary.py, tests/test_config.py

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
`summary.command` now defaults to `off` (ds/config.py DEFAULTS, README row and "One line when you come back" paragraph), and `auto` resolves through `~/.config/omarchy/defaults/agent`: ds/summary.py maps grok, claude, codex, gemini, opencode, and copilot to their headless one-shot argv; pi, omp, crush, an unknown value, a missing file, or a binary missing from PATH return the grouped count with one state-log line each. The claude-then-grok PATH probe is gone. Prompt building, clipping, the settings-menu values, and DS_HELD are untouched; the count notice at lock end and space entry with `off` is pinned by the existing unlock/expiry listener test and the unit `notice` test.

Tests: `test_resolve_auto_follows_the_omarchy_default_agent` (table over grok, claude, codex, unsupported `pi`, missing file, missing binary; the last three assert exactly one log line) and `test_summary_is_off_unless_the_config_says_otherwise` (R1, config without the key). Both were run red before the ds/ change landed.

One edit outside Touches, isolated in its own commit 8c5bc59: `tests/test_ui.py:323` pinned the settings-menu toggle from the old default (`auto` -> `off`); with `off` as the default the same press yields `auto`. Details in the run notes (`fn-19-task-1-touches.md`). Also `ds/config.py._omarchy_dir` became public `omarchy_dir` (call sites were config-internal) so summary can find the agent file.

baseline: green (PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, 255 tests) ; verify: green (256 tests), receipt 8c5bc594-unittest
stage: impl-review - skipped(policy: host-deferred / parallel-wave - conductor owns the gate)

### Integration (conductor)

Fast-forwarded onto the spec branch unchanged (5bd209e, 8c5bc59); the tests/test_ui.py expectation flip is kept as the necessary consequence of the new default. Review round 1 (cursor, gpt-5.6-sol-high) returned NEEDS_WORK on one P2: a non-UTF-8 agent file raised past the OSError handler. Fixed in 151ac95 with a table case; round 2 SHIP. Quiesce verification: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at 151ac95, 256 tests, OK (receipt .flow/tmp/green-receipts/151ac955-unittest.json).

stage: wave-dispatch - ran [1 task, native worktree, rolling admission with nothing else admissible]
stage: impl-review - ran [round 1 NEEDS_WORK, round 2 SHIP] (model: gpt-5.6-sol-high via cursor; AGENTS.md reviewer pin reached through the cursor backend)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 5bd209ec7d3120ba5b3771213c77622e807f8e3a, 8c5bc594c02b30d2b6078c61d8ce9793709e85ba, 151ac955ffd76afadc07799d2fc22ccd3d495009
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (baseline: green, 255 tests, rc 0), PATH=/usr/bin:$PATH python3 -m unittest tests.test_summary tests.test_config (focused, 33 tests, rc 0), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: 256 tests, rc 0; receipt .flow/tmp/green-receipts/8c5bc594-unittest.json), PATH=/usr/bin:$PATH python3 -m unittest tests.test_summary tests.test_config (33 tests after the review fix, OK), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (quiesce, integrated target 151ac95: 256 tests, OK; receipt .flow/tmp/green-receipts/151ac955-unittest.json)
- PRs: