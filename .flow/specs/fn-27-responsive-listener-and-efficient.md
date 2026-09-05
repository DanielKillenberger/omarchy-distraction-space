# Responsive listener and efficient firewall reconciliation

> HTML render lens: [.flow/artifacts/fn-27-responsive-listener-and-efficient/spec.html](../artifacts/fn-27-responsive-listener-and-efficient/spec.html); regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "go over this repo it's vision and v3 and suggest improvements/optimizations if there are any"
> user (turn 2): "v3 should be basically implemented at this point"
> user (turn 3): "can you capture respective specs for each?"
> user (turn 4): "i mean join them as is fitting"

The requested capture refers to the preceding repository assessment. Recommendation 4 was to keep slow system commands off the listener loop. The additional optimization was to avoid reapplying identical firewall state while retaining periodic verification and recovery after failures or slice recreation. These are assistant-origin recommendations accepted for capture by reference. Scheduling details below are inferred requirements for preserving existing behavior.

## Goal & Context
<!-- scope: business -->
<!-- Source: [paraphrase] accepted responsiveness and firewall recommendations. -->

Window placement, notification holding, and lock deadlines must continue to be handled while system commands are slow. An idle listener should not recreate the same firewall table every minute when it can establish that the desired policy is still installed. Efficiency must preserve the process-group exception and recovery behavior.

## Architecture & Data Models
<!-- scope: technical -->
<!-- Source: [inferred] ordering constraints from the reviewed listener and ownership model. -->

Slow firewall, slice-management, and launcher-reconciliation work completes outside the event-processing path, with finite deadlines and bounded outstanding work. Results return to the listener, which remains responsible for deciding whether a result is current and for publishing state. Existing setup/remove ownership locks and transaction rollback remain intact.

Firewall reconciliation compares normalized desired policy with successfully applied state and current enforcement identity. The address set alone is insufficient because an empty-and-recreated slice can have a different kernel identity and an external actor can remove the table. Periodic checks remain able to detect and repair drift even when DNS returns identical addresses.

## API Contracts
<!-- scope: technical -->

- Existing reload and refresh requests retain completion semantics. Scheduling an operation is not success; a caller receives the applicable result or a bounded failure. [inferred]
- Disabling site blocking still removes the table, and entering or leaving the workspace never initiates a firewall update. [paraphrase]

## Edge Cases & Constraints
<!-- scope: technical -->

- Timeouts, missing binaries, failed applies, overlapping refreshes, config reload, and listener shutdown must not publish obsolete success or leave unbounded child work. [inferred]
- Slice recreation and external table removal invalidate an unchanged-policy shortcut. A failed or unverifiable health check cannot certify enforcement. [paraphrase]
- Launcher work must not race setup/remove or recreate entries after removal. Preserve the existing ownership manifest, backups, and rollback guarantees. [paraphrase]

## Acceptance Criteria
<!-- scope: both -->

- **R1:** While firewall application, slice management, or launcher cache refresh is deliberately stalled, the listener continues handling a window event, a hold transition, and a due lock deadline before the stalled operation completes. Every invoked background operation has a finite timeout; timeout and launch failure reach state and waiting callers without terminating the listener. [paraphrase]
- **R2:** Concurrent reload and refresh work is bounded and ordered so that obsolete results cannot overwrite newer policy, report false success, or re-enable blocking after it was disabled. Shutdown stops or bounds outstanding work and releases resources. [inferred]
- **R3:** Repeated periodic refreshes with identical normalized desired policy and verified unchanged enforcement do not replace the firewall table. Changed addresses or policy still cause application, and only a successful apply establishes the comparison baseline. [paraphrase]
- **R4:** Periodic reconciliation detects missing or invalid enforcement, including slice recreation, and reapplies even when desired addresses are unchanged. Failures and unverifiable checks trigger explicit degraded reporting and bounded retry rather than indefinite skipping. [paraphrase]
- **R5:** Launcher reconciliation retains setup/remove exclusion, backup restoration, and rollback behavior. Slow cache refresh does not block listener events, and overlapping requests do not create duplicate or unbounded transactions. Errors remain visible without surrendering ownership guarantees. [inferred]
- **R6:** Tests use controlled stalled commands and changed enforcement identities to prove responsiveness, ordering, timeout cleanup, no-op refreshes, and repair. Record before/after firewall replacement counts for identical periodic cycles; do not claim CPU or latency improvements without measurement. [inferred]

## Boundaries
<!-- scope: business -->

- No new firewall backend, hostname policy, ECH handling, source-port exemption design, or workspace-dependent networking. [inferred]
- No blanket cache shortcut based only on equal addresses and no removal of periodic drift detection. [paraphrase]

## Decision Context
<!-- scope: both -->

- Group scheduling and no-op refreshes because both change the same reconciliation lifecycle and must share its ordering and failure model. [paraphrase]
- Keep one listener responsible for policy decisions; move waiting work without distributing ownership decisions among workers. [inferred]
- Preserve existing entry-sync locking and subprocess failure lessons from repository memory. [inferred]

## Requirement coverage

| Requirement | Task |
|---|---|
| R1 | fn-27-responsive-listener-and-efficient.1 |
| R2 | fn-27-responsive-listener-and-efficient.1 |
| R3 | fn-27-responsive-listener-and-efficient.2 |
| R4 | fn-27-responsive-listener-and-efficient.2 |
| R5 | fn-27-responsive-listener-and-efficient.1 |
| R6 | fn-27-responsive-listener-and-efficient.1, fn-27-responsive-listener-and-efficient.2 |

## Cross-spec integration contract

- fn-25 owns launch resolution, foreign-window handling, and a standalone migration command. It uses a notification action, not edits to the main menu, and never automatically closes the original window.
- fn-26 owns status projection, bar, and menu. fn-27 alone edits listener scheduling/state production.
- Listener state adds `observed_at`, a dictionary with ISO timestamps for `site_block`, `notification_hold`, and `links`, updated only after that observation/check completes, including periodic re-observation. Existing top-level state fields remain compatible.
- Listener adds bounded `ping` IPC returning `ok\n` without initiating work. Status probes it with a short finite timeout; cached subsystem observations are not a heartbeat. fn-26 derives user-facing health from saved subsystem values, configured intent, timestamps, and ping. Absent provenance is unknown; a timestamp older than 121 seconds is stale.
- fn-26 does not probe the firewall from the bar. fn-27 reconciliation retains verification/retry and existing ownership locks. Shared docs and combined live evidence are finalized once after implementation integration.
- Implementation review for this run is Fable through Claude CLI (`--model fable`), explicitly requested by the user. The CLI probe resolved to claude-fable-5-1. This overrides the repository reviewer preference for this run only.
