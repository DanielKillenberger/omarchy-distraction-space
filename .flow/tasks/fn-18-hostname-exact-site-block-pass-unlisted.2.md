---
satisfies: [R1, R2, R3, R4, R5]
---
# fn-18-hostname-exact-site-block-pass-unlisted.2 Hostname router in the feedback servers: original destination, listed-host match, splice with caps, pass_through config and status

## Description
In ds/feedback.py turn the 28080 and 28443 servers into hostname routers: recover the original destination with SO_ORIGINAL_DST (IPv4, SOL_IP option 80) or IP6T_SO_ORIGINAL_DST (IPPROTO_IPV6, option 80); read the Host header or the SNI as today; a hostname equal to or ending in `.` plus a host in the active expansion (case-insensitive, leading `www.` ignored) keeps today's behavior (block page / close / fn-15 origin-aware banner); anything else is spliced to the original destination over a socket bound to a free local port in 61000-61999 (retry on EADDRINUSE), bytes both ways including those already read, 120 s idle timeout, connect timeout 5 s, at most 256 concurrent splices, one rate-limited log line per destination per minute on failure and one per minute when the cap is hit. Never splice when the original destination cannot be recovered. Add `site_block.pass_through` (bool, default true) to ds/config.py DEFAULTS and validation; when false the servers behave exactly as today. `status --json` gains `pass_through: on|off|unavailable` (unavailable when the servers failed to bind). Tests: a fake destination server on loopback for the splice; listed refusal; suffix matching incl. www; port-range binding; the cap; SO_ORIGINAL_DST failure (monkeypatched); config default and validation; status key (tests/test_status.py pins STATUS_KEYS). Do NOT edit README.md (fn-16 owns it right now); note the config key doc as a follow-up in the done summary.

**Touches:** ds/feedback.py, ds/config.py, ds/state.py, ds/listener.py, tests/test_feedback.py, tests/test_config.py, tests/test_status.py

## Acceptance
R1, R2, R4, R5 and R3's listener half hold with tests; suite green. R6 (live check) is the conductor's after merge.

## Done summary
The two feedback servers are hostname routers now: a redirected connection whose Host header or
SNI is a listed host or a subdomain of one keeps today's block page, close, and origin-aware
banner, and every other hostname is spliced to its real pre-redirect destination. `site_block.pass_through`
(default true) turns the router off, and `status --json` reports `pass_through` as on, off, or
unavailable.

Implemented by Grok (grok-4.6 via CLI bridge) from a self-contained prompt; this agent reviewed
the diff, closed two gaps, ran the suite, and committed.

### What landed

- **ds/feedback.py** — `_original_dst` recovers the pre-redirect address with `SO_ORIGINAL_DST`
  (IPv4, `SOL_IP` option 80) or `IP6T_SO_ORIGINAL_DST` (IPv6, `IPPROTO_IPV6` option 80).
  `_listed` matches a hostname against the active expansion's hosts, case-insensitively, ignoring
  a leading `www.`, a trailing dot, and a port, and accepting any subdomain. `_route` splices
  anything unlisted: a socket bound to a free port in 60000-60999 (the range the peer task's
  wrapper accepts), the bytes already read replayed first, 5 s connect timeout, 120 s idle
  timeout, 256 concurrent splices, one rate-limited log line per destination and one for the cap.
- **ds/config.py** — `site_block.pass_through` in DEFAULTS and in `validate`.
- **ds/state.py, ds/listener.py** — `pass_through` on the status payload, `unavailable` when the
  servers did not all bind.
- **tests** — 9 new tests; 248 total, OK (baseline at `7f009b8`: 239, OK).

### Worth the conductor's attention

**The self-address guard is load-bearing, and a test proved it.** The spec assumed
`SO_ORIGINAL_DST` raises `OSError` on a socket that was never redirected. On this kernel it does
not: it answers with the socket's **own local address**. Without the `_is_self` check a direct hit
on 28080/28443 would have spliced the listener to itself in a loop. The test now pins the real
behavior — a non-redirected accepted socket recovers its own address, and `_is_self` rejects it —
plus an end-to-end direct hit with nothing monkeypatched. This is the one place the implementation
diverges from the spec's stated edge case, and it diverges toward safety.

**Test-only port override.** The splice range is overridable through `DS_SPLICE_PORT_MIN` /
`DS_SPLICE_PORT_MAX`, following the file's existing `DS_FEEDBACK_HTTP_PORT` convention, so the
tests never bind the real 60000-60999 range on a live desktop. The tests still assert the
constants are 60000 and 60999.

### Follow-ups

- **README documents nothing about `site_block.pass_through` yet.** Spec fn-16 owns README right
  now, so this task deliberately did not write it. The key needs a row in the config table and a
  sentence in the site-block section once fn-16 lands.
- R6, the live check on this machine, is the conductor's step after merge and was not performed
  here.

stage: impl-review - skipped(policy: host-deferred - conductor owns the gate)

### Integration (conductor)

Cherry-picked onto the spec branch as 0a5fdf9 (workspace commit ccbe844). The conductor moved the splice range to 61000-61999 in 325708f, above the default ephemeral ceiling (see task 1's summary and the spec's Decision Context). Review round 1 (cursor, gpt-5.6-sol-high) returned NEEDS_WORK with three P1 findings, and task 1's review added two more on this file; all five fixed in 99dbe55 with one test each: a registry of live splice source ports plus a retry on a four-tuple collision at connect, routers bound whenever pass-through is on even with `nudges.block_page` off (listed hosts then close fast with no page and no banner), `stop()` no longer zeroes the splice counter under live splices, the SNI reader reassembles a ClientHello spanning several TLS records, and one suffix-aware `_entry_for_host` serves routing, banner identity, and origin attribution. Round 2 SHIP. Integrated-target verification: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at 99dbe55, 255 tests, OK (receipt .flow/tmp/green-receipts/99dbe552-unittest.json).

Not reachable from tests, noted for R6 and the README follow-up: with Encrypted Client Hello the outer SNI is the provider's public name, so a listed host behind ECH passes through; the `site_block.pass_through` config row and the 61000-61999 exemption still need README lines once fn-16's README lands on main.

stage: wave-dispatch - ran [2 tasks, native worktrees, disjoint Touches, no join collision]
stage: impl-review - ran [round 1 NEEDS_WORK, round 2 SHIP] (model: gpt-5.6-sol-high via cursor; AGENTS.md reviewer pin, reached through the cursor backend because in-host subagents cannot run it)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 0a5fdf9a1f8192d2a1d8be289b202defbb17588d, 325708f858b88ddbacee9c18ccb7a6200c7ab865, 99dbe55213265fe1d7b1e9f6afe2c96e8a18088e
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests  (248 tests, OK; baseline at 7f009b8 was 239 tests, OK), PATH=/usr/bin:$PATH python3 -m unittest tests.test_feedback (33 tests after the review fixes, OK), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (integrated target 99dbe55: 255 tests, OK; receipt .flow/tmp/green-receipts/99dbe552-unittest.json)
- PRs: