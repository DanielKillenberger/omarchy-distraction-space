---
satisfies: [R1, R2, R3]
---
# fn-13-messaging-apps-are-moved-never-network.1 Implement Messaging apps are moved, never network-blocked

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
Telegram, Discord, WhatsApp, Signal, and Google Messages ship `hosts: []` with explicit `pwa` keys where the PWA class used to come from the first host, so their windows still move and their traffic is never dropped. README documents the moved-versus-blocked table (corrected to runtime: every catalog product moves its windows, messaging skips the block) and shows the shipped shapes. `test_moved_versus_blocked_table` pins it.

stage: impl-review - ran (model: gpt-5.6-sol-high via cursor backend; SHIP on round 2)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 271d1a6, ef0d8ea, f9bf89e
- Tests: python3 -m unittest discover -s tests
- PRs: