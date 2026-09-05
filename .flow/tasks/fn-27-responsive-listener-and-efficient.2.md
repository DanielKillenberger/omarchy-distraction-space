---
satisfies: [R3, R4, R6]
---
# fn-27-responsive-listener-and-efficient.2 Skip unchanged firewall replacement only after verification

## Description
Add a fixed-scope bounded read-only privileged firewall check if needed. Normalize desired state, record baseline only after successful apply and actual enforcement check, verify current table and slice identity periodically, and skip replace only on verified equal policy. Detect rule/table drift and recreated cgroup identity; equal DNS addresses are never sufficient proof. Preserve wrapper input restrictions and source-port exemption.

**Files:** ds/net.py, ds/listener.py, distractions-nft, install/sudoers.omarchy-distraction-space, tests/test_net.py, tests/test_nft.py, tests/test_listener.py
**Touches:** ds/net.py, ds/listener.py, distractions-nft, install/sudoers.omarchy-distraction-space, tests/test_net.py, tests/test_nft.py, tests/test_listener.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_net tests.test_nft tests.test_listener

## Acceptance
- Parent R3/R4/R6 for reordered equal addresses, modified policy/table, missing table, recreated slice, failed apply/check and recovery.
- Periodic verification remains; explicit refresh/reload completion remains truthful.
- Record before/after replacement counts from deterministic repeated-cycle tests.
- No arbitrary privileged command surface or weakened fixed wrapper validation.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
