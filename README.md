# Omarchy distraction space

One named Hyprland workspace for the apps and sites that take your attention, and a plugin that keeps them there.

![The Omarchy bar showing the distraction-space eye glyph with three held notifications, and the "While you were away" notice listing the per-app count](preview.png)

You list Telegram, X, YouTube, and whatever else pulls you off task. The plugin launches them into one process group, the systemd slice `app-distraction.slice`, and one workspace, `name:distraction`, and a listed web product gets its own browser profile so it has its own process, window class, and audio streams. Their windows open on the space and get moved back when they land anywhere else. Their sites load only from that process group: a WhatsApp or YouTube window left open on the space keeps syncing while you work, and the same site typed into the work browser out of habit gets a block page instead of the feed. A listed link clicked anywhere opens on the space instead of in the work browser. Their notifications wait, their sounds stay muted, the bar shows how many are waiting, and when you come back one notice tells you what was held, per app, or, if you turn it on, one line from your own agent saying whether any of them needed you. Lock the space for 25 minutes and it refuses to open until the timer runs out or you type 50 characters saying why you are leaving early.

## Install

Omarchy 4, Hyprland, Python 3.11, and a Chromium-family browser (`google-chrome`, `brave`, `microsoft-edge`, `opera`, `vivaldi`, `helium`, or `chromium`) for the web products. Runtime dependencies, all present on a stock Omarchy 4 install: `nft`, `sudo` and `visudo`, `hyprctl`, `getent`, `busctl`, `pactl`, `patch`, `systemctl` and `systemd-run` under your user manager, `xdg-settings`, and the Omarchy tools `omarchy-shell`, `omarchy-plugin-clone`, `omarchy-menu-select`, `omarchy-menu-input`, `omarchy-notification-send`, `omarchy-launch-browser`, and `omarchy-launch-editor`. Optional: `update-desktop-database` so the app menu sees the launcher entries at once, and one agent CLI (`claude`, `grok`, `codex`, `gemini`, `opencode`, or `copilot`) when `summary.command` is `auto`.

```bash
omarchy plugin add https://github.com/DanielKillenberger/omarchy-distraction-space.git --enable
```

**Links from other apps.** `setup` asks one question: whether to route links through the distraction space. Yes registers the plugin's link handler as the system's default browser. The handler is a router, not a browser: a clicked link to a listed site opens in the distraction profile on the space, and every other link is forwarded to the browser that was the default before, unchanged, so Omarchy's browser keybinds (Super+Shift+Return, Super+Shift+B) and its web apps keep working. That browser may ask to become the default again; answer "Don't ask again", because one click there takes the default back. No leaves your default browser as it is: a clicked link to a listed site then opens there, hits the block page, and you reopen it from the launcher. The answer is written to `open_links_in_space` in the config file, so setup asks once; a rerun prints the current choice, `distractions config set open_links_in_space true` (or `false`) changes it, and a setup with no terminal takes the config value without asking. `setup --yes` does the same and never prompts for anything, the sudo password included, so a first install that needs one fails and says so. `distractions setup --remove` restores the previous default browser.

Copy the three Hyprland snippets into your own config, because `omarchy plugin add` does not edit Hyprland for you.

- [`hypr/windows.lua`](hypr/windows.lua) into `~/.config/hypr/hyprland.lua`, or your windows file
- [`hypr/bindings.lua`](hypr/bindings.lua) into `~/.config/hypr/bindings.lua`
- [`hypr/autostart.lua`](hypr/autostart.lua) into `~/.config/hypr/autostart.lua`

Reload Hyprland, then run setup once.

```bash
chmod +x ~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions
hyprctl reload
~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions setup
```

`setup` asks for sudo one time. It installs the nftables wrapper at `/usr/local/libexec/omarchy-distraction-space/distractions-nft` and the grant at `/etc/sudoers.d/omarchy-distraction-space`, and records what it installed in `/usr/local/libexec/omarchy-distraction-space/.installed.sha256` so a matching re-run needs no password. Everything else is yours, no root involved. It copies the slice unit [`install/app-distraction.slice`](install/app-distraction.slice) to `~/.config/systemd/user/` and starts it. It writes one launcher entry per listed product under `~/.local/share/applications/` whose `Exec` is `distractions open <name>`, named to shadow the app's system entry or Omarchy's own web-app entry; a file of that name it did not write is moved whole into `entries-backup/` under the state directory first, and every file it wrote goes into `entries.json`. Every other Omarchy web app in that directory (an `Exec` starting with `omarchy-launch-webapp`) is rewritten the same way, backup and record included, to `distractions open --app <url>`, which forwards it to the previous browser as an app window, so Omarchy's launcher never resolves a web app to the plugin's handler and opens it in the wrong browser. It writes the URL handler entry `io.github.danielkillenberger.distraction-space.desktop`, records your current default browser, and, when links are on, makes the handler the default with `xdg-settings`. Then it clones and patches the notification service so the hold has a per-sender silenced list to write to. Run it again after an Omarchy update or after editing the list, so the launcher entries follow it. `distractions setup --remove` reverses all of it. The bar widget lands in the center section; `omarchy bar move io.github.danielkillenberger.distraction-space --section right` moves it.

Installs from before 2.1.0 used the id `distraction-space`. To move to the new id: `omarchy plugin remove distraction-space`, add the plugin again with the command above, copy the three snippets again (the helper path changed), and run `distractions setup`.

Autostart owns the long-running listener. To start it now without logging out:

```bash
~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions listen
```

## Upgrading from 2.x

Each web app asks for a login once, because listed web products now run in their own browser profile and that profile starts empty. Your 2.x web apps stay logged in under the work browser's profile, where listed blocked hosts remain restricted; the listener moves those windows into the space and leaves them open under the existing release and snap-back policy. A notification offers to open the product in the separate distraction profile, where you sign in again. Confirming opens a replacement; it never closes the original. Save your work before closing the original yourself, because drafts, calls, and navigation state cannot transfer. Nothing about the Hyprland snippets or the config file changes: a 2.x config loads with every new key at its default, and `setup` asks the link question once and adds the slice unit, the launcher entries, and the URL handler on its next run. Run it once after updating.

Or carry the logins over instead of signing in again. With both browsers closed, `distractions profile import` copies the default browser's main profile (`~/.config/google-chrome/Default` for Chrome; the matching directory for Chromium, Brave, Edge, and Vivaldi; `--from <dir>` names any other Chromium profile) into the distraction profile, minus the caches Chromium regenerates, so cookies, passwords, bookmarks, history, and extensions arrive in one go. It refuses while the source browser or the distraction browser is running, refuses a source that is not a Chromium profile, and refuses an existing distraction profile unless you pass `--replace`, which moves the existing one to `Distraction.bak-<date>` beside it and never deletes it. This is a one-time snapshot: nothing keeps the two profiles in sync afterwards, the copied extensions run in the distraction profile from then on, and your Google account shows as signed in on two profiles. It moves about a gigabyte and `setup` never runs it.

## Remove

```bash
~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions setup --remove
omarchy plugin remove io.github.danielkillenberger.distraction-space
```

`setup --remove` hands the default browser back to the one it recorded, deletes exactly the launcher and handler files in `entries.json` and moves every backup home, Omarchy's web-app entries included, destroys the nft table, stops and deletes the slice unit, removes the wrapper, the sudoers grant, and that record with sudo, and removes the notification-service clone it created. The browser profile at `~/.local/share/omarchy/distraction-space/browser` stays, and remove prints its path so you can delete it yourself. Run it before `omarchy plugin remove`, because the plugin directory holds the script that does the removing. Delete the three Hyprland snippets by hand, the same way they went in.

## What it does

**The space is a process group.** `distractions open <target>` is the one way in. It takes a URL, a list entry name, or a catalog name, and runs the launch as a transient scope in `app-distraction.slice` under your user manager. A web target starts the distraction browser with `--app=<url>` in the profile at `~/.local/share/omarchy/distraction-space/browser`, so its window class is `<browser>-<host>__-Distraction` and its process is not the work browser's. A native target runs its desktop entry. The launcher entries `setup` wrote and the URL handler both call `open`, so the app menu and links land there without you doing anything. Windows, network, and sound are all decided by that membership, never by which workspace you happen to be looking at.

**Windows stay on one workspace.** Three layers, first match wins, all landing on `name:distraction` without stealing focus. One named Hyprland rule for the whole distraction profile plus one per native window class, set through `hyprctl eval` and re-applied when socket2 reports `configreloaded`, since Hyprland drops them on every config reload. The socket2 `openwindow` event is the safety net: a window whose process, or an ancestor within eight hops, is in the slice is moved there, which catches popups and helper windows with a plain browser class. And adoption: a listed product's web-app window from another browser profile is moved intact and offered a separate-profile launch through a notification action. Moving it does not change its process group or exempt it from site blocking. Discovery, startup scans, and reloads never close it; cancelling or a failed replacement launch leaves it intact. `containment.snap_back` decides what a manual drag off the space does; `distractions release` exempts one window for a while. Super+Tab and Super+Shift+Tab skip the space, so cycling workspaces never drops you into it.

**Listed sites load only from the space.** The wrapper renders one static nftables table whose first rule accepts traffic from the slice's cgroup. After it, the sets `omarchy_ds_v4` and `omarchy_ds_v6` are rejected with a TCP reset, except ports 80 and 443, which are redirected to the plugin's routers on 28080 and 28443. The listener resolves each listed host on start, on `reload`, on `refresh`, and every 60 seconds, and sends the addresses to the wrapper; entering or leaving the space touches nothing. The router reads the Host header or the SNI from the ClientHello. A listed host, or a subdomain of one, gets the block page on 80 and a closed connection on 443. Any other hostname on that shared address is spliced to its real destination, so Google Safe Browsing keeps working while YouTube is listed. The splices leave through TCP source ports 61000 to 61999, which the wrapper lets past the block, and at most 256 run at once. `site_block.pass_through: false` restores the plain address block. `site_block.enabled: false` destroys the table and stops resolving; everything else keeps working.

**Links open in the space.** With your yes at setup, the plugin is the default handler for `http` and `https`. A link to a listed host, or a subdomain of one, clicked in any app sends the exact URL, including its path, query, and fragment, to the distraction browser on the space while you stay where you are. Two links on the same host both reach the browser even when a matching window already exists. Opening a product by name may reuse its window. Unlisted links are forwarded to the browser that was the default before, untouched. While it is the default, `open` owns launching for everything: with no target, or with only browser flags (`--incognito`, `--private-window`), it runs the previous browser bare with the flags appended, which is what Omarchy's browser keybinds do, and `open --app <url>` forwards an unlisted URL as an app window, which is what the rewritten Omarchy web-app entries do. The listener re-runs the entry sync on `refresh` and once a minute, so a web app Omarchy regenerates is rewritten within a minute. The distraction profile is created with Chrome's "make this your default browser?" prompt off, and `profile import` sets the same preference in the copy; your main profile is never touched. If another program takes the default later, `status` reports `links: displaced`, one notice names `distractions setup` as the fix, and everything else keeps working. `open_links_in_space: false` skips the registration, and the entries are still rewritten.

**Two banners, one shape.** "`<Product>` opened in the distraction space" fires when a listed window lands there while you are on another workspace, by rule, by safety net, by adoption, or by `open`; its action enters the space, and while a lock is active the body says when the lock ends and the action shows the lock notice instead. "Blocked here" fires from the TLS router when the SNI names a listed host, since a blocked connection is by construction from outside the space; its action opens the site in the space. HTTP gets the block page instead. Each fires at most once per list entry per 60 seconds and never while you are on the space. `nudges.app_banner` turns off the opened banner, and `nudges.block_page` turns off the block page and the blocked banner together.

**Notifications wait, with a visible count.** While the hold is in effect, the listener pushes each listed app's sender keys into the notification service's per-sender silenced list, one IPC call per key. Those apps write to history and pop no banner. Each held ping goes into `held.jsonl`, the running total shows after the eye glyph in the bar, and the listener removes only the keys it added. `hold_notifications` chooses when the hold applies: `off-space` (the default), `locked`, or `never`.

**One line when you come back.** Entering the space or ending a lock shows a single notification titled "While you were away". By default its body is the per-app count, and nothing you were sent leaves the machine. Set `summary.command` to `auto` and the body comes from the agent you chose with `omarchy default agent` (`~/.config/omarchy/defaults/agent`), run once with the held records on stdin: `grok -p`, `claude -p --output-format text`, `codex exec -s read-only --skip-git-repo-check -`, `gemini -p`, `opencode run`, or `copilot -p`. pi, omp, and crush have no such one-shot form, so they, no chosen agent, and an agent missing from PATH show the count and write one line to the log. The agent gets `summary.timeout_seconds` (60 by default) before the count takes over; a `claude -p` reply took about 7 seconds when this was measured. Zero held notifications show nothing at all.

**Sounds from the space mute.** With `mute_sounds` on, the listener mutes the PulseAudio streams of listed apps for the length of the hold. A stream whose process is in the slice is muted first, whatever its window class, which is what makes WhatsApp Web, Discord, and the other web apps mutable: their audio comes from a child of the distraction browser. Outside the slice it matches the catalog's audio identity against `application.name` and `application.process.binary`, as before, and never mutes a bare browser stream. It records what it muted as sink-input index plus `pid:starttime`, and unmutes only a stream whose identity still matches, so a stream you muted yourself stays muted.

**The lock runs for a set time.** `distractions lock` asks for a duration (25 minutes by default) and what the time is for, then refuses `enter` until the deadline. Locking while you are on the space leaves it first. Leaving early takes `distractions unlock` with a reason of at least 50 characters, and the plugin appends the time, the purpose, and the reason to its log. There is no start-locked setting, so the lock never begins on its own.

## Keys

| Action | Keys |
|---|---|
| Open or leave the space | Super+Ctrl+Shift+D |
| Move the focused window there | Super+Alt+D |
| Lock, or unlock when locked | Super+Ctrl+Shift+F |
| Next occupied workspace, skipping the space | Super+Tab |
| Previous occupied workspace, skipping the space | Super+Shift+Tab |
| Release the focused window from containment (commented out in the snippet) | Super+Ctrl+Shift+E |

The bar widget answers a left click with lock or unlock, a right click with the menu, and a middle click with the toggle. A quiet dot marks degraded or unknown operation; the tooltip and the menu's Status action explain why. It keeps the lock and held-count display, watches state changes, and checks status every 30 seconds so a stopped listener becomes visible even when no file changes. This check pings the listener and reads saved observations; it does not run privileged firewall probes.

The menu can release the window that was focused before the menu opened, for `containment.release_minutes`. Settings includes “Open listed links in the space”, “Block listed sites outside the space”, and “Return moved windows to the space”. Each shows the saved choice separately from its last observed behavior. Browser-routing changes still need `distractions setup`; snap-back is applied on reload but is not independently verified by status. A cancelled or invalid edit leaves the saved choice unchanged.

## Moved, and blocked

Two separate things happen to a listed app. Its windows move to the distraction space, and its hosts are reachable only from the space's process group. Every catalog product gets the first. Messaging apps skip the second, so a chat still delivers while its window stays out of sight.

| | Windows moved | Network blocked outside the space |
|---|---|---|
| Telegram, Discord, WhatsApp, Signal, Google Messages | yes | no |
| X, Facebook, Instagram, Threads, Reddit, TikTok, Snapchat, YouTube, Twitch, Netflix | yes | yes |

[`catalog.json`](catalog.json) ships 19 products, the 15 above plus Bluesky, Pinterest, Tumblr, and LinkedIn. The default list is the 15. `distractions catalog` prints every name, and `distractions list add <name>` adds one. A custom entry with `hosts` is moved and blocked; a custom entry with only `class=<regex>` is moved and never blocked.

## Limits

- The hostname router cannot see through Encrypted Client Hello. A listed site served behind ECH presents the provider's public name in the outer ClientHello, so it passes through.
- The pass-through exemption is TCP source ports 61000 to 61999, above the default `net.ipv4.ip_local_port_range` ceiling of 60999. On a machine whose sysctl widens that range past 61000, an ordinary connection can draw an exempt port and bypass the block.
- HTTPS cannot show the block page without a certificate your browser trusts. The banner is the only feedback on port 443.
- No Firefox web apps. Firefox has no `--app` window with a host-bearing class, so a Firefox default gets `chromium` for the web products, as Omarchy itself does. With no Chromium-family browser installed, `open` for a web target exits 1 with a notice and web products fall back to containment by class with no launch path.
- The accept rule is `socket cgroupv2 level 5`, which needs a kernel and nftables that support cgroup2 socket matching. When `nft` refuses it, or the slice's cgroup directory is missing, the wrapper exits 1, `status` reports `site_block: unavailable`, and nothing else degrades. nftables 1.1.6 on kernel 7.1.9 parses the rule; a privileged apply on that pair is still unverified, so treat the first `sudo nft list table inet omarchy_ds` after setup as the check.
- Chromium hands a second launch of the same profile to the running instance. `open` for a second host while the distraction browser runs yields a new window in the existing process, which is already in the slice, so containment, network, and mute hold; the second transient scope is empty and exits on its own.
- Whether a web app's audio stream reports a process id inside the slice on PipeWire is unverified. When it does not, the stream falls through to the catalog rules, which cannot attribute a shared browser stream, and that web app keeps playing.
- The profile window class `<browser>-<host>__-Distraction` was verified with google-chrome. Brave, Edge, Opera, Vivaldi, and Helium are assumed to honor `--profile-directory` in the class the same way; the rule accepts any prefix, but none of them has been launched here.
- The notification hold needs the patched service clone until Omarchy ships a per-sender silenced list of its own. Without it, `status` reports `notification_hold: unavailable`, one notice names the fix, and everything else keeps working.
- `hyprctl keyword` refuses on Omarchy 4's Lua config, which is why the window rules go through `hyprctl eval`.
- `setup --remove` leaves the browser profile in place. Delete `~/.local/share/omarchy/distraction-space/browser` yourself when you want the logins gone.
- `setup` needs sudo once and writes two root-owned files. Read [`distractions-nft`](distractions-nft) and [`install/sudoers.omarchy-distraction-space`](install/sudoers.omarchy-distraction-space) before you run it.

## Configure

`~/.config/omarchy/distraction-space.json`, honoring `$XDG_CONFIG_HOME`. Missing keys take the default. Unknown keys survive a save. `distractions config get <key>` and `distractions config set <key> <value>` read and write one key; `distractions menu` edits the list, the nudges, the hold, the mute, the lock, and the summary from a menu.

| Key | Default | What it sets |
|---|---|---|
| `list` | the 15 defaults | Catalog name, hostname, `class=<regex>`, or an object with `name` plus `class` or `hosts` |
| `keep_reachable` | `[]` | Hosts whose addresses stay out of the block, even when a listed site shares one |
| `site_block.enabled` | `true` | Render and maintain the nftables table at all; `false` destroys it and stops resolving |
| `site_block.pass_through` | `true` | Splice unlisted hostnames on a blocked address to their real destination; `false` refuses every connection to the address |
| `browser` | `"auto"` | The distraction browser: `auto` takes the Omarchy default when it is Chromium-family, else `chromium`; or an argv array |
| `open_links_in_space` | `true` | Register the URL handler at `setup` and keep it; `false` skips it, and `open` still works when called directly. Absent until `setup` asks; the answer is written here |
| `containment.snap_back` | `true` | Revert a manual move of a contained window off the space; `false` contains on `openwindow` only |
| `containment.release_minutes` | `30` | How long `distractions release` exempts a window with no duration given, at most 10080 (one week) |
| `nudges.app_banner` | `true` | The opened banner when a listed window lands on the space while you are on another workspace |
| `nudges.block_page` | `true` | The block page on port 80, and the blocked banner for a listed HTTPS host |
| `hold_notifications` | `"off-space"` | When the hold applies: `off-space`, `locked`, or `never` |
| `mute_sounds` | `true` | Mute the space's audio streams, and listed apps' streams outside it, during the hold |
| `lock.default_minutes` | `25` | The duration the lock menu offers first |
| `lock.ask_purpose` | `true` | Ask what the locked time is for |
| `lock.reason_min_chars` | `50` | Characters required to unlock early; `0` unlocks with no prompt |
| `summary.command` | `"off"` | `off`, `auto` (the agent from `omarchy default agent`), or an argv array that reads the held records on stdin |
| `summary.timeout_seconds` | `60` | How long that command gets before the per-app count takes over |
| `hooks.lock` / `unlock` / `enter` / `leave` | `[]` | Argv arrays run detached with `DS_EVENT`, `DS_PURPOSE`, `DS_MINUTES`, `DS_REASON`, `DS_HELD` |
| `log` | `~/.local/state/omarchy/distraction-space/log` | Where lock reasons, hook output, network batches, and banner decisions go |

With no config file, the first load seeds `list` from your existing `~/.config/omarchy/app-list.json` and `focus.json`, and falls back to the 15 defaults.

## Commands

`distractions <command>`, at `~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions`. Exit 0 on success, 1 on a refused or failed action, 2 on usage.

| Command | What it does |
|---|---|
| `status [--json]` | Lock, workspace and containment state, plus `health` reasons and per-service `observed_at`. `updated` is the saved state timestamp; `response_at` is this read. Works without a listener and reports it stopped. |
| `open [--app] [url\|name] [browser flags...]` | Deliver an exact listed URL, or launch a list entry or catalog product by name with existing-window reuse. An unlisted URL is forwarded to the previous default browser, as an app window with `--app`; no target forwards the bare browser, and `-` flags pass through to it unchanged. Exit 1 when no browser can be started or the link had no forwarder, 2 on a malformed URL. |
| `migrate ADDRESS IDENTITY` | Notification action: confirm a separate-profile product launch for the still-matching original window. The notification supplies the identity. Cancelling, failure, and success all leave the original open. |
| `profile import [--from DIR] [--replace]` | Copy the default browser's main profile, or the Chromium profile at `DIR`, into the distraction profile once, skipping caches, and print the destination and the byte count. Exit 1 while either browser runs, when the source is not a Chromium profile or overlaps the destination, or when the destination exists without `--replace`. |
| `toggle` / `enter` / `leave` | Enter or leave the space. `enter` refuses while locked. |
| `next` / `prev` | Cycle occupied workspaces, skipping the space. |
| `lock [MINUTES\|forever] [PURPOSE...]` | Lock. No arguments opens the duration menu, then the purpose input. Leaves the space first when you are on it. |
| `unlock [REASON...]` | Unlock early with a reason of at least `lock.reason_min_chars` characters. |
| `release [MINUTES]` | Exempt the focused window from containment for `MINUTES`, default `containment.release_minutes`, or until it closes. Exit 1 with a notice when nothing is focused or no listener runs, 2 on a non-positive duration or one over a week. |
| `list` / `list add` / `list remove` / `list expand` | Read and edit the list; `expand` prints the resolved classes, hosts, senders, audio identity, and desktop id as JSON. |
| `catalog` | Every catalog product name, one per line. |
| `config path` / `get` / `set` / `edit` | Read and write the config file. `set` validates before it writes. |
| `menu` | The full menu: status, lock, enter or leave, release the focused window, edit the list, settings. |
| `senders` | The sender keys the hold pushes into the shell's silenced list. |
| `banners [--count N]` | The newest `banner: host=<h> entry=<name> decision=shown\|debounced` lines from the state log, 20 by default. |
| `listen` | The listener. Autostart runs one per session; a second one exits 0 immediately. |
| `reload` | Ask the running listener to re-read the config. |
| `refresh` | Ask the running listener to re-resolve the listed hosts and re-render the table now, without re-reading the config, and to re-run the launcher entry sync. Exit 1 when no listener runs or the batch failed. |
| `setup [--yes] [--remove]` | Install or remove the privileged wrapper, the slice unit, the launcher entries, the URL handler, and the patched notification-service clone. The first run asks whether to route links through the space; `--yes` takes the config value (`true` by default) without asking and runs sudo with `-n`, so it never prompts for anything. |

## Internals

State file shapes, the listener loop, the static network table, the URL handler and launcher entries, the browser profile, the clone lifecycle, and the catalog format are in [`docs/internals.md`](docs/internals.md).

For opt-in firewall and web-app audio checks, see [live validation](docs/internals.md#opt-in-live-validation). These checks are separate from the offline suite and must record both results and restoration.

## Contributing

```bash
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
```

The suite runs offline. `tests/harness.py` gives every test its own temporary XDG root, the tests put fake `hyprctl`, `getent`, `busctl`, `pactl`, `systemctl`, `systemd-run`, `xdg-settings`, and nft binaries at the front of `PATH`, and the cgroup reads go to a fake `/proc`, so a run never touches your session, your user manager, your config, or your firewall. The `/usr/bin` prefix keeps a shim-based version manager out of the way. Under mise's `python3` shim, most of `tests/test_hypr.py` fails here, because the child process resolves the real `hyprctl` instead of the fake. Plain `python3 -m unittest discover -s tests` is enough on a machine without one. Keep the suite offline in a pull request.

Lint the bar widget with `qmllint` from `qt6-declarative`; it is not on `PATH`. Quickshell maps `qs.*` onto the shell root, so a bare `-I "$OMARCHY_PATH/shell"` cannot resolve `qs.Commons` or `qs.Ui`. Give it an import directory whose `qs` entry links to the shell instead.

```bash
mkdir -p /tmp/qmlimports && ln -sfn "${OMARCHY_PATH:-/usr/share/omarchy}/shell" /tmp/qmlimports/qs
/usr/lib/qt6/bin/qmllint -I /tmp/qmlimports BarWidget.qml
```

Two warnings remain, both noise. `Member "iconSlot" not found on type "QObject"` at `Style.bar.iconSlot`: `Style.bar` is an inline `QtObject` whose declared properties qmllint cannot see through the bare `QObject` type. `Type QProcess::ExitStatus of parameter exitStatus in signal called exited was not found` at the state process's `onExited`: the type lives in a Qt module this import path does not carry, and Omarchy's own `plugins/bar/indicators/ScreenRecording.qml` emits it verbatim under the same command. Anything else is a finding.

## License

MIT. See [`LICENSE`](LICENSE).
