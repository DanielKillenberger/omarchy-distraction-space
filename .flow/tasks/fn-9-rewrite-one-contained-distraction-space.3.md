---
satisfies: [R2, R11]
---
# fn-9-rewrite-one-contained-distraction-space.3 Site block: resolver, nft wrapper with redirect and reject, wrapper install

## Description
Implement `ds/net.py`: `resolve_batch(hosts, generation, reason)` on a `ThreadPoolExecutor(8)` with a 2 s per-host timeout and a 10 s batch deadline (pending hosts fall back to last-good), last-good merge in `addrs.json`, `keep_reachable` subtraction, `apply(addresses)` calling `replace`/`flush` via `sudo -n distractions-nft`, `site_block` state on/off/unavailable with one notice, and one log line per batch (generation, reason, host count, resolved and failed counts, stale/coalesced marker, apply result, elapsed ms). The listener (task 7) owns generation bookkeeping and the on-space recheck; this module exposes pure batch functions it can drive. Rewrite `distractions-nft` per fn-8: same `replace|flush ds` interface and address-only stdin, table `inet omarchy_ds` with v4/v6 sets, filter output chain rejecting set members (tcp reset / icmp unreachable), nat output chain redirecting tcp 80 to 28080 and tcp 443 to 28443. Implement all of `ds/setup.py`: content compare, `sudo install -D -m 0755`, sudoers render + `visudo -cf` + `sudo install -m 0440`, refuse user-writable ancestors, `--remove`, then `omarchy-shell shell rescanPlugins` as the last step for both install and remove; a missing or failing rescan leaves files in place, prints the failure, and exits 1. Tests use fake `sudo`, `visudo`, `omarchy-shell` binaries on PATH.

**Files:** `ds/net.py`, `distractions-nft`, `ds/setup.py`, `install/sudoers.omarchy-distraction-space`, `tests/test_net.py`, `tests/test_nft.py`, `tests/test_setup.py`.

**Touches:** [ds/net.py, ds/setup.py, distractions-nft, install/**, tests/test_net.py, tests/test_nft.py, tests/test_setup.py]
## Acceptance
- Rendered ruleset contains both redirect rules per family and reject verdicts; empty sets render a table that matches nothing.
- Unresolvable hosts keep last-good; a batch past its 10 s deadline returns with pending hosts on last-good; an empty final set sends `flush`, never an empty `replace`.
- Every batch writes one log line with generation, reason, counts, apply result, and elapsed ms.
- Wrapper refuses any argv or stdin outside the contract with exit 2.
- Setup is idempotent, refuses a user-writable destination chain, runs the rescan last, and `--remove` reverses it; a denied sudo leaves no partial grant; a failed rescan leaves files installed and exits 1.
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
