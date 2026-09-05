# The space is a process group: one boundary for windows, links, network, and sound

> HTML render lens: [.flow/artifacts/fn-22-the-space-is-a-process-group-one/spec.html](../artifacts/fn-22-the-space-is-a-process-group-one/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Goal & Context
<!-- scope: business -->

Version 2 keeps distractions on one workspace, but it decides "inside or outside" by looking at which workspace the person is currently viewing. That single choice is the root of every inconsistency the person reports.

- The site block follows the cursor. Leave the space and the addresses go into nftables. Come back and they are flushed. A WhatsApp web app or a YouTube window left open on the space loses its network the moment the person switches to work, so chats stop syncing and pages error out ("auto updates in the distraction space get blocked"). Every workspace switch triggers a DNS batch, a sudo call, and a generation-counter race.
- Links land in the wrong place. A YouTube link clicked in Telegram opens a tab in the work browser on the work workspace. The tab is then blocked, a banner fires, and the person has to reopen the link by hand from the space. Doing the same thing from the space works, so the outcome depends on where the person happened to be standing.
- Web apps share one process with the work browser. On this machine on 2026-09-04 the WhatsApp and X web-app windows on the space and the work browser window on workspace 1 all carried process id 3463. No network rule can tell those windows apart, which is why version 2 grew 400 lines of peer-port to inode to pid to Hyprland-client attribution just to decide whether one banner should show.
- Banners are the sum of special cases. A window banner, an HTTPS banner with attribution, an HTTP block page, three debounce tables, and a provenance log with rate limits.
- Sound from web apps cannot be muted, because their audio comes from the shared browser's audio process (README, Limits).

Version 3 replaces "where is the person looking" with "which processes belong to the space". The space becomes a systemd slice as well as a Hyprland workspace. Everything the plugin launches into the space runs in `app-distraction.slice` under the person's user manager, and listed web products run in their own browser profile, which gives them their own process tree, their own window class, and their own audio streams. With that one boundary in place:

- Listed hosts are reachable from the slice, always, and unreachable from everything else, always. The block no longer changes when the person switches workspace. Apps on the space keep syncing while the person works. Nothing is resolved or applied on workspace changes.
- A link to a listed host, clicked anywhere, opens inside the space. The plugin registers itself as the URL handler, opens listed URLs in the distraction browser on the space without stealing focus, and forwards everything else to the previous browser untouched.
- One banner shape covers every case. "Opened in the distraction space" when something landed there while the person was elsewhere, "Blocked here" when a work process reached a listed host. Each carries one action that opens the thing in the space. The attribution machinery goes away because a blocked connection is, by construction, from outside the slice.
- Sound mute keys on slice membership first, so WhatsApp Web, Discord, and every other web app on the space can be muted while the person is away. The catalog's audio names stay as the fallback for apps started outside the slice.

The person asked whether the network block is needed at all. It is the only mechanism that catches the habit path, which is typing or autocompleting a listed site in the work browser. Links are better served by routing than by refusing, so version 3 routes links and keeps the block as a static backstop behind a config switch, on by default. Turning it off leaves windows, links, sound, and notifications working as designed.

Target user is the existing user base of the plugin on Omarchy 4 with a Chromium-family default browser. Version 3.0.0 lands on a branch and does not touch `main` while the 2.1.0 marketplace submission is open.

## Architecture & Data Models
<!-- scope: technical -->

**The space.** Two things define it and every component reads one of them.

- The Hyprland workspace `name:distraction`, unchanged from version 2.
- The systemd slice `app-distraction.slice` under the user manager. Verified on this machine on 2026-09-04: `systemd-run --user --scope --slice=app-distraction.slice` places the child at `/user.slice/user-1000.slice/user@1000.service/app.slice/app-distraction.slice/run-<n>.scope`. A process is "in the space" when its cgroup path has that slice as its fifth component.

**Launch.** `distractions open <target>` is the single way into the slice. The target is a URL, a list entry name, or a catalog name. The command resolves the target to one of two launches and runs it as a transient scope in the slice, detached, with the plugin's environment stripped of nothing. Resolution order is fixed: an argument with a URL scheme is a URL; otherwise a list entry name; otherwise a catalog name, which launches but is logged as not network-restricted. One host classifier, "listed or a subdomain of a listed host", serves `open` and the URL handler alike. `systemd-run --scope` blocks until its child exits, so `open` starts it in a new session with its standard streams closed and passes `--quiet --collect`. A forwarded, unlisted URL is never wrapped in the slice; it runs the way the previous handler would have run it.

- Web targets (a URL, or an entry with hosts or a `pwa` host) launch the distraction browser with `--app=<url>` and the profile flags below. When a window of that profile for the same host already exists, the command focuses it on the space instead of launching a second one.
- Native targets (an entry with a catalog `desktop` id) launch the desktop entry's `Exec` line.

The distraction browser is the Omarchy default browser when it is Chromium-family (the same case list `omarchy-launch-webapp` uses: google-chrome, brave, microsoft-edge, opera, vivaldi, helium, chromium), otherwise `chromium`. It runs with `--user-data-dir=$XDG_DATA_HOME/omarchy/distraction-space/browser --profile-directory=Distraction`. Verified on this machine on 2026-09-04 with google-chrome: the resulting window class is `chrome-<host>__-Distraction` and its pid is its own, separate from the work browser. Config `browser` overrides the binary with an argv array.

**Launcher entries.** For every listed product, setup writes one desktop entry under the person's applications directory whose `Exec` is `distractions open <name>`. Filenames follow what they replace. A native app's system entry (`org.telegram.desktop.desktop`, `signal-desktop.desktop`) lives under `/usr/share/applications` and is shadowed through ordinary XDG precedence. An Omarchy web app (`YouTube.desktop`, `WhatsApp.desktop`) lives in the person's own applications directory, the same directory setup writes to, so precedence cannot apply. Setup moves such a file, when the manifest does not already own it, into `entries-backup/` under the state directory, records the pair in the manifest, and then writes its own entry. Remove restores every backup and deletes exactly the manifest's files. Setup never edits a file it did not write; it moves it aside whole and puts it back whole. The catalog gains an optional `desktop` id per native product. Omarchy's own launcher runs the browser directly rather than through the URL handler, which is why the entries, and not the handler, are what route app-menu clicks into the space.

**URL handler.** Setup installs a desktop entry with `MimeType=x-scheme-handler/http;x-scheme-handler/https` whose `Exec` is `distractions open %u`, records the previous default handler, and makes the plugin's entry the default with `xdg-settings`. `open` with a URL whose host is neither listed nor a subdomain of a listed host forwards to the recorded previous handler by parsing its `Exec` line, the same way `omarchy-launch-webapp` reads a desktop file. When the recorded handler is the plugin itself or is missing, the fallback is `omarchy-launch-browser`. Remove restores the recorded default. The listener checks on start and on every periodic tick whether the plugin is still the default, reports `links: displaced` in state when it is not, and notifies once per listener lifetime.

**Windows.** Three layers, first match wins, all landing on `name:distraction` with `silent` so focus stays where the person is. Class matching in the first layer covers the distraction profile class and the native classes only; a listed product's web-app class from any other profile is never moved by class and goes to adoption alone.

1. One named Hyprland rule for the whole distraction profile, matching class `^[a-z-]+-.+__-Distraction$`, plus one rule per native class, set through `hyprctl eval` and re-applied on `configreloaded` exactly as version 2 does. The per-host web rules of version 2 collapse into the single profile rule.
2. The socket2 `openwindow` safety net moves any window whose pid, or an ancestor within eight hops, is in the slice. This covers popups and helper windows that carry a plain browser class.
3. Adoption. A window whose class is a listed product's web app in another profile (`chrome-<host>__-Default` and the other prefixes) belongs to a browser outside the slice and can never reach its host. The listener closes it and runs `open` for the product, once per window address. This is what makes a version 2 web app, or an "install as app" done in the work browser, end up in the right place without a manual step.

**Release.** Sometimes a chat app belongs on a work workspace for a while, to post something or to answer a thread. `distractions release [minutes]` exempts the focused window from all three layers until the deadline, default `containment.release_minutes`, or until the window closes. The listener keeps the exempt set as `{address: until}` and writes it to state. A released window keeps its network because it stays in the slice. `containment.snap_back` decides what happens to an unreleased window the person drags off the space: `true`, the default, reverts the move on the `movewindow` event as version 2 does for listed classes; `false` contains on `openwindow` only.

**Network.** The privileged wrapper renders one static table. The listener resolves listed hosts on start, on reload, on the `refresh` verb, and every 60 seconds, and sends the address set to the wrapper. `refresh` is a new listener verb that re-resolves without re-reading the config; `reload` keeps its meaning. Entering or leaving the space no longer touches the network, and the listener's own enforce path no longer short-circuits to a flush while the person is on the space.

nftables resolves a `socket cgroupv2` path to the cgroup's kernel id when the rule is loaded. A slice that systemd garbage-collects while empty would leave the accept rule pointing at a dead id, and traffic from a recreated slice would fall through to the reject rules. So the slice is not left to `systemd-run` to create on demand. Setup installs `app-distraction.slice` as a unit file under the person's user manager, no root involved, and the listener starts it before every wrapper `replace`. The wrapper checks that the slice's cgroup directory exists under `/sys/fs/cgroup` before it hands the script to `nft`, and exits 1 with `refused: slice cgroup missing` otherwise, which the listener reports as `site_block: unavailable`. The table, in order, accepts traffic from the slice cgroup, accepts the splice source-port range, rejects set members, and redirects TCP 80 and 443 on set members to the routers, exactly as version 2 does after the first rule. The wrapper derives the cgroup path from the invoking uid and takes nothing new on stdin, so the sudoers surface is unchanged. `keep_reachable`, `pass_through`, and the SNI routers keep their version 2 behavior. `site_block.enabled: false` destroys the table and skips resolution; state reports `site_block: off`.

**Feedback.** Two banners, one debounce table keyed by list entry, one log line per decision.

- Opened. Raised when a listed window lands on the space, by rule, by safety net, by adoption, or by `open`, while the person is on another workspace. Title is the product name followed by "opened in the distraction space". Body names the key that enters. The action enters the space. When the lock is active the body says "locked until HH:MM" and the action is a no-op that shows the lock notice. Nothing is raised when the person is on the space.
- Blocked. Raised by the TLS router when the SNI names a listed host. Title is "Blocked here". Body is the product name and the key. The action runs `open https://<host>/`. The HTTP router keeps serving the block page on port 80 with the same text.

Each banner fires at most once per list entry per 60 seconds. The debounce table, the peer-port attribution, the inode walk, the Hyprland-owner walk, and the provenance rate limiter are removed. The router writes one line `banner: host= entry= decision=shown|debounced` and `distractions banners` reads it.

**Sound.** The mute walks `pactl -f json list sink-inputs` as before. A sink input is a member when `application.process.id` is in the slice, checked through its cgroup file, or when the catalog audio identity matches as in version 2. The slice check runs first and a slice member is muted regardless of its window class, so the version 2 rule that never mutes a bare browser stream does not apply inside the slice: an unlisted page open in a distraction-profile window is muted with everything else while the person is away and released on the space. `muted.json` keeps its shape. WhatsApp Web, Discord, and other web apps become mutable because their audio service process is a child of the distraction browser and shares its cgroup.

**Notifications, summary, lock, bar, workspace cycling.** Unchanged mechanisms. Two behavioral additions. Locking while on the space leaves it, through the same cycle `leave` uses. `enter` while a listed window was adopted or opened during the lock finds it waiting.

**State.** `state.json` gains `"links": "on" | "off" | "displaced"`, `"browser": "<basename>"`, and `"released": {"<address>": "<until-iso>"}`. `site_block` keeps its three values. `expansion.json` entries gain `"desktop": "<id>" | null`, and a version 2 file on disk reads with `null` defaulted. A new `entries.json` manifest under the state directory lists every launcher and handler file setup wrote as `{"path": ..., "backup": ... | null}` plus `"previous_handler": "<desktop-id>" | null`. The banner log keeps version 2 lines readable; `distractions banners` prints any `banner:` line.

## API Contracts
<!-- scope: technical -->

- `distractions open <url | name>` - exit 0 after launching or focusing, 1 when the browser cannot be started or the target is not listed and no forwarder exists, 2 on usage. A listed URL opens in the space; an unlisted URL forwards to the previous handler and exits 0 when that handler started.
- `distractions setup [--remove]` - adds the launcher entries, the URL handler registration, and the new wrapper render to the version 2 steps. `--remove` reverses those three and leaves the browser profile directory in place, printing its path.
- `distractions refresh` - asks the running listener to re-resolve and re-render now, without re-reading the config. Exit 0 when the batch applied, 1 when the listener is not running or the batch failed.
- `distractions release [minutes]` - exempts the focused window from containment for `minutes`, default `containment.release_minutes`. Exit 0 when the listener recorded it, 1 when no window is focused or the listener is not running, 2 on a non-positive duration.
- `distractions status --json` - the version 2 object plus `links`, `browser`, and `released`.
- `distractions banners [--count N]` - the version 3 line shape: `banner: host=<h> entry=<name> decision=<shown|debounced>`.
- Config, all keys optional and defaulted:
  - `site_block.enabled` (`true`) - render and maintain the table at all.
  - `browser` (`"auto"`) - `auto` picks as described, or an argv array.
  - `open_links_in_space` (`true`) - register and keep the URL handler; `false` skips registration and `open` still works when called directly.
  - `containment.snap_back` (`true`) - revert a manual move of an unreleased contained window off the space; `false` contains on `openwindow` only.
  - `containment.release_minutes` (`30`) - default duration for `release`.
  - `nudges.app_banner` now governs the Opened banner and `nudges.block_page` governs the Blocked banner and the block page. Names kept so version 2 configs load unchanged.
- Catalog: a native product may carry `"desktop": "<desktop-file-id-without-suffix>"`. Every other catalog field keeps its version 2 meaning.
- Hyprland snippets: unchanged files. Existing installs need no snippet edit.
- Privileged wrapper: same argv and stdin grammar as version 2 (`replace|flush ds`, one address per line). The rendered table adds the cgroup accept rule as the first rule of both chains. The cgroup path comes from `SUDO_UID` alone; a missing or non-numeric value is refused.
- Slice unit: `install/app-distraction.slice`, copied by setup to the user manager's configuration directory, started by setup and by the listener before each render, stopped and deleted by remove.

## Edge Cases & Constraints
<!-- scope: technical -->

- A version 2 install upgrading to 3 has web apps logged in under the work browser's profile. The distraction profile starts empty, so the person logs into WhatsApp, X, and the others once. The README's upgrade section states this in the first sentence.
- Chromium hands a second launch of the same profile to the running instance and exits, so `open` for a second host while the distraction browser is running yields a new window in the existing process. That process is already in the slice, so containment, network, and mute hold. The transient scope for the second launch is empty and exits on its own.
- A link out of a distraction window to an unlisted site opens a plain window of the distraction profile. Its class carries no host, so layer 1 misses it and layer 2 moves it by pid. It reaches the unlisted site because the slice is unrestricted.
- A work page that embeds a listed host raises the Blocked banner once per entry per 60 seconds. This is the same bound as version 2 and `nudges.block_page: false` silences it.
- The Blocked action opens the site root, since the SNI carries the host and never the path.
- `xdg-settings` failing, or the default browser changing later through `omarchy-install-browser`, leaves the plugin displaced. State says so, one notice names `distractions setup` as the fix, and every other feature keeps working.
- A browser outside the case list (Firefox as the Omarchy default) makes `open` use `chromium`. When neither is installed, `open` for a web target exits 1 with a notice and web products fall back to version 2 behavior, which is containment by class with no launch path.
- A native app started outside `open`, for example from a terminal, is contained by class and muted by catalog identity, and its network is unrestricted only if its hosts are empty, which holds for every native product in the catalog.
- The wrapper's cgroup rule uses `socket cgroupv2 level 5`. nftables 1.1.6 on this machine parses it (checked 2026-09-04 with `nft -c`); applying it under root is a verification step in the first task. A kernel or nftables that refuses the rule makes the wrapper exit 1, the listener reports `site_block: unavailable`, and nothing else degrades.
- Adoption closes a window. The closed window is a listed product's web app whose start URL is its host, so no page state beyond that start URL exists to lose. Adoption never closes a plain browser window.
- The lock keeps its meaning of "cannot enter". Windows opened or adopted during a lock accumulate on the space and the Opened banner says when the lock ends.
- The slice and the profile are per user. Two sessions of the same account share both, as they share the workspace today.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** `distractions open <url>` with a listed host launches the distraction browser as a transient scope in `app-distraction.slice` with the profile flags, and the window lands on `name:distraction` without changing the focused workspace. Errors: no Chromium-family browser available exits 1 with one notice; a malformed or non-http(s) URL exits 2; a running window for the same host is focused instead of duplicated.
- **R2:** `distractions open <url>` with an unlisted host forwards to the recorded previous handler and exits 0. Errors: a missing or self-referring record forwards to `omarchy-launch-browser`; a handler whose `Exec` cannot be parsed exits 1 with one notice.
- **R3:** After setup, the plugin's handler is the `xdg-settings` default for http and https, a listed link clicked in any app opens in the space, and `setup --remove` restores the recorded previous default. Errors: `xdg-settings` failure leaves `links: displaced` in state with one notice; `open_links_in_space: false` skips registration and reports `links: off`.
- **R4:** Setup writes one launcher entry per listed product with `Exec=distractions open <name>`, named to shadow the Omarchy web app or the native app's system entry, records each file in the manifest, and remove deletes exactly those files. Errors: an unwritable applications directory fails setup with the path in the message and writes no manifest; a file not in the manifest is never deleted.
- **R5:** Every window of the distraction profile matches one Hyprland rule, and a window whose pid or ancestor within eight hops is in the slice is moved to the space by the safety net. Errors: an unreadable cgroup file for the pid skips the pid check and falls back to class matching.
- **R6:** A listed product's web-app window from a browser outside the slice is closed and reopened through `open`, once per window address. Errors: a failed `open` leaves the window where it is, moved to the space by class, and logs one line.
- **R7:** The rendered nftables table accepts traffic from the slice cgroup before any reject or redirect, and keeps the version 2 rules after it. A listed host is reachable from a process in the slice and refused from a process outside it regardless of the active workspace. Errors: the wrapper refuses the version 2 stdin bounds unchanged; an `nft` that rejects the cgroup rule exits 1 and state reports `site_block: unavailable`.
- **R8:** Entering and leaving the space performs no resolution and no wrapper call. Resolution runs on start, reload, `refresh`, and every 60 seconds. Errors: a failed batch keeps the last good set with one notice, as in version 2.
- **R9:** `site_block.enabled: false` destroys the table, stops resolution, and reports `site_block: off`, while windows, links, mute, and hold keep working. Errors: none beyond R7.
- **R10:** Exactly two banner kinds exist. Opened fires when a listed window lands on the space while the person is elsewhere, with an action that enters; Blocked fires from the TLS router for a listed SNI, with an action that opens the site root in the space. Each fires at most once per list entry per 60 seconds and never while the person is on the space. Errors: the lock active turns the Opened action into the lock notice and puts the lock end in the body.
- **R11:** The peer-port attribution, the `/proc` inode and pid walks, the Hyprland-owner walk, and the provenance rate limiter are removed, and `distractions banners` reads the three-field line. Errors: none.
- **R12:** With `mute_sounds` on and the hold in effect, a sink input whose process is in the slice is muted, and a web app's audio in the distraction profile is muted on this machine. Catalog identity matching remains for streams outside the slice. Slice membership bypasses the version 2 bare-browser guard: an unlisted page in a distraction-profile window is muted too. Errors: an unreadable cgroup file falls through to catalog matching; the version 2 unmute safety rules stay.
- **R13:** Locking while on the space leaves it. Errors: no other workspace occupied leaves the person in place, as `leave` does today.
- **R14:** `state.json` and `status --json` carry `links` and `browser`, and a version 2 config file loads with every new key at its default. Errors: an invalid `browser` argv is reported by `config set` before the write, as other keys are.
- **R15:** The README describes the slice, the profile, the login-once upgrade cost, the two banners, and the network switch, and the plugin manifest reads 3.0.0. Errors: none.
- **R16:** `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes offline with fakes for `systemd-run`, `xdg-settings`, and the cgroup file reads added to the harness. Errors: none.
- **R17:** `distractions release [minutes]` exempts the focused window from all three containment layers until the deadline or until the window closes, `status --json` lists `released` as `{address: until}`, and the window keeps its network because it stays in the slice. Errors: no focused window, or the listener not running, exits 1 with one notice; a non-positive duration exits 2; a window that closes is pruned from the set on `closewindow`.
- **R18:** With `containment.snap_back: true`, a manual move of an unreleased slice member or listed class off the space is reverted on the `movewindow` event; with `false`, only `openwindow` triggers containment. Errors: none beyond R5.

## Boundaries
<!-- scope: business -->

- No Firefox web apps. Firefox has no `--app` window with a host-bearing class; a Firefox default browser gets `chromium` for web products, as Omarchy itself does.
- No browser extension and no HTTPS block page. Feedback on port 443 stays a banner.
- No change to the notification hold mechanism, the shell patch, the clone lifecycle, the summary, or the lock prompts.
- No per-window or per-tab network policy inside the work browser. The unit of network policy is the process group.
- No automatic purge of the distraction profile on remove.
- No change to the three Hyprland snippets. Existing installs keep them.
- No Encrypted Client Hello handling; the version 2 limit stands.
- No `main` push. Work happens on a branch until the 2.1.0 marketplace review completes.

## Decision Context
<!-- scope: both -->

### Motivation
<!-- scope: business -->

The person's three complaints share one cause. Workspace-keyed policy makes the outcome of an action depend on where the person was standing when they took it. A process-keyed policy makes the outcome depend only on what the thing is. That is what "it just works" means here, and it is why the rewrite starts from the boundary rather than from any one symptom.

### Implementation Tradeoffs
<!-- scope: technical -->

- Slice over workspace as the network key. nftables can match a socket's cgroup and cannot match a window's workspace, so the slice is the only boundary the kernel can enforce. It also removes every network action from the enter and leave paths, which is where the generation counter, the waiters, and the flush lived.
- Separate browser profile over a shared one. The shared process id (3463 for WhatsApp, X, and the work browser on this machine) makes per-process policy impossible without it. The cost is one login per web app after upgrade. The benefit is that windows, network, and audio all become attributable with no heuristics.
- Routing links over refusing them. A refusal is a dead end the person has to recover from by hand. A route ends where the person wanted to go. The URL handler is one desktop file and one `xdg-settings` call, both reversible.
- Keeping the block, static and switchable. The block is the only answer to the typed-URL path. Making it static makes it predictable, and the switch makes the decision cheap to revisit.
- Adoption over silent containment of foreign web-app windows. A contained but blocked window is the exact broken state the person reported. Closing and reopening it in the right process is the only outcome that works, and the only page state at risk is the start URL.
- Rejected: `exec` dispatcher window rules by pid. Chromium's single-instance handoff means the second launch's pid never owns a window.
- Rejected: DNS-level block. It cannot be scoped to a process group and would need root at query time.
- Rejected: a browser extension. Per-browser, per-profile, and outside what an Omarchy plugin can install.
- Rejected: matching the notification sender by bus pid and cgroup. Better than app-name matching, but the shell patch is the suppression mechanism and stays out of scope here.
- One nftables table, not a second network stack. The browser profile is a process boundary; the network policy is still the single table fn-9 set as a boundary.
- A persistent slice unit over an on-demand transient slice, because nftables pins the rule to a cgroup id at load time and an on-demand slice can be garbage-collected between launches.
- Backup and replace for Omarchy's same-name web-app entries, chosen by the person on 2026-09-05 over leaving them alone and relying on adoption, which would show a window flash on every app-menu click.
- Mute everything in the slice, chosen on 2026-09-05: the version 2 bare-browser guard stays for streams outside the slice only.
- `release` plus `containment.snap_back`, chosen on 2026-09-05 over a config-only or verb-only shape, because working with a chat app on a work workspace for a while is a real case and containment should not have to be switched off globally to allow it.

### Superseded prior decisions
<!-- scope: technical -->

- fn-1 R1/R6 and fn-9 R2: the block applied and lifted by the current workspace. Replaced by the slice as the network key (R7, R8).
- fn-11 R1: one window rule per expanded web entry. Replaced by the single profile rule (R5); the native per-class rules and the `configreloaded` re-apply stay.
- fn-13 R2: X contained by class and blocked by host in a shared browser. X becomes a web target in the distraction profile.
- fn-15 R1/R2 and fn-20 R1–R3: banner suppression by peer-port attribution and the provenance line. Removed by construction (R10, R11).
- Kept unchanged: fn-21's sudoers transaction and wrapper bounds, fn-14's reject rules, fn-18's `pass_through`, `keep_reachable`, and SNI routers.

## Parked unknowns

- Whether `socket cgroupv2 level 5` applies under root on kernel 7.1.9 and nftables 1.1.6. The parser accepts it; a privileged apply during the first network task settles it.
- Whether `application.process.id` on the distraction browser's sink inputs resolves to a process inside the slice on PipeWire here. One `pactl` listing with the distraction browser playing sound settles it.
- Whether Brave, Edge, Opera, Vivaldi, and Helium honor `--profile-directory` in the window class the way google-chrome does. One launch per installed browser settles it; the rule pattern already accepts any prefix.

## Quick commands

```bash
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
./distractions open https://www.youtube.com/ && ./distractions status --json
sudo nft list table inet omarchy_ds | head -20
```

## Early proof point

Task fn-22-the-space-is-a-process-group-one.1 validates the core approach: the wrapper renders the cgroup accept rule, `nft` applies it under root on this kernel, and the persistent slice keeps the rule live across launches. If it fails, re-evaluate the static-table design before fn-22-the-space-is-a-process-group-one.3 and later; the window, link, and sound halves do not depend on it.

## Requirement coverage

| Req | Description | Task(s) | Gap justification |
|-----|-------------|---------|-------------------|
| R1 | `open` launches a listed URL in the slice and profile, or focuses | .3 | — |
| R2 | `open` forwards an unlisted URL to the previous handler | .3 | — |
| R3 | URL handler registered by setup, restored by remove, displaced reported | .4 | — |
| R4 | Launcher entries with manifest, backup, exact removal | .4 | — |
| R5 | Profile rule and pid/ancestor safety net | .6 | — |
| R6 | Adoption of foreign-profile web-app windows | .6 | — |
| R7 | Static table with cgroup accept first; slice reachable, outside refused | .1 | — |
| R8 | No network action on enter/leave; resolution on start, reload, refresh, 60 s | .2 | — |
| R9 | `site_block.enabled: false` destroys the table and reports off | .2 | — |
| R10 | Exactly two banner kinds, 60 s per entry, never on the space | .5, .6 | — |
| R11 | Attribution and provenance removed; three-field line | .5 | — |
| R12 | Slice-first mute, bare-browser guard bypassed inside the slice | .7 | — |
| R13 | Locking on the space leaves it | .7 | — |
| R14 | `links`, `browser` in state and status; v2 config loads with defaults | .2 | — |
| R15 | README, internals, manifest 3.0.0 | .9 | — |
| R16 | Test suite passes offline with new fakes | .1–.9, gated by .9 | — |
| R17 | `release` verb and exempt set | .8 | — |
| R18 | `containment.snap_back` policy | .8 | — |
