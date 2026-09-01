---
satisfies: [R3, R4]
---
# fn-8-off-space-block-feedback-page-and.1 Wrapper redirect chain: nat output redirect to 28080/28443, drop to reject

## Description
Extend the privileged wrapper's rendered table with the nat redirect chain and swap the filter drops to fast rejects (spec §Redirect instead of silent drop; advances R1/R2 plumbing, satisfies R3/R4). Split out because it is the early proof point and touches only the wrapper + its test file, disjoint from the listener work.

**Size:** S
**Files:** `distractions-nft`, `tests/test_distractions_nft.py`
**Touches:** [distractions-nft, tests/test_distractions_nft.py]

### Approach
- In `render_table` (`distractions-nft:43-61`) add a `chain output_nat { type nat hook output priority dstnat; policy accept; }` with `ip daddr @omarchy_ds_v4 tcp dport 80 redirect to :28080`, `... tcp dport 443 redirect to :28443`, and the `ip6`/`@omarchy_ds_v6` twins; ports as module constants next to `SET4`/`SET6`.
- Swap the two filter `drop` verdicts to rejects: `reject with tcp reset` for TCP, default reject for the rest — keep the per-rule shape and `policy accept;` on the chain (spec gotcha: never a chain-level reject policy). Keep set-driven matching so empty sets are a no-op.
- Keep `parse_replace_stdin`, `commit()` confinement (`table inet omarchy_ds` substring), and the `replace|flush ds` CLI untouched — `test_setup.py`/`test_enforcement.py` assert those substrings.

### Investigation targets
**Required** (read before coding):
- `distractions-nft:43-61` — render_table to extend
- `tests/test_distractions_nft.py:16-134` — fake-nft subprocess harness and substring assertion style

**Optional** (reference as needed):
- `tests/test_setup.py`, `tests/test_enforcement.py` — other tests asserting wrapper substrings that must keep passing

### Key context
nftables inet-family nat output chains only see a connection's first packet; conntrack translates the rest before the filter hook, so redirected flows never hit the reject rules — no exception rule needed. `reject with tcp reset` is only valid on a rule that matches TCP; the non-TCP reject must stay a default (icmpx) reject on a separate rule. `nft -c -f` (check mode) still opens a netlink socket and needs CAP_NET_ADMIN, so an unprivileged run fails with a permission error, not a parse verdict — the dry-check test must treat permission-denied as a skip, not a failure.

## Acceptance
- [ ] Rendered script contains the nat output chain with all four redirect rules and hard-coded :28080/:28443
- [ ] Filter chain rejects (tcp reset for tcp dport rules' leftovers; default reject otherwise) — no `drop` verdicts remain
- [ ] `flush ds` renders both sets empty; empty sets match nothing (assert rendered shape)
- [ ] Wrapper refuses non-address stdin, other targets, other commands exactly as today (existing tests still pass)
- [ ] `nft -c -f` dry-check test is capability-aware: it runs only when `nft` exists and skips (never fails) on a missing binary OR a permission/netlink error; the privileged dry-check stays a documented manual step
- [ ] `python3 -m pytest tests/ -q` passes as an ordinary unprivileged user

## Done summary
Superseded, not implemented. The redirect-and-reject wrapper, the block page, the SNI banner, and the entry confirm are carried unchanged into fn-9-rewrite-one-contained-distraction-space (R2, R4, tasks .3, .4, .5). This task was written against the old single-file script, whose `enter()` and `listen()` anchors fn-9 deletes, so no code was written here.
## Evidence
- Commits:
- Tests:
- PRs: