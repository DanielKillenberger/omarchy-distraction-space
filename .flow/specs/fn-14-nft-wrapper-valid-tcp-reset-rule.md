# nft wrapper: valid TCP reset rule

## Conversation Evidence

> user: "ok then do it once now and then again once fn-10 is in" (running `distractions setup`; the refreshed wrapper then failed every flush and replace)

## Goal & Context

<!-- scope: business -->

After `distractions setup` installed the fn-9 wrapper, `site_block` went to `unavailable`: nftables 1.1.6 rejects the ruleset at parse time, so neither `replace ds` nor `flush ds` loads and the site block is off entirely. The unit tests run against a fake `nft` and only match strings, so the bad syntax passed.

## Architecture & Data Models

<!-- scope: technical -->

`render_table` in `distractions-nft` emits `ip daddr @<set> tcp reject with tcp reset` and the ip6 twin. nft needs a transport match before `reject with tcp reset`: `ip daddr @<set> meta l4proto tcp reject with tcp reset`. The redirect rules already carry `tcp dport` and are fine. Tests in `tests/test_nft.py` assert the corrected strings. A syntax check against the real `nft -c -f` needs CAP_NET_ADMIN, so the live proof is `sudo -n <wrapper> flush ds` and `replace ds` exiting 0 after install; record it in the done summary.

## Quick commands

```bash
python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
```

## Acceptance Criteria

<!-- scope: both -->

- **R1:** The rendered ruleset's TCP reset rules read `ip daddr @omarchy_ds_v4 meta l4proto tcp reject with tcp reset` and `ip6 daddr @omarchy_ds_v6 meta l4proto tcp reject with tcp reset`; the generic `reject` rules and the four redirect rules are unchanged. Errors: none.
- **R2:** On this machine, after `distractions setup` installs the wrapper, `sudo -n <wrapper> flush ds` and `replace ds` with one address both exit 0 and the listener reports `site_block: on`.

## Boundaries

<!-- scope: business -->

No other wrapper change. The fake-nft test double stays; a real-nft check is out of reach without root in tests.

## Decision Context

<!-- scope: both -->

Hotfix. Rejected: `tcp dport 0-65535 reject with tcp reset`, which is a roundabout way to say "TCP".
