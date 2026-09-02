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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
