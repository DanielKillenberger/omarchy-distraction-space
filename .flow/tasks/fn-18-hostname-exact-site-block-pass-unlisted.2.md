---
satisfies: [R1, R2, R3, R4, R5]
---
# fn-18-hostname-exact-site-block-pass-unlisted.2 Hostname router in the feedback servers: original destination, listed-host match, splice with caps, pass_through config and status

## Description
In ds/feedback.py turn the 28080 and 28443 servers into hostname routers: recover the original destination with SO_ORIGINAL_DST (IPv4, SOL_IP option 80) or IP6T_SO_ORIGINAL_DST (IPPROTO_IPV6, option 80); read the Host header or the SNI as today; a hostname equal to or ending in `.` plus a host in the active expansion (case-insensitive, leading `www.` ignored) keeps today's behavior (block page / close / fn-15 origin-aware banner); anything else is spliced to the original destination over a socket bound to a free local port in 60000-60999 (retry on EADDRINUSE), bytes both ways including those already read, 120 s idle timeout, connect timeout 5 s, at most 256 concurrent splices, one rate-limited log line per destination per minute on failure and one per minute when the cap is hit. Never splice when the original destination cannot be recovered. Add `site_block.pass_through` (bool, default true) to ds/config.py DEFAULTS and validation; when false the servers behave exactly as today. `status --json` gains `pass_through: on|off|unavailable` (unavailable when the servers failed to bind). Tests: a fake destination server on loopback for the splice; listed refusal; suffix matching incl. www; port-range binding; the cap; SO_ORIGINAL_DST failure (monkeypatched); config default and validation; status key (tests/test_status.py pins STATUS_KEYS). Do NOT edit README.md (fn-16 owns it right now); note the config key doc as a follow-up in the done summary.

**Touches:** ds/feedback.py, ds/config.py, ds/state.py, ds/listener.py, tests/test_feedback.py, tests/test_config.py, tests/test_status.py

## Acceptance
R1, R2, R4, R5 and R3's listener half hold with tests; suite green. R6 (live check) is the conductor's after merge.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
