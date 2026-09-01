---
satisfies: [R2, R11]
---
# fn-9-rewrite-one-contained-distraction-space.3 Site block: resolver, nft wrapper with redirect and reject, wrapper install

## Description
Implement `ds/net.py` (2 s per-host resolution in a worker, last-good merge in `addrs.json`, `keep_reachable` subtraction, `replace`/`flush` via `sudo -n distractions-nft`, `site_block` state on/off/unavailable with one notice) and rewrite `distractions-nft` per fn-8: same `replace|flush ds` interface and address-only stdin, table `inet omarchy_ds` with v4/v6 sets, filter output chain rejecting set members (tcp reset / icmp unreachable), nat output chain redirecting tcp 80 to 28080 and tcp 443 to 28443. Implement the wrapper half of `ds/setup.py`: content compare, `sudo install -D -m 0755`, sudoers render + `visudo -cf` + `sudo install -m 0440`, refuse user-writable ancestors, `--remove`.

**Files:** `ds/net.py`, `distractions-nft`, `ds/setup.py`, `install/sudoers.omarchy-distraction-space`, `tests/test_net.py`, `tests/test_nft.py`, `tests/test_setup.py`.

## Acceptance
- Rendered ruleset contains both redirect rules per family and reject verdicts; empty sets render a table that matches nothing.
- Unresolvable hosts keep last-good; an empty final set sends `flush`, never an empty `replace`.
- Wrapper refuses any argv or stdin outside the contract with exit 2.
- Setup is idempotent, refuses a user-writable destination chain, and `--remove` reverses it; a denied sudo leaves no partial grant.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
