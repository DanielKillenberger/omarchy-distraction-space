---
satisfies: [R4, R6]
---
# fn-27-responsive-listener-and-efficient.3 Verify the fixed firewall policy and slice identity

## Description
Implement the privileged verification half independently while listener review finishes. Add fixed check ds verb taking same bounded address-only stdin; compare complete actual nft policy to expected rules, including ordering, level5 cgroup exemption, exactsets, sourceports61000-61999 and no extras. Read /tmp/fn27-2-design.md for confirmed nft1.1.6 JSON omissions and textual rendering details. Root confirmed real kernel testing works in disposable unshare --user --map-root-user --net namespace with SUDO_UID=1000 and actualexisting slice. Actual nft text expands bare reject into reject with icmp port-unreachable or icmpv6 port-unreachable. Return stable fixed slice dev+inode identity only after fullmatch and before/after stat; capoutput while reading, bound processdeadline/reap. No install, no userfirewall changes, no arbitrary privileged operands.

**Files:** distractions-nft, tests/test_nft.py
**Touches:** distractions-nft, tests/test_nft.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_nft

## Acceptance
- Full policy equality preserves rule order, hooks,priorities, ports, addresssets and cgroup ancestorlevel; extra/missing/modified objects reject verification.
- Equal addresses in different order verify; malformed addresses and arbitrarycommands refuse.
- Before/after fixed cgroupstat identity stable; missing/recreated slice cannot certify a priorbaseline.
- Bounded stdout/stderr consumption and deadline with terminate/reap; failures return nonzero, never positiveproof.
- Real disposable namespace test applies/checks expectedpolicy, mutates actualrule/table, detectsdrift, repairsandchecks; hostfirewall untouched.


## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
