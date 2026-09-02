# Summary off by default; `auto` means the Omarchy default agent

## Conversation Evidence

> user: "Default is ai summaries is off right?" then "it should default to off and it should default to the agent i defined as my agent in omarchy (grok)"

## Goal & Context

<!-- scope: business -->

A fresh install never sends notification text to an agent. The "While you were away" notice shows the per-app count until the person turns the agent summary on, and when they do, the plugin uses the coding agent they already chose in Omarchy instead of whichever CLI happens to be on PATH first.

## Architecture & Data Models

<!-- scope: technical -->

- `summary.command` default changes from `auto` to `off` in `ds/config.py` DEFAULTS and README.
- `auto` resolves through Omarchy's default agent: `~/.config/omarchy/defaults/agent` holds one of `pi|omp|opencode|claude|codex|grok|gemini|copilot|crush` (written by `omarchy default agent`; absent when the person never chose). `ds/summary.py` maps it to a headless one-shot invocation that reads the prompt on stdin and answers on stdout: `grok` to `grok -p`, `claude` to `claude -p --output-format text`, `codex` to `codex exec -s read-only --skip-git-repo-check -`, `gemini` to `gemini -p`, `opencode` to `opencode run`, `copilot` to `copilot -p`; `pi`, `omp`, `crush`, an unknown value, an absent file, or a binary missing from PATH fall back to the count, each with one state-log line. The old PATH-order probe (claude then grok) is removed.
- The listener's existing settings menu row for `summary.command` keeps its values (`auto`, `off`, custom argv).
- The user's own config on this machine is left as they set it; the default applies to new installs and to a config without the key.

## Quick commands

```bash
python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
```

## Acceptance Criteria

<!-- scope: both -->

- **R1:** A config without `summary.command` resolves to `off`; DEFAULTS and README say `off`. Errors: none.
- **R2:** With `summary.command: auto`, the command comes from `~/.config/omarchy/defaults/agent` through the mapping above; tests cover grok, claude, codex, an unsupported agent, a missing file, and a missing binary, the last three falling back to the count with a state-log line. Errors: none.
- **R3:** The per-app count notice still appears at lock end and space entry when the command is `off`. Errors: none.

## Boundaries

<!-- scope: business -->

- No change to how the prompt is built or clipped, or to the hooks' `DS_HELD`.
- Deciding whether the summary runs on plain space entry as well as lock end is a separate decision the user has not made yet.

## Decision Context

<!-- scope: both -->

The user chose on 2026-09-02: off by default, and the Omarchy default agent as the meaning of `auto`. Rejected: keeping the PATH-order probe, which picked claude on a machine whose chosen agent is grok.
