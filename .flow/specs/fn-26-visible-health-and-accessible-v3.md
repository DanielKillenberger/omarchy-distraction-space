# Visible health and accessible v3 controls

> HTML render lens: [.flow/artifacts/fn-26-visible-health-and-accessible-v3/spec.html](../artifacts/fn-26-visible-health-and-accessible-v3/spec.html); regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "go over this repo it's vision and v3 and suggest improvements/optimizations if there are any"
> user (turn 2): "v3 should be basically implemented at this point"
> user (turn 3): "can you capture respective specs for each?"
> user (turn 4): "i mean join them as is fitting"

The requested capture refers to the preceding repository assessment. Recommendations 3 and 5 were to make degraded operation visible, verify the live firewall and web-app audio boundaries, and expose v3 controls through the menu. These are assistant-origin recommendations accepted for capture by reference. Detailed status and failure semantics remain marked [inferred].

## Goal & Context
<!-- scope: business -->
<!-- Source: [paraphrase] accepted review recommendations 3 and 5. -->

The person should know when the distraction space is only partially working and should be able to make routine exceptions from its own menu. The bar currently exposes the lock and held-notification count while subsystem degradation stays in command output or notices. Several v3 settings and temporary window release require command-line knowledge.

## Architecture & Data Models
<!-- scope: technical -->
<!-- Source: [inferred] status and menu integration requirements. -->

Status separates the last observed subsystem state from the time the status response was generated. Listener liveness alone does not prove that it is responsive or that an external subsystem still matches the saved observation. The bar and menu consume a shared health assessment and distinguish intentionally disabled features from failures and unknown state.

Existing config validation and command behavior remain the authority for menu changes. A menu success means the requested change succeeded, not merely that the menu closed. Persisted choices and effective behavior are distinguished where setup or another action is still needed.

## API Contracts
<!-- scope: technical -->

- Preserve the existing status interface while exposing observation freshness and reasons for degraded or unknown operation. Exact additional field names are chosen during planning. [inferred]
- Add a plain-language status action, temporary window release, and settings for listed-link routing, site blocking, and snap-back. Existing configurable release duration remains authoritative. [paraphrase]

## Edge Cases & Constraints
<!-- scope: technical -->

- No listener, an unresponsive listener, unreadable state, unavailable notification holding, failed site blocking, and displaced browser routing must not appear healthy by default. [inferred]
- An intentionally disabled feature is a user choice rather than an operational failure. Health presentation must not create repeated distraction banners. [inferred]
- Live evidence must identify what was actually exercised. A passing offline fake is not evidence that the kernel or audio server accepted the integration. [paraphrase]

## Acceptance Criteria
<!-- scope: both -->

- **R1:** The bar quietly indicates degraded or unknown operation for enabled containment services and offers readable reasons through its status surface. Lock and held-count behavior remains available; absent or malformed status produces unknown state rather than a healthy fallback. [paraphrase]
- **R2:** Status preserves the age and provenance of saved observations instead of stamping them as freshly verified on each read. A stopped or unresponsive listener is distinguishable from a working listener, and deliberately disabled features are distinguishable from failures. [inferred]
- **R3:** The menu can release the focused window for the configured default duration and can change listed-link routing, site blocking, and snap-back with everyday labels. It reflects effective versus pending behavior, reports failed changes, and leaves the saved choice unchanged on cancellation or validation failure. Release with no focused window or no listener uses the existing refusal behavior. [paraphrase]
- **R4:** Live validation demonstrates that a listed blocked host is reachable from the distraction process group and refused outside it, and that distraction web-app sound mutes and restores while unrelated work-browser sound remains unaffected. Record the exercised browser and platform versions, results, and remaining limitations. Missing capabilities or failed checks remain explicitly unverified or failed. [paraphrase]
- **R5:** Automated coverage exercises healthy, disabled, unavailable, displaced, missing, malformed, and stale observations plus menu cancellation and failed application of settings. The ordinary suite remains offline and isolated; live validation restores the session state it changes. [inferred]

## Boundaries
<!-- scope: business -->

- No continuous privileged probing from the bar, automatic default-browser takeover, or automatic repair of disabled settings. [inferred]
- No new focus modes, analytics, browser support expansion, or claim that all supported browsers were verified from a single-browser check. [inferred]

## Decision Context
<!-- scope: both -->

- Group health with controls because the person needs both an explanation of what is happening and a way to make the relevant choice. [paraphrase]
- Keep the degraded indicator quiet to preserve the attention-saving purpose of the space. [paraphrase]
- Live firewall and audio evidence belongs here because the health surface must not imply stronger guarantees than the integration can demonstrate. [inferred]

## Requirement coverage

| Requirement | Task |
|---|---|
| R1 | fn-26-visible-health-and-accessible-v3.1 |
| R2 | fn-26-visible-health-and-accessible-v3.1 |
| R3 | fn-26-visible-health-and-accessible-v3.1 |
| R4 | fn-26-visible-health-and-accessible-v3.2 |
| R5 | fn-26-visible-health-and-accessible-v3.1, fn-26-visible-health-and-accessible-v3.2 |

## Cross-spec integration contract

- fn-25 owns launch resolution, foreign-window handling, and a standalone migration command. It uses a notification action, not edits to the main menu, and never automatically closes the original window.
- fn-26 owns status projection, bar, and menu. fn-27 alone edits listener scheduling/state production.
- Listener state adds `observed_at`, a dictionary with ISO timestamps for `site_block`, `notification_hold`, and `links`, updated only after that observation/check completes, including periodic re-observation. Existing top-level state fields remain compatible.
- Listener adds bounded `ping` IPC returning `ok\n` without initiating work. Status probes it with a short finite timeout; cached subsystem observations are not a heartbeat. fn-26 derives user-facing health from saved subsystem values, configured intent, timestamps, and ping. Absent provenance is unknown; a timestamp older than 121 seconds is stale.
- fn-26 does not probe the firewall from the bar. fn-27 reconciliation retains verification/retry and existing ownership locks. Shared docs and combined live evidence are finalized once after implementation integration.
- Implementation review for this run is Fable through Claude CLI (`--model fable`), explicitly requested by the user. The CLI probe resolved to claude-fable-5-1. This overrides the repository reviewer preference for this run only.
