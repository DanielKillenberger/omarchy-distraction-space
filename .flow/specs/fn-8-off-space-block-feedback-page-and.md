# Off-space block feedback page and conscious entry confirm

## Conversation Evidence

> user (turn 1): "i want that when i'm not on ws d that a page shows up telling me that i can't access this page on this workspace. Pls switch to super + d or smth. Make sure I actually want to enter distraction space."

## Overview

Today the always-on off-space site block (fn-4 R8) silently drops packets to listed-site addresses: the browser hangs until timeout and nothing tells the user why. This spec turns that silence into feedback. Off-space, plain-HTTP requests to a listed site land on a local block page that names the host and says to switch with Super+D. HTTPS attempts fail immediately (no hang) and a helper banner names the host and says the same thing — a real HTTPS page is impossible without a man-in-the-middle CA, which stays rejected. Everything else to listed addresses (QUIC, other ports) is rejected fast instead of dropped. Separately, Super+D entry onto the distraction space now asks for confirmation, so entering is a conscious choice, not a reflex keypress. Focus mode still locks the space exactly as today; the confirm runs only after focus is off.

## Goal & Context
<!-- scope: business -->

The person using this plugin already has the plugin-owned list, the always-on off-space site block, and the focus-mode lock. Winning is: an off-space attempt to open a listed site produces immediate, legible feedback ("you can't open x.com on this workspace — Super+D for the distraction space") instead of a hung tab, and pressing Super+D to enter the space asks "do you actually want this?" before switching. Leaving the space stays a plain keypress. Focus mode keeps its existing lock and its existing unlock flow; this spec adds nothing to focus mode.

## Architecture & Data Models
<!-- scope: technical -->

**Redirect instead of silent drop.** The privileged wrapper `distractions-nft` renders table `inet omarchy_ds` on every `replace ds` (`render_table` at `distractions-nft:43-61`). Extend that render with a second chain: `chain output_nat { type nat hook output priority dstnat; }` holding `ip daddr @omarchy_ds_v4 tcp dport 80 redirect to :28080`, `ip daddr @omarchy_ds_v4 tcp dport 443 redirect to :28443`, and the `ip6` twins. The existing filter chain changes its two `drop` verdicts to `reject` (default reject, ICMP/ICMPv6 unreachable; `reject with tcp reset` for TCP) so leftover traffic — QUIC udp/443, native-app ports — fails fast instead of hanging. NAT translation of established connections is applied by conntrack before the filter hook sees the packet, so redirected flows (daddr rewritten to loopback) never hit the reject rules. The redirect ports are fixed constants inside the wrapper; the wrapper interface stays exactly `replace|flush ds` with one address per stdin line, the same address validation, and the same table confinement. `flush ds` still empties both sets; empty sets match nothing, so on-space there is no redirect and no reject. The wrapper file changes, so an existing install must get the new wrapper into `/usr/local/libexec`; until then the old wrapper keeps the old drop behavior and nothing breaks. README says to re-run `distractions setup` after a plugin update — but today's `setup_privileged_helper()` returns early whenever the installed wrapper's sudo grant works (`_wrapper_grant_ok()` at `distractions:3928-3947`), so that re-run is currently a no-op on existing installs. fn-7 (in flight) replaces exactly this: its repairable case is "trusted ancestors, dest missing or byte/metadata mismatch", i.e. a content-mismatched installed wrapper gets replaced. This spec therefore depends on fn-7 (recorded dep edge) and changes wrapper content only, never the install flow.

**Listener-owned feedback servers.** `listen()` at `distractions:4141` gains two daemon-thread servers started before the socket2 loop, both binding IPv4 loopback and IPv6 loopback (redirect keeps the family: v4 flows arrive on 127.0.0.1, v6 on ::1):

- HTTP feedback server on port 28080. Any request gets a self-contained block page (inline CSS, no external assets, dark-and-light friendly): the requested host (from the `Host` header, HTML-escaped, falling back to "this site"), the line that it cannot be opened on this workspace, and the instruction — Super+D opens the distraction space; if focus mode is on, Super+Ctrl+Shift+F first. The request read is bounded like the TLS catcher's (~2 seconds, byte-capped); non-HTTP or truncated input just closes the connection. Connection closes after the response.
- TLS catcher on port 28443. Accept, read the ClientHello with a short timeout (~2s, bounded bytes), best-effort parse the SNI `server_name`, close immediately. The browser gets a fast connection-closed error instead of a timeout. When an SNI host was parsed, show a helper banner via `notify()`: title `Blocked on this workspace`, body `<host> opens in the distraction space — Super+D.` Debounce one banner per host per 30 seconds. This is a NEW notify call with its own debounce dict keyed by hostname — it reuses the debounce shape and `BANNER_DEBOUNCE_S` (`distractions:187-188`) but never `maybe_banner()` itself (`distractions:1433-1438`), whose title/body are the fn-4 app-intercept copy and whose `_banner_at` keyspace is product names, not hostnames. Because handlers run on concurrent threads (unlike fn-4's single-threaded socket2 loop), the debounce check-and-stamp is atomic under one lock — parallel ClientHellos from a single page load must still yield exactly one banner. No SNI parsed → close silently, no banner.

Each accepted connection is handled on its own daemon thread, following the per-connection dispatch pattern used for reload connections (`handle_reload_conn` at `distractions:1786`); the bounded read caps how long any handler lives, so a burst of parallel asset requests neither queues behind a serial accept loop nor leaks threads. Server threads never take down `listen()`: any per-connection exception is swallowed. Bind granularity is per socket: each server binds up to two sockets (127.0.0.1 and ::1); a family whose bind fails is skipped while the other keeps serving, and any bind failure notifies once ("Block-page server unavailable") and continues — the nft redirect then lands on a closed port, which is an immediate connection refused, still a fast fail. The servers are dumb responders: they do not consult the list, workspace, or focus state; the kernel only redirects traffic when the sets are populated, i.e. off-space with listed hosts.

**Interplay with focus mode.** While focus is on, the fn-1 `/etc/hosts` sinkhole maps listed hosts to `0.0.0.0`/`::`, so the browser never dials a listed address and the redirect never sees the flow; the attempt fails fast as today. This spec's page and banner cover the focus-off case, which is exactly when Super+D is available and the message is actionable. `focus_block.py` and the `omarchy_focus` table are untouched. The existing sinkhole-address filters (`focus_block.py:539-549`) already keep `0.0.0.0` out of the `ds` sets.

**Conscious entry confirm.** `enter()` at `distractions:1985-1991` currently checks `on_distractions()`, then `is_focus()` → `blocked_message()`, then `show()`. Insert a confirmation between the focus check and `show()`: a zenity question dialog, title `Distraction space`, text `Enter the distraction space?`, OK label `Enter`, cancel label `Stay`, `--timeout 30`, following the existing zenity call shape (`prompt_list_editor` at `distractions:1841-1863`). Confirm (exit 0) → `show()`. Cancel (exit 1) or timeout (exit 5) → stay on the current workspace, no notification needed. Zenity missing or crashing (FileNotFoundError, other exit codes) → fail open: notify once that the confirm is unavailable and enter anyway — a broken dialog must not lock the user out of their own workspace. Two guards close the gaps a 30-second dialog opens: (1) after the dialog returns with confirm, re-check `is_focus()` and `on_distractions()` before `show()` — focus can turn on (fn-6 timer, manual toggle) while the dialog sits open, and the lock always wins; a re-check that finds focus on shows `blocked_message()` instead of entering. (2) Each keypress is a fresh `distractions toggle` process, so a non-blocking flock on a confirm lock file under `STATE_DIR` (the `LISTEN_LOCK` pattern at `distractions:4141-4150`) makes a second Super+D while a dialog is open exit silently — never two stacked dialogs. A non-interactive `distractions toggle` (no display, scripted) simply times out to Stay. The focus-locked path is unchanged and runs before any dialog (no dialog while focus is on). `hide()` (leaving), `toggle()`'s leave branch, Super+Alt+D window move, and the fn-2/fn-6 focus-toggle flow are untouched.

## Approach

- Extend `render_table` in `distractions-nft` with the nat output chain (two redirect rules per family, fixed ports 28080/28443) and swap the filter `drop` verdicts to fast rejects. Keep `parse_replace_stdin`, confinement checks, and the CLI surface identical.
- Add a small `feedback server` module region in `distractions`: an HTTP handler rendering the block page from the Host header, and a raw-socket TLS-ClientHello SNI parser (handshake record → ClientHello → extensions → server_name). No TLS library, no certificates, no response bytes on 28443.
- Start both servers as daemon threads from `listen()` after the lock is held, before the socket2 loop. Reuse `notify()` for the banner and the bind-failure notice, with the existing hardened absorb behavior.
- Add the zenity confirm to `enter()` with explicit exit-code handling and the fail-open path.
- README: describe the block page and banner, the HTTPS limitation (browser error page + banner, by design, no MITM CA), the entry confirm, and that updating the plugin requires re-running `distractions setup` once so the new wrapper is installed.
- Tests follow the fn-4 injected-command style in `tests/`: wrapper render assertions (nat chain present, redirect ports, reject verdicts, empty-set flush), SNI parser unit tests (valid ClientHello, truncated, garbage, no-SNI), block-page render (host escaping, fallback host), banner debounce, bind-failure absorb, and `enter()` confirm logic with a fake zenity (confirm, cancel, timeout as exit 5, missing binary, focus-flip re-check, flock no-op on a held lock). Fake zenity and fake `distractions-nft` binaries on PATH per `tests/test_edit_list.py:20-32`; `distractions` imported via `SourceFileLoader` per `tests/test_edit_list.py:39-46`; wrapper driven as a subprocess per `tests/test_distractions_nft.py:50-58`.

## Quick commands

```bash
python3 -m py_compile distractions distractions-nft
python3 -m pytest tests/ -q
```

Manual checks (real session, wrapper reinstalled via `setup`): off-space `curl http://x.com` returns the block page; off-space `curl https://x.com` fails fast and one banner names the host; `curl https://x.com` again inside 30s shows no second banner; on-space both load; Super+D off-space with focus off shows the confirm, Cancel stays, Enter switches; focus on still shows `blocked_message()` with no dialog.

## Boundaries
<!-- scope: business -->

- No MITM: no local CA, no certificate interception, no served bytes on the TLS port. The HTTPS "page" is the browser's own fast-fail error plus the helper banner. This is a hard boundary, not a gap.
- Focus mode is untouched: its lock, its reason-to-leave flow, the fn-1 network block, and the fn-6 popup stay as they are. No confirm dialog while focus is on (the lock message already covers it).
- The confirm gates entering only. Leaving the space, Super+Alt+D window moves, and the workspace cycle (Super+Tab) are unchanged.
- No per-tab or per-navigation browser integration (no extension, no Chrome policy files).
- The wrapper interface stays `replace|flush ds`; no new commands, no caller-supplied ports, no new sudoers surface.
- Banner text and block-page text name Super+D and (when relevant) Super+Ctrl+Shift+F consistently with the README key table.
- Killing already-open TCP flows stays out of scope. The death mode does change: a flow that crosses a workspace switch now dies by immediate reject (TCP reset) instead of a slow drop-timeout — accepted, not hidden.
- The feedback ports are plain loopback listeners: any local process can probe 127.0.0.1:28080 and learn the plugin is installed. Accepted — the page is static text and leaks nothing else.
- If some other local service already owns 28080/28443, the plugin's bind fails (notify-once path) and the redirect delivers blocked-site requests to that service. Accepted as a misconfiguration surface; the ports were picked to collide with nothing common.

## Decision Context
<!-- scope: both -->

fn-4 rejected SNI inspection as overkill for the *intercept banner* and declared "SNI or HTTP Host inspection is out of scope" for that spec. The user has now asked for exactly this feedback ("a page shows up telling me that i can't access this page on this workspace"), which is new evidence: the silent drop's UX is the problem being fixed. SNI parsing here is a ~40-line read-only parse on a loopback socket the kernel already redirected — not a packet-inspection subsystem.

A true HTTPS block page requires installing a trusted CA and terminating TLS for arbitrary sites (what corporate MITM proxies do). That is rejected: it would make the plugin a root-of-trust attack surface to solve a cosmetic problem. Nearly every listed host ships HSTS, so a self-signed-certificate answer would be an unbypassable browser error anyway — worse than a clean fast fail plus a banner that explains it. The HTTP page still matters: typed `http://` URLs and non-HSTS hosts get the full page, and the page is where the longer explanation lives.

`reject` replaces `drop` so native apps and QUIC fail in milliseconds instead of retry-looping; on the user's own outbound loopback-adjacent traffic there is no stealth value in drops.

Fixed wrapper-internal ports keep the sudoers surface closed: a caller-supplied port would let the unprivileged side redirect privileged-blocked traffic anywhere. 28080/28443 sit outside the default ephemeral range (32768+) and collide with nothing shipped.

The entry confirm is zenity to match the existing editor UI. Timeout counts as Stay: an unanswered dialog means the user walked away, and yanking them onto the distraction space minutes later would be the opposite of a conscious choice. Fail-open on a broken zenity: the block page, site block, and focus lock are the enforcement layers; the confirm is a speed bump, and a missing dialog tool must not brick workspace navigation. (fn-6 recorded a user preference against contingency UI for its own popups; this fail-open is a different surface — a keybind that must never dead-end — and is spec'd deliberately, not as contingency creep.)

The wrapper's `destroy table` + recreate on every `replace ds` leaves a sub-millisecond window with no rules on the 30-second periodic re-resolve — status quo inherited from fn-4, accepted; an atomic-swap rewrite is not worth the wrapper churn.

fn-6 (task .2 in progress) is editing `listen()`'s select loop concurrently; this spec's server-thread startup lands before the loop, an adjacent-but-distinct region. Merge-conflict risk only, no behavioral coupling — whichever lands second rebases; no dependency edge.

fn-7 is different: it is a real dependency. The R5 update story ("re-run setup once") only works after fn-7's setup repair path lands, because the current `setup_privileged_helper()` skips any install whose grant still works and would silently keep the old drop-only wrapper. The dep edge is recorded; fn-8 does not duplicate fn-7's freshness detection.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** While the active workspace is not the distraction space, an HTTP request to a listed site returns a local block page that names the requested host and says to switch with Super+D. Errors: an unreadable Host header falls back to a generic "this site"; non-HTTP or never-completing input hits the bounded read (~2s, byte-capped) and the connection just closes; a failed page render still closes the connection; the listener stays up.
- **R2:** While off-space, an HTTPS attempt to a listed site fails within a few seconds (no browser timeout hang) and, when an SNI hostname is readable, one helper banner (its own hostname-keyed debounce, not fn-4's product `_banner_at`) names the host and says Super+D opens the distraction space. Errors: no SNI → fast fail with no banner; repeat attempts inside 30 seconds — including concurrent parallel connections from one page load — do not stack banners (lock-guarded debounce); a notify failure never exits `listen()`.
- **R3:** Non-web traffic to listed addresses (QUIC udp/443, other ports) is rejected fast off-space. On the distraction space, all of it flows (sets empty via existing flush). Errors: none beyond fn-4 R8's existing apply/lift surface.
- **R4:** The privileged wrapper keeps its exact interface and confinement: `replace|flush ds`, address-only stdin, table `inet omarchy_ds` only, redirect ports hard-coded. Errors: any other argv or non-address input is refused exactly as today.
- **R5:** If the feedback servers cannot bind, the user is told once, `listen()` continues, and blocked web traffic still fails fast (connection refused on the redirect port). Bind failure is per socket: a failed family is skipped, the other keeps serving, the notice still fires once. A stale (pre-update) installed wrapper keeps the old drop behavior with no breakage; README tells the user to re-run `distractions setup` after update, and the setup that actually replaces a content-mismatched wrapper is fn-7's repair path (dep edge fn-8 → fn-7; verified by a stale-wrapper-replaced test in task .3 or referenced from fn-7).
- **R6:** Super+D onto the distraction space, with focus off, shows a confirmation; Enter switches, Cancel or a 30-second timeout stays put. Leaving the space is unchanged and never asks. Errors: zenity missing or crashing notifies once and enters anyway; while focus is on the existing lock message shows and no dialog appears; a confirm answered Enter after focus turned on mid-dialog re-checks and shows `blocked_message()` instead of entering; a second Super+D while a dialog is open is a silent no-op (flock guard), never a second dialog; a non-interactive invocation times out to Stay.

## Early proof point

First task: extend `render_table` and prove the rendered ruleset loads (`nft -c -f` dry-check — capability-aware, since check mode needs CAP_NET_ADMIN: run privileged manually, skip in unprivileged CI) with redirect + reject verdicts, and that a redirected `curl http://<listed-ip>` on a dev box lands on a local port. If output-hook redirect does not behave as expected on the running kernel, rethink before building the servers.

## Open Questions

None. HTTPS gets fast-fail plus banner, never a MITM page. Confirm is entry-only, fail-open, timeout-as-cancel. Wrapper update requires one `setup` re-run.

## Requirement coverage

| Req | Description | Task(s) | Gap justification |
|-----|-------------|---------|-------------------|
| R1 | Off-space HTTP attempts land on the local block page | fn-8-off-space-block-feedback-page-and.1, fn-8-off-space-block-feedback-page-and.2 | — |
| R2 | Off-space HTTPS fails fast with a debounced host banner | fn-8-off-space-block-feedback-page-and.1, fn-8-off-space-block-feedback-page-and.2 | — |
| R3 | Remaining traffic to listed addresses rejected fast; on-space flows | fn-8-off-space-block-feedback-page-and.1 | — |
| R4 | Wrapper interface and confinement unchanged, ports hard-coded | fn-8-off-space-block-feedback-page-and.1 | — |
| R5 | Bind-failure degradation + stale-wrapper compatibility + README setup re-run | fn-8-off-space-block-feedback-page-and.2, fn-8-off-space-block-feedback-page-and.3 | — |
| R6 | Confirmed conscious entry via Super+D, entry-only, guarded | fn-8-off-space-block-feedback-page-and.3 | — |


