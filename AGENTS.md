<!-- BEGIN FLOW-NEXT -->
<!-- flow-next:snippet:v2 -->
## Flow-Next

This project uses Flow-Next for ALL task tracking. `flowctl` comes from the flow-next plugin install — every flow-next skill resolves it itself, and on Claude Code it is also on PATH. Do NOT create markdown TODOs or use TodoWrite. Cold session: `flowctl brief` first — one bounded call (specs, ready tasks, memory); go deeper with `show`/`cat`/`anchor <task-id>`.

- Lifecycle: `flowctl list` / `show fn-N.M` / `start fn-N.M` / `done fn-N.M --summary-file s.md --evidence-json e.json` (e.json: `{"commits": ["<sha>"], "tests": ["<cmd>"], "prs": []}`)
- BEFORE any other flowctl operation, or when unsure of a flag: run `flowctl usage` (CLI cheatsheet + orchestration recipes) or `flowctl --help`.
- BEFORE bridging work to another model/CLI (`codex exec`, `cursor-agent`, `claude -p`, `grok`) or picking an implementation/review model: run `flowctl usage` and follow "Orchestration & model steering" exactly.
- Creating a spec: write it directly — `/flow-next:plan` is task breakdown only. `flowctl spec create --title "Short title" --plan-file plan.md --json`, then `/flow-next:plan <spec-id>`. Scaffold cascade (first match wins): `SPEC.md` -> `spec.md` -> bundled template.
- Substantial replies (reports, reviews, multi-section answers): invoke `/flow-next:prose` BEFORE drafting — the artifact prose contract applies to chat replies too. Short conversational turns skip it.
- If `flowctl` is not found: your shell lacks the plugin's `scripts/` dir on PATH (only Claude Code injects it). Resolve it the way the skills do - the plugin install's `scripts/flowctl` (Claude/Droid: plugin-root env var; Codex: `${CODEX_HOME:-$HOME/.codex}/scripts/flowctl`; Cursor/Grok: two levels above any flow-next SKILL.md) - or update/reinstall the flow-next plugin. A repo with no `.flow/` yet: run `/flow-next:setup`.
<!-- END FLOW-NEXT -->

<!-- flow-next:model-routing:start -->
## Model routing

<!-- Scaffolded by /flow-next:setup as an EXAMPLE to edit. Every routing line
     below is commented out, so nothing is routed until you uncomment one.
     These are your preferences to fill in - never detected facts. flow-next
     does not know which models your account serves and never writes one here. -->

<!-- Grammar: <tier>: <model>   or   <tier>: <model> at <effort>
     Name the model ids YOUR harness and account actually serve - ask the
     harness for its list, then invoke one; ids change and vary per account. -->

reviewer: gpt-5.6-sol-high
<!-- implementer / scout lines stay commented. reviewer is the host pin for
     review.backend host (bare only; model is not in the backend string). -->
<!-- implementer: <model> at <effort>   - work handed to another harness (plan
     here, implement cheaper or faster there). Absent = the session model
     implements. -->
<!-- fast scout: <model>                - mechanical inventory scanning, where
     the cheapest tier is the correct one. -->
<!-- thinking scout: <model>            - analysis that degrades badly on a
     fast tier. -->

<!-- Unset is the default and the doctrine: planning, capture, interview,
     requirement analysis, every verdict, and the worker run on the session
     model. Effort strings pass through to the host untranslated. -->

<!-- Resolution at each dispatch site: an explicit instruction in the moment,
     then this block, then the agent definition's own default, then the session
     model. A model this harness cannot reach falls back to the session model
     with one note - routing never fails closed, and nothing here is validated. -->
<!-- flow-next:model-routing:end -->
