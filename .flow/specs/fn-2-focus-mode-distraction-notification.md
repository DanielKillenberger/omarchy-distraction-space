# Focus-mode distraction notification block

> HTML render lens: [.flow/artifacts/fn-2-focus-mode-distraction-notification/spec.html](../artifacts/fn-2-focus-mode-distraction-notification/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "next spec is that all notifications from distraction space should also be blocked. So during focus mode i don't want to get a notification from apps in distraction space."

## Goal & Context
<!-- scope: business -->

The person using this plugin already hides the distraction workspace when focus mode is on. Those apps still send desktop banners and sounds, so a chat ping can break focus without the window being visible. Winning is a full focus session with zero banners and zero sounds from those apps. When focus turns off, one grouped notice lists a count per app that pinged, and may play one sound. Copy matches Omarchy's native voice, the same matter-of-fact tone as the bar eye and the 50-character reason field. This spec sits beside the network-destination block and can ship in either order.

## Architecture & Data Models
<!-- scope: technical -->
<!-- Source-tag breakdown: 70% [paraphrase] / 30% [inferred] -->

Focus mode on applies a notification block for every app that belongs to the distraction space. Focus mode off lifts the block this spec applied. Membership is the workspace's apps, not the extra network destinations that are not apps in that space. The enforcement mechanism is not part of this spec.

## API Contracts
<!-- scope: technical -->

*Pending technical-scope interview pass.*

## Edge Cases & Constraints
<!-- scope: technical -->

*Pending technical-scope interview pass.*

## Acceptance Criteria
<!-- scope: both -->

- **R1:** While focus mode is on, the user does not receive a notification from any app that belongs to the distraction space. Errors: if apply fails, the plugin tells the user and leaves the previous notification state unchanged. [paraphrase]
- **R2:** Notifications from apps that do not belong to the distraction space still appear while focus mode is on. Errors: no error surface beyond R1. [paraphrase]
- **R3:** Turning focus mode off restores notifications from the distraction-space apps. Errors: if the lift fails, the plugin tells the user and blocks may remain until a later successful lift. [inferred]
- **R4:** After focus turns off, one grouped notice lists a count per distraction-space app that pinged. Errors: if nothing was blocked, show no notice. [user]
- **R5:** That grouped notice may play one sound. Errors: no error surface beyond R4. [user]
- **R6:** While focus is on, both the popup banner and the sound from those apps are blocked. Errors: no error surface beyond R1. [user]
- **R7:** There is no way to read blocked pings or a running summary while focus is on. Errors: no error surface beyond R1. [user]
- **R8:** If the mute cannot apply, the plugin tells the user, leaves pings as they were, and focus can still turn on. Errors: no error surface beyond R1. [user]

## Boundaries
<!-- scope: business -->

- Network destination blocking stays the sibling spec. This spec is notifications only. [paraphrase]
- Extra destinations that are not apps in the distraction space are not a notification-block set here. [paraphrase]
- A whole-desktop mute that blocks every app is out of scope. [inferred]
- Unread badges are out of scope. The user has no badge surface. [user]
- No history screen and no per-app notification toggles. Workspace membership is the list. [user]
- No allow-list and no urgent bypass. If the app lives in the space, it is silent until focus is off. [user]
- Agent-parsed "important things" summary is a later sibling spec. This spec ships a grouped count without an agent. [user]

## Decision Context
<!-- scope: both -->

### Motivation
<!-- scope: business -->

Winning is a focus session with no banner and no sound from distraction-space apps. A grouped per-app count after focus-off is enough. Opening the apps after is how you catch up. A thin count is an accepted miss. The mute and the catch-up ship together. This work can ship before, after, or with the network block.

### Implementation Tradeoffs
<!-- scope: technical -->

Hiding the distraction workspace does not stop notification banners or sounds. The user asked for those notifications to be blocked while focus mode is on, scoped to apps in that space. [paraphrase]

This is a sibling of the network-destination block. Same focus-mode gate. Different surface. [paraphrase]

The block mechanism stays unset here so plan can pick it against Omarchy and the desktop notification daemon. [inferred]

## Parked unknowns

- How the notification block is enforced. Plan picks the mechanism.

## Resolved via Project Docs

- `README.md`: Focus mode is on by default. Super+D is the only way into the distraction space, and only after focus is off. Turning focus off requires a zenity reason of at least 50 characters. The bar control is an eye icon.
- `.flow/specs/fn-1-focus-mode-network-distraction-block.md`: Sibling spec blocks network destinations while focus is on. This spec is notifications only.
- `CHANGELOG.md`, `STRATEGY.md`, `GLOSSARY.md`, `knowledge/decisions/`: absent.

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
