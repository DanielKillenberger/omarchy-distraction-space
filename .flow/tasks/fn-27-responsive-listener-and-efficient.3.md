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
Added fixed read-only `check ds` with the same capped address-only stdin as replace. It compares the complete rendered policy against bounded nft text, retains rule boundaries/order and every token, normalizes address-set ordering and only the expected numeric priorities/reject expansions, and certifies stable before/after slice dev/inode identity.

Success is exit 0 and one JSON object `{"dev": integer, "ino": integer}`. All verification failures return nonzero without success JSON. Listing uses fixed argv `nft -y list table inet omarchy_ds`, DEVNULL stdin, merged output capped while reading at 1 MiB, a 5-second deadline, process-group kill and child reap. Numeric cgroup fallback is conservatively rejected: the full expected level-5 path must be present.

Empty check input verifies an installed empty-set table and still needs the slice. It does not certify table absence/off policy. Network reconciliation must continue its existing flush path for empty desired policy; root conductor was notified. Replace/flush rendering remains unchanged.

Baseline: green, 12 tests. New positive check regression failed red for the unsupported verb before implementation. Final focused suite: 18 tests pass, covering full-policy drift, order, cgroup level/path/numeric fallback, slice identity change/missing slice, input caps and operands, listing overflow on stdout/stderr, launch failure/nonzero/invalid UTF-8, timeout with open/closed pipes, and reap. See evidence JSON for logs.

Actual disposable user/network namespaces verified apply/check, extra-rule and missing-table drift, repair, empty and 4096-address sets. Packet test retained outside-slice rejection (curl rc7/HTTP000) and inside-slice HTTP200. No host firewall mutation or installation occurred.

Grok 4.6 high mechanical bridge was attempted but stalled eight minutes after initial reads without edits; it was terminated and the session model implemented the specified security design. Bridge log: /tmp/fn27-3-grok.log.

stage: impl-review - skipped(policy: parallel-wave - conductor owns the gate)

Task remains in_progress; shared lifecycle and gate receipts are deferred to the conductor. Changes are committed in the assigned isolated workspace.

Added durable opt-in LiveNftTests in tests/test_nft.py. Set DS_LIVE_NFT_TEST=1 to run real wrapper/nft operations solely inside unshare --user --map-root-user --net; unavailable tools, real slice, or namespace support skip explicitly. A non-optional runtime guard rejects the parent network namespace before any nft operation, and PYTHONOPTIMIZE is cleared so child assertions remain active.

The test applies and checks the policy, compares JSON dev/inode to the real slice stat, records the actual nft listing, adds a rule and deletes the table, verifies both drift cases fail without stdout, repairs each, and checks empty/4096-address sets. Captured real listing in /tmp/fn27-3-followup-verify.log contains numeric priorities 0/-100, level-5 quoted cgroup path, source ports61000-61999 and icmp/icmpv6 port-unreachable expansions.

Cleanup now skips killpg after proc.wait has recorded a return code, avoiding the root PID-reuse hazard. Timeout/output-failure paths still kill before reaping, including the forked-child case. New successful-listing cleanup regression failed red before this fix; ordinary suite passes with one opt-in skip and live-enabled focused suite passes all20 tests.

stage: impl-review - skipped(policy: parallel-wave - conductor owns the gate)

Only this follow-up commit appears in the adjacent evidence file. Task stays in_progress; conductor reviews and completes.

Conductor integration: 433 tests passed (one intentional live-test skip). Fable implementation review SHIP (claude-fable-5-1). stage: impl-review - ran (model: claude-fable-5-1).
Live wrapper validation: 20 tests passed with DS_LIVE_NFT_TEST=1 in disposable network namespace.
## Evidence
- Commits: 2eb905f51da3f8175d134ce8137b6ea605d30e6c, f22fa25e92d051b492dd4dc2b1fc7fbbec0fabb4
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (433 passed, 1 skipped), PATH=/usr/bin:$PATH DS_LIVE_NFT_TEST=1 python3 -m unittest tests.test_nft (20 passed)
- PRs: