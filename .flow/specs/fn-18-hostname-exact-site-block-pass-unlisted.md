# Hostname-exact site block: pass unlisted connections through

## Conversation Evidence

> user: "safebrowsing.google.com was just blocked but i never opened it"
> user: "do we need a spec that moves away from ips? we can't have this collateral damage."

## Goal & Context

<!-- scope: business -->

Only listed hostnames fail. Today the site block drops every address a listed host resolves to, and Google, Cloudflare, and Fastly front many products on the same addresses, so blocking YouTube also refused Chrome's Safe Browsing updates on 2026-09-02 and raised a banner for a hostname nobody opened. After this spec a connection to a shared address is refused only when the hostname the client asked for is a listed host or a subdomain of one; every other hostname on that address reaches its real destination unchanged. The block page, the banner, and the fast HTTPS failure keep their behavior for listed hostnames.

## Architecture & Data Models

<!-- scope: technical -->

**Today's path.** `distractions-nft` puts resolved addresses in `omarchy_ds_v4` / `omarchy_ds_v6`; a nat output chain redirects TCP 80 to 28080 and TCP 443 to 28443 for set members, and a filter output chain rejects every other port. The listener's feedback servers (`ds/feedback.py`) answer on those two ports: a block page on 80, a TLS ClientHello read and close on 443.

**Pass-through.** The two feedback servers become hostname routers. On accept, the listener recovers the original destination with `SO_ORIGINAL_DST` (IPv4) or `IP6T_SO_ORIGINAL_DST` (IPv6) from the redirected socket, reads the Host header (80) or the SNI (443, ClientHello only, bounded as today), and decides:

- **Listed** (the hostname equals a host in the active expansion's `hosts`, or ends with `.` plus one, ignoring case and a leading `www.`): today's behavior, block page or close, origin-aware banner from fn-15.
- **Unlisted or unreadable hostname**: open a TCP connection to the original destination and splice bytes both ways, including the bytes already read, until either side closes; per-connection idle timeout 120 s; at most 256 concurrent splices, beyond which the connection is closed. Nothing is decrypted or logged beyond a rate-limited count.

**The outbound exemption.** The listener's own outbound sockets would hit the same redirect. `distractions-nft` gains one rule ahead of the redirects and the reject: `tcp sport 60000-60999 accept` (both families). The listener binds every splice socket to a free local port in that range (`bind(("0.0.0.0", port))` before `connect`, retrying on `EADDRINUSE`), so only its splices are exempt. `sudo -n` re-runs of `replace` and `flush` carry the new rule; `setup` refreshes the wrapper.

**Config.** `site_block.pass_through` (boolean, default true) lets a person fall back to the address block; `status --json` gains `pass_through: on|off|unavailable` (unavailable when the servers failed to bind, in which case redirected connections fail as today).

**Non-web ports.** UDP and other TCP ports on set members stay rejected (QUIC falls back to TCP 443). This keeps the wrapper small; a listed host's non-web traffic is not the case this spec fixes.

## Edge Cases & Constraints

<!-- scope: technical -->

- `SO_ORIGINAL_DST` fails (not redirected, direct hit on 28080/28443): treat as listed-path behavior for a Host/SNI that is listed, otherwise close; never splice to an unknown destination.
- Destination unreachable or connect timeout (5 s): close the client; one rate-limited log line per destination per minute.
- Splice cap reached: close new connections, one log line per minute.
- The listener exits: the redirect rules remain until `flush`, so redirected connections are refused, which is today's behavior; the listener's clean exit keeps flushing on space entry as before.
- IPv6 original destination recovery uses `IP6T_SO_ORIGINAL_DST` (value 80 on Linux, level `IPPROTO_IPV6`).
- Bound source port exhaustion (1000 in flight): treated as cap reached.
- Tests drive both servers with a fake destination server on loopback and assert splice, listed refusal, hostname suffix matching, the port-range binding, the cap, and the `SO_ORIGINAL_DST` failure path (monkeypatched); the wrapper test asserts the accept rule precedes the redirect and reject rules.

## Quick commands

```bash
python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
```

## Acceptance Criteria

<!-- scope: both -->

- **R1:** A redirected TCP 443 connection whose SNI is not a listed host or subdomain reaches its original destination unchanged (bytes both ways), and a redirected TCP 80 connection whose Host header is unlisted does the same. Errors: destination unreachable closes the client and logs once per destination per minute.
- **R2:** A redirected connection whose hostname is a listed host or a subdomain of one keeps today's behavior: block page on 80, close on 443, origin-aware banner. Errors: none.
- **R3:** The wrapper accepts TCP source ports 60000 to 60999 ahead of the redirect and reject rules in both families, and the listener binds every splice socket in that range. Errors: range exhausted counts as cap reached.
- **R4:** At most 256 splices run at once; the 257th connection is closed and logged once per minute. Errors: none.
- **R5:** `site_block.pass_through: false` restores today's address block with no splicing; `status --json` reports `pass_through`. Errors: bind failure yields `unavailable` and today's behavior.
- **R6:** Live check on this machine: with YouTube listed and the person off the space, `curl https://safebrowsing.google.com/` returns the real server's response and no banner appears, while `curl https://youtube.com/` fails fast with a banner. Recorded by the conductor.

## Boundaries

<!-- scope: business -->

- No TLS interception, no certificates, no decryption.
- DNS is unchanged; the address sets are unchanged.
- The wrapper remains the only privileged component; the accept rule is its only new line.

## Decision Context

<!-- scope: both -->

The user rejected collateral blocking on 2026-09-02. Rejected here: a DNS-level block (bypassed by browser secure DNS, and the legacy tree's 1,400-line stack was removed for that reason), and removing shared-address products from the list, which hides the problem in the catalog.
