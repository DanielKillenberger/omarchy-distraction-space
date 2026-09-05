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
The listener skips unchanged firewall replacement only after a fresh full-policy check confirms the same normalized addresses and slice device/inode. Drift, changed policy, recreated slice, or failed verification allows at most one replacement and postcheck per cycle. Failed verification discards the baseline and reports unavailable. Empty or disabled policies always flush. Serialized generation checks preserve cancellation, waiter ordering, and listener-only publication. The public net.apply(addresses) contract remains unchanged.

Real-kernel reconciliation on Python 3.11.16 used one replacement and three checks across three unchanged cycles. Extra-rule and deleted-table drift each triggered check/replace/check; two empty cycles both flushed. The probe bypassed sudo inside a disposable user/network namespace, as its durable evidence explicitly records. No CPU or latency percentage is claimed.

A final minimum-version check reproduced truncated pending stdin on Python 3.11 when a reader was slower than the polling interval. Temporary-file input preserves bytes, text encoding, cancellation, and launch-failure cleanup without private interpreter fields. Four delayed 262144-byte payload variants failed before the fix and passed afterward. Successful subprocess cleanup avoids signalling reaped children while timeout cleanup still terminates descendants.

The focused task suite ran 95 tests with one intentional skip. After the compatibility fix, both full suites ran 447 tests with one intentional skip each on Python 3.11.16 and 3.14.7. QML lint retained only its two documented warnings. Fable approved the initial implementation and compatibility follow-up with no blocking findings. The existing spec-completion review covers R1-R6; the follow-up preserves the reviewed reconciliation and listener logic.

stage: impl-review - ran (model: claude-fable-5-1).
stage: plan-sync - skipped(config: planSync.enabled=false).

Implementation and review remain local on fn-25-27-v3-improvements, based on v3 at f0cc79a. No push, main merge, release, or deployment occurred.
## Evidence
- Commits: 7cea6ff797077754fa2761724d064cf4f009c4e4, 3c8c949c8b7c9cccef33f97fbb9e1ddfd193be2b
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (447 tests, one intentional skip), PATH=/tmp/ds-python-compat/cpython-3.11.16-linux-x86_64-gnu/bin:/usr/bin:$PATH python3 -m unittest discover -s tests (447 tests, one intentional skip), Real kernel reconciliation on Python 3.11: .flow/evidence/v3-live-reconcile.json
- PRs: