# Blocked-site banners only for off-space origins; hold push robustness

## Conversation Evidence

> user: "I get constant popups about x being blocked though. I guess that's X refreshing in distraction space or smth else?"
> user: "can we figure that these fetches happen from workspace d and therefore we shouldn't actually show the banner. We only want this to show up when something in another workspace tries to talk to those services"
> user: "i really need that spec to fix the popups about stuff being blocked while i'm on a normal workspace. It's annoying.."

## Goal & Context

<!-- scope: business -->

The "Blocked on this workspace" banner exists to catch the person reaching for a distraction from a normal workspace. Today it also fires for every background fetch made by a window that already sits on the distraction space (an X web app polling `api.x.com`, `abs.twimg.com`, and a dozen more hosts), one banner per host every 30 seconds. After this spec, a redirected connection whose origin is a window on the distraction space produces no banner, a connection from a window on any other workspace still does, and banners are debounced per catalog entry rather than per host.

Separately, the notification hold sometimes reports `unavailable` right after the listener starts and only recovers on the next reload or workspace change. The hold module logs to stderr, which the launcher discards, so the cause was never visible. The listener logs those failures to the state log and retries an unavailable push on its own.

## Architecture & Data Models

<!-- scope: technical -->

**Connection attribution** (`ds/feedback.py`, helpers in `ds/hypr.py`). Both feedback servers (HTTP on 28080, TLS on 28443) know the peer's source port from `accept`. `/proc/net/tcp` and `/proc/net/tcp6` map that local port (the client side of the redirected connection, remote port 80 or 443) to a socket inode; a scan of `/proc/<pid>/fd` for processes owned by the current uid maps the inode to a pid (the same data `ss -tnp` shows). Chromium opens sockets from a helper process, so the pid is walked up through `/proc/<pid>/status` PPid for at most eight steps until a pid that owns at least one Hyprland client (`hyprctl clients -j`, field `pid`) is found. The origin is **on-space** when every client of that pid has workspace name `distraction`. The origin is **off-space** when any client of that pid is elsewhere, or when no owning process or window can be found (fail toward showing the banner). `hyprctl clients` is read at most once per second and cached; the walk never blocks the accept loop for more than the read timeouts already in place.

**Entry fallback for shared browser processes.** One Chromium profile serves a web app on the distraction space and normal windows elsewhere through the same network process, so the pid walk alone says off-space. Before deciding, the SNI host (TLS) or Host header (HTTP) is mapped to its catalog entry through the active expansion (`hosts` lists, with a `www.` prefix ignored). If that entry has at least one window class, and at least one current client matches one of those classes, and every such client is on the distraction space, the origin is treated as on-space. An entry with no matching window anywhere stays off-space (a bare browser tab on a normal workspace).

**Debounce per entry.** The banner key is the catalog entry name (or the bare host when no entry matches), one banner per key per 30 seconds. The banner body names the entry ("X opens in the distraction space — Super+Ctrl+Shift+D."), the block page is unchanged.

**Hold robustness** (`ds/hold.py`, `ds/listener.py`). `hold._log` writes to the state log through the same helper `hypr._log` uses (timestamped line in `state_path("log")`), never stderr. The listener keeps the effective-hold logic; when `notification_hold` reads `unavailable`, every periodic tick (the existing 30 s cadence) retries `sync_hold(force=True)` until it returns `on` or `off`; the one-time notice stays one-time. `push` logs the failing IPC verb, key, and error text.

## Edge Cases & Constraints

<!-- scope: technical -->

- Peer port not found in `/proc/net/tcp*` (connection already closed) or inode not owned by this uid: off-space, banner shown.
- Owning process exits mid-walk: off-space.
- A process with windows on both the distraction space and elsewhere: off-space (the fallback may still rescue it through the entry's own windows).
- IPv6 peers and IPv4-mapped addresses: both tables are read; only the port is matched.
- `hyprctl` unavailable: attribution disabled for that connection, banner shown, one log line per minute at most.
- Debounce state is per listener lifetime, as today.
- Hold retry never spams: the notice fires once per listener lifetime; retries are silent apart from the log.

## Quick commands

```bash
python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
```

Redirect the suite to a file. A leaked child in one test keeps a pipe open, so piping the suite through `tail` stalls. Put `/usr/bin` first on PATH so the sandboxed fakes resolve the system python3, not the mise shim.

## Acceptance Criteria

<!-- scope: both -->

- **R1:** A redirected connection whose owning process (after the parent walk) has windows only on the distraction space produces no banner; one whose process has a window on another workspace, or that cannot be attributed, produces the banner. Errors: proc or hyprctl read failures fall toward showing the banner and log once per minute.
- **R2:** When the connection's host maps to a catalog entry with window classes and every window matching those classes is on the distraction space, no banner is shown even if the pid walk said off-space. An entry with no matching windows keeps the banner. Errors: none.
- **R3:** Banners are debounced per catalog entry name (bare host when unmatched) for 30 seconds, and the body names the entry. Errors: none.
- **R4:** `hold` failures appear in the state log with verb, key, and error; while `notification_hold` is `unavailable` the listener retries the push on each periodic tick until it succeeds, without a second notice. Errors: none.
- **R5:** Tests cover R1 to R4 with fixtures for `/proc/net/tcp`, `/proc/<pid>/fd`, `/proc/<pid>/status`, and `hyprctl clients`; the live check on this machine records an X web app polling from the distraction space with no banner and a `curl https://x.com` from a terminal on a normal workspace with a banner.

## Boundaries

<!-- scope: business -->

- The network block itself, the block page content, the hold semantics, mute, and summary are unchanged.
- No per-connection blocking exemption: on-space windows are still blocked while the person is off the space; only the banner is suppressed.
- No browser extension and no local CA.

## Decision Context

<!-- scope: both -->

The user chose on 2026-09-02 to keep the banner as the HTTPS feedback and to make it origin-aware rather than adding an in-browser page. Rejected: a global rate limit alone, because it hides the banner the person actually needs while the X web app keeps polling.

Wording fix 2026-09-02 (task 1 review, Opus): the R2 fallback applies only when the process that opened the connection itself owns a window matching the entry's classes, and all of those windows are on the distraction space. The literal "every window matching those classes" would also silence a terminal `curl https://x.com` while the X web app sits on the space, which R5 forbids. Accepted follow-ups from the same review: memoize the on-space verdict per banner key for about a second (the per-connection /proc/<pid>/fd scan costs ~60 ms), and do not hold the clients-cache lock across the hyprctl subprocess.
