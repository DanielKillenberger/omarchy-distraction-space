---
satisfies: [R3]
---
# fn-18-hostname-exact-site-block-pass-unlisted.1 Wrapper: accept the listener's splice source-port range ahead of redirect and reject

## Description
In distractions-nft, add `tcp sport 60000-60999 accept` for ip and ip6 as the first rules of both the filter output chain and the nat output chain, so the listener's splice sockets (bound in that range) bypass the reject and the redirect. Update tests/test_nft.py to assert the accept lines precede the redirect and reject lines in the rendered ruleset for both families. No other wrapper change.

**Touches:** distractions-nft, tests/test_nft.py

## Acceptance
R3's wrapper half: rendered ruleset has the accept rules first in both chains and both families; tests pin the order; suite green.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
