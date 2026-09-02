---
satisfies: [R3]
---
# fn-18-hostname-exact-site-block-pass-unlisted.1 Wrapper: accept the listener's splice source-port range ahead of redirect and reject

## Description
In distractions-nft, add `tcp sport 61000-61999 accept` for ip and ip6 as the first rules of both the filter output chain and the nat output chain, so the listener's splice sockets (bound in that range) bypass the reject and the redirect. Update tests/test_nft.py to assert the accept lines precede the redirect and reject lines in the rendered ruleset for both families. No other wrapper change.

**Touches:** distractions-nft, tests/test_nft.py

## Acceptance
R3's wrapper half: rendered ruleset has the accept rules first in both chains and both families; tests pin the order; suite green.

## Done summary
`distractions-nft` now renders `meta nfproto ipv4|ipv6 tcp sport 60000-60999 accept` as the first
two rules of both `chain output` (filter) and `chain output_nat` (nat), ahead of every reject and
redirect, so the listener's splice sockets from fn-18 task 2 leave the machine untouched by the
site block. `tests/test_nft.py` gains one test that slices the rendered script into its two chain
bodies and pins, per family and per chain, that the accept is the chain's first rule and precedes
both rejects and both redirects.

Implemented by Grok (grok-4.6 via CLI bridge) on a single pass; tests run, red-checked, and
committed by the worker.

R3 (wrapper half) satisfied. The listener-side source-port binding is task 2 and is untouched here.

### Gates

- baseline: green via handoff (239 tests OK at 7f009b8)
- `flowctl gate classify --base 7f009b8` -> FULL (unmatched: distractions-nft)
- full suite on the committed tree: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests`
  -> 240 tests, OK (suite_rc=0); receipt `.flow/tmp/green-receipts/3fdb232a-unittest.json`
- red-check: with the accepts relocated below the reject/redirect rules the new test fails with
  6 subtest failures, so the test pins order rather than presence. Reverted before commit.

### For the conductor

- **nft syntax is not kernel-validated here.** `nft -c -f -` fails in this sandbox with
  `netlink: Error: cache initialization failed: Operation not permitted`, so
  `test_nft_check_skips_without_cap` took its documented skip path. Recorded as INCONCLUSIVE, not
  green. `meta nfproto ipv4 tcp sport <lo>-<hi> accept` is standard inet-table syntax, but the
  live check in R6 is the first real parse of these two lines.
- **Ephemeral-range overlap, spec-level, out of scope for this task.** Linux's default
  `net.ipv4.ip_local_port_range` is 32768-60999, so the accepted range 60000-60999 sits inside it:
  an ordinary outbound connection that happens to draw a source port in the last 1000 ports
  bypasses the site block. Roughly a 3.5% chance per connection against the default range. The
  spec fixes 60000-60999 in R3 and the task says "no other wrapper change", so I implemented it as
  written. Worth a decision before the live check: either narrow the range above
  `ip_local_port_range`'s ceiling, or reserve it via `net.ipv4.ip_local_reserved_ports`, or accept
  the leak as the cost of the pass-through.
- A stale `__pycache__/distractions-nft*.pyc` from my red-check briefly produced a false red on a
  correct tree (mutated and restored sources were the same byte length). Cleared; the final green
  ran against cleared caches on a clean tree. Flagged only so a repeat of that symptom is not
  misread as a real failure.

stage: impl-review - skipped(policy: host-deferred + parallel-wave - conductor owns the gate)

### Integration (conductor)

Fast-forwarded onto the spec branch unchanged as 3fdb232. The conductor then moved the exempt range to 61000-61999 in 325708f: the worker's ephemeral-range note was confirmed on this machine (`net.ipv4.ip_local_port_range` = 32768-60999), so the spec's 60000-60999 gave any program's outbound connection about a 3.5 percent chance of an exempt source port. Spec R3, both task briefs, and the spec's Decision Context record the move. Review round 1 (cursor, gpt-5.6-sol-high) returned NEEDS_WORK with four findings, all in the peer task's router; fixed in 99dbe55 and re-reviewed to SHIP. Integrated-target verification: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at 99dbe55, 255 tests, OK (receipt .flow/tmp/green-receipts/99dbe552-unittest.json).

stage: wave-dispatch - ran [2 tasks, native worktrees, disjoint Touches, no join collision]
stage: impl-review - ran [round 1 NEEDS_WORK, round 2 SHIP] (model: gpt-5.6-sol-high via cursor; AGENTS.md reviewer pin, reached through the cursor backend because in-host subagents cannot run it)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 3fdb232a19d0e188372b6a773390eae8074390b3, 325708f858b88ddbacee9c18ccb7a6200c7ab865, 99dbe55213265fe1d7b1e9f6afe2c96e8a18088e
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests -> 240 tests, OK (baseline 239 OK at 7f009b8; +1 new ordering test), red-check: accepts relocated after reject/redirect -> new test fails with 6 subtest failures, then reverted, INCONCLUSIVE: nft -c -f - kernel syntax check unavailable in sandbox (netlink cache initialization failed: Operation not permitted); test_nft_check_skips_without_cap took its documented skip path, PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (integrated target 99dbe55: 255 tests, OK; receipt .flow/tmp/green-receipts/99dbe552-unittest.json)
- PRs: