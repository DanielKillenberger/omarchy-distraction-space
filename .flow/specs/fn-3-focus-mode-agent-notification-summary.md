# Focus-mode agent notification summary

> HTML render lens: [.flow/artifacts/fn-3-focus-mode-agent-notification-summary/spec.html](../artifacts/fn-3-focus-mode-agent-notification-summary/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "summary is good. Note that we should spec out a feature where if user has an agent defined the user can configure the distraction-space to have the agent parse them during focus mode (inaccessible summary in the background) and one summary of important things will be presented at the end"
> user (turn 2): "yes capture that as fn-3"
> user (turn 3): "omarchy lets you define an agent and we should use the one the user has defined. The plugin should keep a ledger on what important means to the user. So the user could say summary not helpful or helpful and leave feedback. That'll be stored to inform the next summary parse."
> user (turn 4): "user will have to choose one but i think i can only enable one?"
> user (turn 5): "there's a default agent set"
> user (turn 6): "i guess you could override it to a cli app"
> user (turn 7): "any of the ones that omarchy allows as agent"
> user (turn 8): "we should have basically the same selector modal that omarchy has for our summary agent"
> user (turn 9): "well any of them that allow headless invocation like claude -p or similar"
> user (turn 10): "the user needs to enable agent summaries in the plugin. Having an agent in omarchy doesn't immediately consent to agent summaries."

## Goal & Context
<!-- scope: business -->
<!-- Source-tag breakdown: 80% [user] / 20% [paraphrase] -->

The mute spec already hides banners and sounds, then shows a grouped per-app count when focus turns off. That count is a thin catch-up. This spec adds an optional path the user must turn on in the plugin. Having an Omarchy default agent is not consent. Once enabled, the plugin uses that default agent to read blocked pings during focus, in the background, and the user gets one summary of important things when focus turns off. The user can override that default with the same kind of selector modal Omarchy already uses, limited to agents that can run a one-shot headless prompt. After each summary, the user can mark it helpful or not and leave feedback. That ledger shapes the next parse. Focus mode still works with agent summaries off. The grouped count stays the catch-up until the user enables this path.

## Architecture & Data Models
<!-- scope: technical -->
<!-- Source-tag breakdown: 70% [paraphrase] / 30% [inferred] -->

This path is optional configuration on top of the mute spec and stays off until the user enables agent summaries in the plugin. The mute spec still owns blocking and the grouped-count fallback. Once enabled, the agent in use is Omarchy's default agent, unless the user overrides it through the same kind of selector modal Omarchy uses for its default agent. The offered set is only those Omarchy agents that can run headless, a one-shot prompt with no interactive session. Focus-on starts a background parse of the blocked distraction-space pings. The running parse is not readable until focus-off. Focus-off presents one important-things summary and a helpful / not-helpful prompt with optional feedback. That ledger is an input to the next parse. How the plugin talks to the agent is not part of this spec.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** When an agent is configured, that agent parses blocked distraction-space notifications in the background while focus mode is on. Errors: if the parse fails, the plugin tells the user when focus turns off. [paraphrase]
- **R2:** The running parse and any in-progress summary stay inaccessible until focus turns off. Errors: no error surface beyond R1. [user]
- **R3:** When focus turns off and an agent is configured, the user sees one summary of important things, not each original ping. Errors: if the summary cannot be shown, the plugin tells the user. [user]
- **R4:** When no agent is configured, this spec does not change the mute spec's grouped-count catch-up. Errors: no error surface. [paraphrase]
- **R5:** The user can point the plugin at an agent they already have, without rebuilding or reinstalling. Errors: a rejected setting leaves the previous agent setting unchanged. [paraphrase]
- **R6:** If the agent path fails, the mute spec's grouped-count notice still applies. Errors: no error surface beyond R1 and R3. [inferred]
- **R7:** When no override is set, the plugin uses Omarchy's default agent. Errors: if Omarchy has no default agent, R4 applies. [user]
- **R8:** The user can override the default to any agent Omarchy allows as an agent. Errors: a rejected override leaves the previous setting unchanged. [user]
- **R9:** After a summary, the user can mark it helpful or not helpful and leave feedback. Errors: a rejected note is not stored; earlier ledger entries stay. [user]
- **R10:** The plugin stores that feedback in a ledger that informs the next summary parse. Errors: if the write fails, the plugin tells the user; the summary already shown stays; the next parse may lack the new entry. [user]
- **R11:** The override set is only Omarchy-allowed agents that support headless invocation, a one-shot prompt with no interactive session. Errors: an agent that cannot run that way is not offered. [user]
- **R12:** The override picker is the same kind of selector modal Omarchy uses for its default agent. Errors: if the picker cannot open, the previous setting stays and the plugin tells the user. [user]
- **R13:** Agent summaries stay off until the user enables them in the plugin. An Omarchy default agent alone does not turn them on. Errors: while off, R4 applies. [user]

## Boundaries
<!-- scope: business -->

- Notification mute, banners, sounds, and the no-agent grouped count stay the mute spec. [paraphrase]
- Network destination blocking stays the network spec. [paraphrase]
- Focus mode does not require an agent, and an Omarchy default agent is not consent to send pings to it. [user]
- Peeking at the running parse while focus is on is out of scope. [user]
- An override that is not an Omarchy-allowed agent, or that cannot run headless, is out of scope. [user]

## Decision Context
<!-- scope: both -->

The mute spec's grouped count is enough to ship. The user asked for a later path where an agent reads the blocked pings during focus and returns one important-things summary at the end. [paraphrase]

The agent is Omarchy's default agent, and only after the user enables agent summaries in this plugin. The user can override it through the same kind of selector modal Omarchy already uses. The offered set is only agents Omarchy allows that can run a one-shot headless prompt. The plugin does not invent its own agent list. [user]

What counts as important is a ledger. Helpful / not-helpful plus optional feedback after each summary shapes the next parse. [user]

This is a sibling of the mute spec, not a rewrite of it. Same focus-mode gate. Different surface. [user]

How the plugin talks to that agent stays unset here so plan can pick it against Omarchy. [inferred]

## Parked unknowns

- How the plugin hands ping text and the ledger to the agent. Plan picks the mechanism.
- Which current Omarchy agents qualify as headless. Plan checks each allowed agent against a one-shot prompt.

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.M (TBD — populate via /flow-next:plan) |
| R2 | fn-N.M (TBD — populate via /flow-next:plan) |
| R3 | fn-N.M (TBD — populate via /flow-next:plan) |
| R4 | fn-N.M (TBD — populate via /flow-next:plan) |
| R5 | fn-N.M (TBD — populate via /flow-next:plan) |
| R6 | fn-N.M (TBD — populate via /flow-next:plan) |
| R7 | fn-N.M (TBD — populate via /flow-next:plan) |
| R8 | fn-N.M (TBD — populate via /flow-next:plan) |
| R9 | fn-N.M (TBD — populate via /flow-next:plan) |
| R10 | fn-N.M (TBD — populate via /flow-next:plan) |
| R11 | fn-N.M (TBD — populate via /flow-next:plan) |
| R12 | fn-N.M (TBD — populate via /flow-next:plan) |
| R13 | fn-N.M (TBD — populate via /flow-next:plan) |
