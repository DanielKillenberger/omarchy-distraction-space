---
satisfies: [R3, R4, R6]
---
# fn-27-responsive-listener-and-efficient.2 Skip unchanged firewall replacement only after verification

## Description
Consume the fixed check ds verb supplied by independent task .3. Normalize desired state, record baseline only after successful apply and actual enforcement check, verify current table and slice identity periodically, and skip replace only on verified equal policy. Detect rule/table drift and recreated cgroup identity; equal DNS addresses are never sufficient proof. Preserve wrapper input restrictions and source-port exemption.

**Files:** ds/net.py, ds/listener.py, tests/test_net.py, tests/test_listener.py
**Touches:** ds/net.py, ds/listener.py, tests/test_net.py, tests/test_listener.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_net tests.test_nft tests.test_listener
## Acceptance
- Parent R3/R4/R6 for reordered equal addresses, modified policy/table, missing table, recreated slice, failed apply/check and recovery.
- Periodic verification remains; explicit refresh/reload completion remains truthful.
- Record before/after replacement counts from deterministic repeated-cycle tests.
- No arbitrary privileged command surface or weakened fixed wrapper validation.

## Done summary
The listener now skips unchanged firewall replacement only after a fresh complete policy check confirms the same slice device/inode. Changed policy, drift, recreated slice, or failed verification permits at most one replacement and postcheck per cycle. Failed verification reports unavailable and discards the baseline; empty/disabled policy flushes each time. Cancellation and stale-generation ordering stay serialized. The wait budget includes three wrapper calls.

Focused gate passed95 tests with1 intentional skip; full integrated gate passed445 tests with1 intentional skip. Real-kernel namespace evidence in .flow/evidence/v3-live-reconcile.json confirms one replace andthreechecks overthreeequal cycles, repair of extra-rule anddeleted-table drift, and repeatedemptyflush. No CPU/latency percentage claimed.

Fable implementation review SHIP with no blocking findings. Successful subprocess cleanup no longer signals reaped children; timeout descendants remaincovered. Notice recovery and generic incomplete-work messages are tested. Public net.apply(addresses) remains unchanged.

stage: impl-review - ran (model: claude-fable-5-1).
stage: plan-sync - skipped(config: planSync.enabled=false).
No push, merge, release or deployment.
## Evidence
- Commits: 7cea6ff, 8edafdb, 075f4e2
- Tests: PATH=/usr/bin:$PATH python3 -m unittest tests.test_net tests.test_nft tests.test_listener (95 passed,1 intentional skip), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (445 passed,1 intentional skip), Real kernel reconciliation in disposable namespace: .flow/evidence/v3-live-reconcile.json
- PRs: