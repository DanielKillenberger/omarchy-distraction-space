# Reliable links and deliberate window migration

> HTML render lens: [.flow/artifacts/fn-25-reliable-links-and-deliberate-window/spec.html](../artifacts/fn-25-reliable-links-and-deliberate-window/spec.html); regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "go over this repo it's vision and v3 and suggest improvements/optimizations if there are any"
> user (turn 2): "v3 should be basically implemented at this point"
> user (turn 3): "can you capture respective specs for each?"
> user (turn 4): "i mean join them as is fitting"

The requested capture refers to the preceding repository assessment. Its first two recommendations were to preserve explicit clicked URLs when a product window already exists and to replace automatic closure of foreign-profile web apps with deliberate migration. These are assistant-origin recommendations accepted for capture by reference, not verbatim user requirements. Detailed failure handling below is marked [inferred].

## Goal & Context
<!-- scope: business -->
<!-- Source: [paraphrase] accepted review recommendations 1 and 2. -->

A listed link must reach the requested page in the distraction profile even when another page on that host is already open. An existing web-app window must not lose a draft, navigation state, or a call because the listener discovered it. Both improvements preserve the person's intended activity while keeping distractions in their designated space.

## Architecture & Data Models
<!-- scope: technical -->
<!-- Source: [inferred] constraints derived from the reviewed v3 behavior. -->

Launch resolution preserves whether the person supplied an explicit URL or requested a product by name. A product-name launch may reuse a window. An explicit URL must be delivered to the distraction browser without a host-only reuse shortcut.

Foreign-profile window discovery places the window in the space and offers migration. Moving the window does not change its process membership or grant network access. Migration requires an explicit action that explains that the replacement starts in another profile and cannot transfer unsaved page state. Startup scans, reloads, and repeated window events must not turn discovery into consent to close.

## API Contracts
<!-- scope: technical -->

- The existing open command retains URL, product-name, and unlisted-forwarding inputs. Explicit URL delivery preserves path, query, and fragment. [paraphrase]
- Migration is a separate user action. Its exact menu or notice presentation is a planning decision; finding a matching window is never the action itself. [inferred]

## Edge Cases & Constraints
<!-- scope: technical -->

- A foreign window may already be network-blocked. Retaining it protects its state but does not promise it can keep syncing. [inferred]
- Browser startup success proves neither restored authentication nor transferred page state. Closing the original must therefore require deliberate user choice. [paraphrase]
- Window disappearance, rejected moves, missing browser binaries, and failed launches must leave recoverable state and clear feedback. [inferred]

## Acceptance Criteria
<!-- scope: both -->

- **R1:** Opening two distinct listed URLs on the same host delivers both exact URLs to the distraction browser, including path, query, and fragment, whether a matching window exists or not. A failed delivery attempt reports failure instead of claiming success from window discovery alone. [paraphrase]
- **R2:** Opening a listed product by name may reuse its existing window. Explicit links continue to respect the space's focus and lock behavior; unlisted links retain previous-browser forwarding. Invalid inputs and unavailable launchers retain the existing refusal behavior. [inferred]
- **R3:** Discovery of a foreign-profile listed web-app window moves it into the space, subject to existing release and snap-back policy, without automatically closing it. Startup, reload, and repeated events obey the same rule; failed moves are reported without closing the original. [paraphrase]
- **R4:** Migration is offered as a deliberate action explaining the separate profile and possible loss of unsaved state if the original is closed. Cancelling leaves the original intact. A failed replacement launch never closes the original, and a successful launch alone does not authorize closure. [inferred]
- **R5:** Regression coverage exercises two same-host deep links, named-product reuse, foreign-window discovery with possible unsaved state, cancellation, and failed migration. Fixtures never open or close real session windows. [inferred]

## Boundaries
<!-- scope: business -->

- No transfer of live browser state, drafts, calls, or authentication between profiles. Existing profile import remains a separate operation. [inferred]
- No network exemption for foreign-profile windows and no change to the process-group boundary. [inferred]

## Decision Context
<!-- scope: both -->

- Group link delivery and migration because both must preserve the activity the person meant to open. [paraphrase]
- This follow-up changes the v3 host-only reuse and automatic adoption-close decisions. The completed v3 implementation remains historical context. [inferred]
- Prefer preserving the original window over assuming that a web-app class implies disposable start-page state. [paraphrase]

## Requirement coverage

| Requirement | Task |
|---|---|
| R1 | fn-25-reliable-links-and-deliberate-window.1 |
| R2 | fn-25-reliable-links-and-deliberate-window.1 |
| R3 | fn-25-reliable-links-and-deliberate-window.2 |
| R4 | fn-25-reliable-links-and-deliberate-window.2 |
| R5 | fn-25-reliable-links-and-deliberate-window.1, fn-25-reliable-links-and-deliberate-window.2 |

## Cross-spec integration contract

- fn-25 owns launch resolution, foreign-window handling, and a standalone migration command. It uses a notification action, not edits to the main menu, and never automatically closes the original window.
- fn-26 owns status projection, bar, and menu. fn-27 alone edits listener scheduling/state production.
- Listener state adds `observed_at`, a dictionary with ISO timestamps for `site_block`, `notification_hold`, and `links`, updated only after that observation/check completes, including periodic re-observation. Existing top-level state fields remain compatible.
- Listener adds bounded `ping` IPC returning `ok\n` without initiating work. Status probes it with a short finite timeout; cached subsystem observations are not a heartbeat. fn-26 derives user-facing health from saved subsystem values, configured intent, timestamps, and ping. Absent provenance is unknown; a timestamp older than 121 seconds is stale.
- fn-26 does not probe the firewall from the bar. fn-27 reconciliation retains verification/retry and existing ownership locks. Shared docs and combined live evidence are finalized once after implementation integration.
- Implementation review for this run is Fable through Claude CLI (`--model fable`), explicitly requested by the user. The CLI probe resolved to claude-fable-5-1. This overrides the repository reviewer preference for this run only.

## Branch and release constraint

User direction during implementation: keep this work separate until admission to the Omarchy plugin marketplace. The integration branch is fn-25-27-v3-improvements, based on v3 branch fn-22-the-space-is-a-process-group-one at f0cc79a. No merge to main, release or deployment is part of this run.
