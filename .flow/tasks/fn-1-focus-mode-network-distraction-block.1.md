---
satisfies: [R1, R2, R3, R4, R5, R6, R7]
---
# fn-1-focus-mode-network-distraction-block.1 Implement Focus-mode network distraction block

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
Host impl-review on GPT-5.6 Sol high returned SHIP. Focus mode now blocks the active destination list at the network: /etc/hosts for exact names, nftables for current resolved addresses, and suffix DNS through the live resolver (systemd-resolved drop-in, owning dnsmasq instance, or resolv.conf takeover). Empty applies are refused. Apply and lift failures notify and leave the previous network state in place. Failed apply does not turn focus on. python3 tests/test_focus_block.py: 34 passed.
## Evidence
- Commits: 88740e93d476e1b388f45c2bc076532e980ef140
- Tests: python3 tests/test_focus_block.py
- PRs: https://github.com/DanielKillenberger/omarchy-distraction-space/pull/1