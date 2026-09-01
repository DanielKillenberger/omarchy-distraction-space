---
satisfies: [R1, R2, R5]
---
# fn-8-off-space-block-feedback-page-and.2 Listener feedback servers: HTTP block page and TLS SNI banner

## Description
Add the two loopback feedback servers the redirect chain lands on, started as daemon threads from `listen()` (spec §Listener-owned feedback servers; R1, R2, and R5's bind-failure half). Split from the wrapper task: different files, independently testable without root.

**Size:** M
**Files:** `distractions`, `tests/test_feedback_servers.py`
**Touches:** [distractions, tests/test_feedback_servers.py]

### Approach
- Port/timeout/byte-cap constants go in the top constants block near `BANNER_DEBOUNCE_S`/`NFT_WRAPPER` (`distractions:183-195`).
- HTTP server (28080): raw socket accept; per-connection daemon thread per the `handle_reload_conn` dispatch shape (`distractions:1786`); bounded read (~2s settimeout, byte cap) of the request head; extract Host header; respond with the self-contained block page (host HTML-escaped, fallback "this site", Super+D + Super+Ctrl+Shift+F copy per spec) and close. Garbage/timeout → close.
- TLS catcher (28443): same accept/thread/bounded-read shape; parse TLS ClientHello SNI (record header → handshake → extensions → server_name) with pure byte slicing; close; on parsed SNI call the NEW banner helper — `notify("Blocked on this workspace", f"{host} opens in the distraction space — Super+D.")` behind its own hostname-keyed debounce dict using `BANNER_DEBOUNCE_S` (do NOT reuse `maybe_banner()` at `distractions:1433` or its `_banner_at`). Handlers run concurrently, so the debounce check-and-stamp must be atomic under one `threading.Lock` — a check-then-set without the lock lets parallel ClientHellos (one page load opens several) all pass the check and stack banners.
- Server startup: one idempotent starter per the `start_stream_watcher()` guard pattern (`distractions:3821-3827`), called from `listen()` right after `start_stream_watcher()` (`distractions:4150`), before the socket2 loop. Bind 127.0.0.1 and ::1 per server (up to 4 sockets); a failed family is skipped, any failure notifies once via `notify()` (`distractions:269`), and `listen()` always continues. NOTE: fn-6.2 is editing `listen()`'s select loop concurrently — rebase onto latest main before touching `listen()`.

### Investigation targets
**Required** (read before coding):
- `distractions:4141-4213` — listen() startup ordering and loop
- `distractions:3821-3827` — idempotent thread-starter guard pattern
- `distractions:1786-1815` — per-connection handler + dispatch shape
- `distractions:1433-1438` and `distractions:187-188` — fn-4 debounce shape to mirror (not reuse)

**Optional** (reference as needed):
- `tests/test_edit_list.py:39-46` — SourceFileLoader import of `distractions` for unit tests
- `distractions:269-284` — notify() absorb semantics

### Key context
SNI lives in the first TLS record: ClientHello extensions, extension type 0x0000, entry type 0 (host_name). Parse defensively — every length field checked against the buffer; any malformed structure returns None. Browsers may send preconnects with no SNI or immediate FIN — both are the silent-close path.

## Acceptance
- [ ] SNI parser unit tests: valid ClientHello (host extracted), truncated at every length boundary, garbage bytes, TLS-without-SNI — no exceptions, None on failure
- [ ] Block page test: names the host, HTML-escapes a hostile Host header, falls back to "this site", contains Super+D copy
- [ ] Live-socket test: real servers on ephemeral test ports — HTTP request gets the page; TLS-catcher connection closes fast; slow/garbage client is closed by the bounded read
- [ ] Banner debounce is lock-guarded and atomic: a concurrent test fires many parallel ClientHellos for one host and asserts exactly one notify; sequential repeat inside the window → one notify; different hosts → independent; keyspace separate from `_banner_at`
- [ ] Bind-failure test: occupied port → one notify, listener path continues, other family/server still serves
- [ ] `python3 -m pytest tests/ -q` passes

## Done summary
Superseded, not implemented. The redirect-and-reject wrapper, the block page, the SNI banner, and the entry confirm are carried unchanged into fn-9-rewrite-one-contained-distraction-space (R2, R4, tasks .3, .4, .5). This task was written against the old single-file script, whose `enter()` and `listen()` anchors fn-9 deletes, so no code was written here.
## Evidence
- Commits:
- Tests:
- PRs: