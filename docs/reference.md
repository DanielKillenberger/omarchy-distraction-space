# Reference

The [README](../README.md) is the short tour. This page is the complete account of installing and operating the plugin: what it needs, what setup writes, how each feature behaves, where it falls short, and every config key and command. The state file shapes, the listener loop, the static network table, the URL handler and launcher entries, the browser profile, the clone lifecycle, and the catalog format are in [internals](internals.md), which is for reading or changing the code.

## Requirements

Omarchy 4, Hyprland, Python 3.11, and a Chromium-family browser (`google-chrome`, `brave`, `microsoft-edge`, `opera`, `vivaldi`, `helium`, or `chromium`) for the web products.

Runtime dependencies, all present on a stock Omarchy 4 install: `nft`, `sudo` and `visudo`, `hyprctl`, `getent`, `busctl`, `pactl`, `pw-metadata`, `wireplumber`, `patch`, `systemctl` and `systemd-run` under your user manager, `xdg-settings`, and the Omarchy tools `omarchy-shell`, `omarchy-plugin-clone`, `omarchy-menu-select`, `omarchy-menu-input`, `omarchy-notification-send`, `omarchy-launch-browser`, and `omarchy-launch-editor`. Launcher refresh also needs `update-desktop-database` from `desktop-file-utils`; when it is missing, reload/refresh report incomplete work even if the config and firewall were applied.

Optional: one agent CLI (`claude`, `grok`, `codex`, `gemini`, `opencode`, or `copilot`) when `summary.command` is `auto`.

## What setup installs

```bash
omarchy plugin add https://github.com/DanielKillenberger/omarchy-distraction-space.git --enable
chmod +x ~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions
~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions setup
```

That is the whole install: the add command and one setup run. Then log out and back in once, or start the listener by hand, because Hyprland runs autostart lines only at login. Autostart owns the long-running listener; `distractions listen` starts it now without logging out.

### Links from other apps

`setup` asks two questions, one after the other and both before anything asks for a password. The first: whether to route links through the distraction space. Yes registers the plugin's link handler as the system's default browser. The handler is a router, not a browser: a clicked link to a listed site opens in the distraction profile on the space, and every other link is forwarded to the browser that was the default before, unchanged, so Omarchy's browser keybinds (Super+Shift+Return, Super+Shift+B) and its web apps keep working. That browser may ask to become the default again; answer "Don't ask again", because one click there takes the default back. No leaves your default browser as it is: a clicked link to a listed site then opens there, hits the block page, and you reopen it from the launcher.

The answer is written to `open_links_in_space` in the config file, so setup asks once; a rerun prints the current choice, `distractions config set open_links_in_space true` (or `false`) changes it, and a setup with no terminal takes the config value without asking. `setup --yes` does the same and never prompts for anything, the sudo password included. `distractions setup --remove` restores the previous default browser.

### Blocking listed sites

`setup` asks a second question, right after the link one and before anything asks for a password: whether to block listed sites outside the space. Yes installs the firewall helper and the sudoers grant, which is the one part of this plugin that needs your password. No installs everything else — the slice, the Hyprland file, the launcher entries, the notification hold, the WirePlumber hook — runs no sudo at all, and leaves the space working as a place your distractions live rather than the only place they load.

The answer is written to `site_block.enabled`, so setup asks once and a rerun prints the choice instead. A machine that already has the helper installed counts as a yes and is never asked: an update keeps site blocking on. `setup --yes` and a setup with no terminal never ask and never take the default here — nobody is there to type a password, so an unanswered question stays unanswered and the run says in one line what turns it on later.

Either of two things turns it on afterwards, and both end with it working rather than with an instruction to go and run something else:

```bash
distractions site-block on    # installs the helper when it is missing, then applies the block
distractions site-block off   # destroys the table; the helper and the grant stay installed
```

and the settings menu's "Block listed sites outside the space", which turns it off and turns it on directly when the helper is there, and otherwise opens Omarchy's floating terminal running `distractions site-block on`, since that is where a password prompt has somewhere to appear. `site-block on` with no terminal and no helper installs nothing and says a terminal is needed once. Turning it off leaves the helper and the grant in place, so turning it back on costs no second password; `setup --remove` is what removes them.

`config set site_block.enabled true` stays a plain config write — a config write never asks for a password — and prints the turn-on command when no helper is installed. Until one is, `status` reports site blocking as `not set up` rather than `off` or `unavailable`, names that command, and the listener raises no repeated "unavailable" notice: that notice is for a helper that is installed and failing.

### The Hyprland configuration

`setup` writes one file, [`~/.config/hypr/distraction-space.lua`](../hypr/), whose content is the three shipped snippets in order ([`hypr/windows.lua`](../hypr/windows.lua), [`hypr/bindings.lua`](../hypr/bindings.lua), [`hypr/autostart.lua`](../hypr/autostart.lua)), and appends one marked line to `~/.config/hypr/hyprland.lua` that loads it through Omarchy's optional-require helper. A rerun rewrites the file only when those snippets changed, and never over your edits: a file you changed is left as it is and reported, and deleting it gets you the shipped snippets again. It then asks Hyprland to reload; if Hyprland is not reachable, setup says a reload or a re-login is needed and continues. An install whose snippets were pasted by hand is handled as described under [moving a pasted 3.x install](#moving-a-pasted-3x-install).

### Root-owned files

This step runs only when site blocking is on, and it is the only step that needs a password. `setup` asks for sudo one time. It installs the nftables wrapper at `/usr/local/libexec/omarchy-distraction-space/distractions-nft` and the grant at `/etc/sudoers.d/omarchy-distraction-space`, and records what it installed in `/usr/local/libexec/omarchy-distraction-space/.installed.sha256` so a matching re-run needs no password. The grant lets only the installing user run that one wrapper without a password, which is how the listener keeps the firewall table in place.

### Everything else

Everything else is yours, no root involved. It copies the slice unit [`install/app-distraction.slice`](../install/app-distraction.slice) to `~/.config/systemd/user/` and starts it. That unit and the two WirePlumber files below are written without following a link: a symlink where one of those three goes, or at any directory setup opens on the way to it under `~/.config` or `~/.local/share`, is refused by name rather than written through, setup says which one to delete, and that run fails so you see it. It writes one launcher entry per listed product under `~/.local/share/applications/` whose `Exec` is `distractions open <name>`, named to shadow the app's system entry or Omarchy's own web-app entry; a file of that name it did not write is moved whole into `entries-backup/` under the state directory first, and every file it wrote goes into `entries.json`. Every other Omarchy web app in that directory (an `Exec` starting with `omarchy-launch-webapp`) is rewritten the same way, backup and record included, to `distractions open --app <url>`, which forwards it to the previous browser as an app window, so Omarchy's launcher never resolves a web app to the plugin's handler and opens it in the wrong browser.

It writes the URL handler entry `io.github.danielkillenberger.distraction-space.desktop`, records your current default browser, and, when links are on, makes the handler the default with `xdg-settings`. It installs a WirePlumber hook script under `~/.local/share/wireplumber/scripts/` and its config fragment under `~/.config/wireplumber/wireplumber.conf.d/` so a sound the distraction browser starts while the hold is on is muted the moment its stream is created, and restarts WirePlumber once when those files changed; setup says so when it does, and says so when the hook did not load, in which case sounds are muted a moment after they start instead. Then it clones and patches the notification service so the hold has a per-sender silenced list to write to.

Run it again after an Omarchy update or after editing the list, so the launcher entries follow it. `distractions setup --remove` reverses all of it. The bar widget lands in the center section; `omarchy bar move io.github.danielkillenberger.distraction-space --section right` moves it.

## Moving a pasted 3.x install

A 3.x install that pasted the three snippets by hand is left as it is: setup reports which file still holds the pasted lines, writes nothing, and the rest of the run still happens. Delete those pasted lines from `~/.config/hypr/hyprland.lua`, `bindings.lua`, and `autostart.lua`, and from your windows file if the workspace rule went there, then rerun `distractions setup`. Setup will not write over them: a second copy would start two listeners and register every bind twice. After the pasted lines are gone, setup writes `~/.config/hypr/distraction-space.lua` and one marked line in `hyprland.lua`.

## Remove

```bash
~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions setup --remove
omarchy plugin remove io.github.danielkillenberger.distraction-space
```

`setup --remove` hands the default browser back to the one it recorded, deletes exactly the launcher and handler files in `entries.json` and moves every backup home, Omarchy's web-app entries included, deletes the marked Hyprland line and the file setup wrote (an edited file is moved into `hypr-backup/` under the state directory, and remove prints where it went), destroys the nft table, stops and deletes the slice unit, deletes the WirePlumber hook and restarts WirePlumber, removes the wrapper, the sudoers grant, and that record with sudo, and removes the notification-service clone it created. At the slice unit and the two WirePlumber paths it deletes a plain file and nothing else: a symlink standing where one of them was, or anything else that is not a plain file, is left alone and named, and a fragment left that way keeps its script with it, because the feature that fragment still asks for would otherwise have no script to load. The browser profile at `~/.local/share/omarchy/distraction-space/browser` stays, and remove prints its path so you can delete it yourself. Run it before `omarchy plugin remove`, because the plugin directory holds the script that does the removing.

## What it does

**The space is a process group.** `distractions open <target>` is the one way in. It takes a URL, a list entry name, or a catalog name, and runs the launch as a transient scope in `app-distraction.slice` under your user manager. A web target starts the distraction browser with `--app=<url>` in the profile at `~/.local/share/omarchy/distraction-space/browser`, so its window class is `<browser>-<host>__-Distraction` and its process is not the work browser's. A native target runs its desktop entry. The launcher entries `setup` wrote and the URL handler both call `open`, so the app menu and links land there without you doing anything. Windows, network, and sound are all decided by that membership, never by which workspace you happen to be looking at.

**The distraction profile starts empty.** Listed web products run in their own browser profile, so each asks for a login once. To carry the logins over instead, close both browsers and run `distractions profile import`: it copies the default browser's main profile (`~/.config/google-chrome/Default` for Chrome; the matching directory for Chromium, Brave, Edge, and Vivaldi; `--from <dir>` names any other Chromium profile) into the distraction profile, minus the caches Chromium regenerates, so cookies, passwords, bookmarks, history, and extensions arrive in one go. It refuses while the source browser or the distraction browser is running, refuses a source that is not a Chromium profile, and refuses an existing distraction profile unless you pass `--replace`, which moves the existing one to `Distraction.bak-<date>` beside it and never deletes it. This is a one-time snapshot: nothing keeps the two profiles in sync afterwards, the copied extensions run in the distraction profile from then on, and your Google account shows as signed in on two profiles. It moves about a gigabyte and `setup` never runs it.

**Windows stay on one workspace.** Three layers, first match wins, all landing on `name:distraction` without stealing focus. One named Hyprland rule for the whole distraction profile plus one per native window class, set through `hyprctl eval` and re-applied when socket2 reports `configreloaded`, since Hyprland drops them on every config reload. The socket2 `openwindow` event is the safety net: a window whose process, or an ancestor within eight hops, is in the slice is moved there, which catches popups and helper windows with a plain browser class. And adoption: a listed product's web-app window from another browser profile is moved intact and offered a separate-profile launch through a notification action. Confirming opens a replacement in the distraction profile and never closes the original; drafts, calls, and navigation state cannot transfer, so save your work before you close the original yourself. Moving it does not change its process group or exempt it from site blocking. Discovery, startup scans, and reloads never close it; cancelling or a failed replacement launch leaves it intact. `containment.snap_back` decides what a manual drag off the space does; `distractions release` exempts one window for a while. Super+Tab and Super+Shift+Tab skip the space, so cycling workspaces never drops you into it.

**Listed sites load only from the space.** The wrapper renders one static nftables table whose first rule accepts traffic from the slice's cgroup. After it, the sets `omarchy_ds_v4` and `omarchy_ds_v6` are rejected with a TCP reset, except ports 80 and 443, which are redirected to the plugin's routers on 28080 and 28443. The listener resolves each listed host on start, on `reload`, on `refresh`, and every 60 seconds. Reconciliation may skip an unchanged table only after a fresh full-policy check confirms the same slice identity; drift requires repair. An empty or disabled block is flushed; entering or leaving the space touches nothing. The router reads the Host header or the SNI from the ClientHello. A listed host, or a subdomain of one, gets the block page on 80 and a closed connection on 443. Any other hostname on that shared address is spliced to its real destination, so Google Safe Browsing keeps working while YouTube is listed. The splices leave through TCP source ports 61000 to 61999, which the wrapper lets past the block, and at most 256 run at once. `site_block.pass_through: false` restores the plain address block. `site_block.enabled: false` destroys the table and stops resolving; everything else keeps working.

**Moved, and blocked.** Two separate things happen to a listed app. Its windows move to the distraction space, and its hosts are reachable only from the space's process group. Every catalog product gets the first. Messaging apps skip the second, so a chat still delivers while its window stays out of sight.

| | Windows moved | Network blocked outside the space |
|---|---|---|
| Telegram, Discord, WhatsApp, Signal, Google Messages | yes | no |
| X, Facebook, Instagram, Threads, Reddit, TikTok, Snapchat, YouTube, Twitch, Netflix | yes | yes |

[`catalog.json`](../catalog.json) ships 19 products, the 15 above plus Bluesky, Pinterest, Tumblr, and LinkedIn. The default list is the 15. `distractions catalog` prints every name, and `distractions list add <name>` adds one. A custom entry with `hosts` is moved and blocked; a custom entry with only `class=<regex>` is moved and never blocked.

**Links open in the space.** With your yes at setup, the plugin is the default handler for `http` and `https`. A link to a listed host, or a subdomain of one, clicked in any app sends the exact URL, including its path, query, and fragment, to the distraction browser on the space while you stay where you are. Two links on the same host both reach the browser even when a matching window already exists. Opening a product by name may reuse its window. Unlisted links are forwarded to the browser that was the default before, untouched. While it is the default, `open` owns launching for everything: with no target, or with only browser flags (`--incognito`, `--private-window`), it runs the previous browser bare with the flags appended, which is what Omarchy's browser keybinds do, and `open --app <url>` forwards an unlisted URL as an app window, which is what the rewritten Omarchy web-app entries do. The listener re-runs the entry sync on `refresh` and once a minute, so a web app Omarchy regenerates is rewritten within a minute. The distraction profile is created with Chrome's "make this your default browser?" prompt off, and `profile import` sets the same preference in the copy; your main profile is never touched. If another program takes the default later, `status` reports `links: displaced`, one notice names `distractions setup` as the fix, and everything else keeps working. `open_links_in_space: false` skips the registration, and the entries are still rewritten.

**Two banners, one shape.** "`<Product>` opened in the distraction space" fires when a listed window lands there while you are on another workspace, by rule, by safety net, by adoption, or by `open`; its action enters the space, and while a lock is active the body says when the lock ends and the action shows the lock notice instead. "Blocked here" fires from the TLS router when the SNI names a listed host, since a blocked connection is by construction from outside the space; its action opens the site in the space. HTTP gets the block page instead. Each fires at most once per list entry per 60 seconds and never while you are on the space. `nudges.app_banner` turns off the opened banner, and `nudges.block_page` turns off the block page and the blocked banner together.

**Notifications wait, with a visible count.** While the hold is in effect, the listener pushes each listed app's sender keys into the notification service's per-sender silenced list, one IPC call per key. Those apps write to history and pop no banner. Each held ping goes into `held.jsonl`, the running total shows after the eye glyph in the bar, and the listener removes only the keys it added. `hold_notifications` chooses when the hold applies: `off-space` (the default), `locked`, or `never`.

**One line when you come back.** Entering the space or ending a lock shows a single notification titled "While you were away". By default its body is the per-app count, and nothing you were sent leaves the machine. Set `summary.command` to `auto` and the body comes from the agent you chose with `omarchy default agent` (`~/.config/omarchy/defaults/agent`), run once with the held records on stdin: `grok -p`, `claude -p --output-format text`, `codex exec -s read-only --skip-git-repo-check -`, `gemini -p`, `opencode run`, or `copilot -p`. pi, omp, and crush have no such one-shot form, so they, no chosen agent, and an agent missing from PATH show the count and write one line to the log. The agent gets `summary.timeout_seconds` (60 by default) before the count takes over; a `claude -p` reply took about 7 seconds when this was measured. Zero held notifications show nothing at all. `summary.after: "unlock"` keeps the notice for lock endings and lets entering the space clear the count silently.

**Sounds from the space mute.** With `mute_sounds` on, the listener mutes the PulseAudio streams of listed apps for the length of the hold. A stream whose process is in the slice is muted first, whatever its window class, which is what makes WhatsApp Web, Discord, and the other web apps mutable: their audio comes from a child of the distraction browser. Outside the slice it matches the catalog's audio identity against `application.name` and `application.process.binary`, as before, and never mutes a bare browser stream. It records what it muted as sink-input index plus `pid:starttime` and unmutes only a stream whose identity still matches, so a stream you muted yourself outside the space stays muted. When the hold ends, and once when the listener starts while the hold is off, it also unmutes any muted stream whose process is still in the slice, record or no record, so a mute that outlived its record (across a listener restart, say) does not stay stuck. Every mute, unmute, and dropped record is one line in the plugin log.

**The lock runs for a set time.** `distractions lock` asks you to type whole minutes (with the configured default shown as an example; `0` means until manual unlock) and what the time is for, then refuses `enter` until the deadline. Locking while you are on the space leaves it first. Leaving early takes `distractions unlock` with a reason of at least 50 characters, and the plugin appends the time, the purpose, and the reason to its log. The native reason prompt opens wider and fits within the screen edges. It remains a single-line input, so very long reasons are elided while editing. There is no start-locked setting, so the lock never begins on its own.

## Limits

- The hostname router cannot see through Encrypted Client Hello. A listed site served behind ECH presents the provider's public name in the outer ClientHello, so it passes through.
- The pass-through exemption is TCP source ports 61000 to 61999, above the default `net.ipv4.ip_local_port_range` ceiling of 60999. On a machine whose sysctl widens that range past 61000, an ordinary connection can draw an exempt port and bypass the block.
- HTTPS cannot show the block page without a certificate your browser trusts. The banner is the only feedback on port 443.
- No Firefox web apps. Firefox has no `--app` window with a host-bearing class, so a Firefox default gets `chromium` for the web products, as Omarchy itself does. With no Chromium-family browser installed, `open` for a web target exits 1 with a notice and web products fall back to containment by class with no launch path.
- The accept rule is `socket cgroupv2 level 5`, which needs a kernel and nftables that support cgroup2 socket matching. When `nft` refuses it, or the slice's cgroup directory is missing, the wrapper exits 1, `status` reports `site_block: unavailable`, and nothing else degrades. On kernel 7.1.9 with nftables 1.1.6, live checks verified outside-slice refusal and inside-slice delivery to the same Reddit HTTPS address. Separate disposable-network-namespace checks applied and verified the table, detected rule/table drift, repaired it, and exercised packet rejection/acceptance. These results cover the tested policy and platform, not every site or protocol; see the [validation record](internals.md#recorded-live-validation).
- Chromium hands a second launch of the same profile to the running instance, and that instance keeps its existing scope and audio environment. A fresh known Chrome/Chromium launch reserves the browser's portal scope inside the slice; unknown or forking wrappers and other brands/channels remain unverified.
- Chrome 152.0.7977.64 through the tested Omarchy Chrome wrapper kept browser and audio processes in the slice on PipeWire 1.6.8 / WirePlumber 0.5.15. The listener muted a disposable distraction stream, its owned-stream release restored it, and existing and newly started work-browser streams stayed unmuted. That check predates the slice sweep, which now releases a pre-muted stream, including mute restored after an interrupted session, when its process is in the slice. This check used local WebAudio and does not establish every site, browser, wrapper, or a global leave/unlock transition. See the [validation record](internals.md#recorded-live-validation).
- The profile window class `<browser>-<host>__-Distraction` was verified with google-chrome. Brave, Edge, Opera, Vivaldi, and Helium are assumed to honor `--profile-directory` in the class the same way; the rule accepts any prefix, but none of them has been launched here.
- A cold work browser forwarded by a handler that inherited the distraction browser's audio environment can inherit its mute restore identity and start muted. The independently launched work-browser checks do not cover that path.
- The notification hold needs the patched service clone until Omarchy ships a per-sender silenced list of its own. Without it, `status` reports `notification_hold: unavailable`, one notice names the fix, and everything else keeps working.
- `hyprctl keyword` refuses on Omarchy 4's Lua config, which is why the window rules go through `hyprctl eval`.
- `setup --remove` leaves the browser profile in place. Delete `~/.local/share/omarchy/distraction-space/browser` yourself when you want the logins gone.
- Site blocking needs sudo once and writes two root-owned files. Read [`distractions-nft`](../distractions-nft) and [`install/sudoers.omarchy-distraction-space`](../install/sudoers.omarchy-distraction-space) before you say yes; nothing else in the plugin asks for a password.

## Configuration

`~/.config/omarchy/distraction-space.json`, honoring `$XDG_CONFIG_HOME`. Missing keys take the default. Unknown keys survive a save. `distractions config get <key>` and `distractions config set <key> <value>` read and write one key; `distractions menu` edits the list, the nudges, the hold, the mute, the lock, and the summary from a menu.

| Key | Default | What it sets |
|---|---|---|
| `list` | the 15 defaults | Catalog name, hostname, `class=<regex>`, or an object with `name` plus `class` or `hosts` |
| `keep_reachable` | `[]` | Hosts whose addresses stay out of the block, even when a listed site shares one |
| `site_block.enabled` | `true` | Render and maintain the nftables table at all; `false` destroys it and stops resolving. Absent until `setup` asks or `distractions site-block` answers; an installed helper counts as a yes |
| `site_block.pass_through` | `true` | Splice unlisted hostnames on a blocked address to their real destination; `false` refuses every connection to the address |
| `browser` | `"auto"` | The distraction browser: `auto` takes the Omarchy default when it is Chromium-family, else `chromium`; or an argv array |
| `open_links_in_space` | `true` | Register the URL handler at `setup` and keep it; `false` skips it, and `open` still works when called directly. Absent until `setup` asks; the answer is written here |
| `containment.snap_back` | `true` | Revert a manual move of a contained window off the space; `false` contains on `openwindow` only |
| `containment.release_minutes` | `30` | How long `distractions release` exempts a window with no duration given, at most 10080 (one week) |
| `nudges.app_banner` | `true` | The opened banner when a listed window lands on the space while you are on another workspace |
| `nudges.block_page` | `true` | The block page on port 80, and the blocked banner for a listed HTTPS host |
| `hold_notifications` | `"off-space"` | When the hold applies: `off-space`, `locked`, or `never` |
| `mute_sounds` | `true` | Mute the space's audio streams, and listed apps' streams outside it, during the hold |
| `lock.default_minutes` | `25` | The example shown in the native minutes prompt |
| `lock.ask_purpose` | `true` | Ask what the locked time is for |
| `lock.reason_min_chars` | `50` | Characters required to unlock early; `0` unlocks with no prompt |
| `summary.command` | `"off"` | `off`, `auto` (the agent from `omarchy default agent`), or an argv array that reads the held records on stdin |
| `summary.timeout_seconds` | `60` | How long that command gets before the per-app count takes over |
| `summary.after` | `"any"` | When the notice shows: `any` (a lock ending, or entering the space) or `unlock` (a lock ending only; entering the space still clears the count and runs the enter hook, silently) |
| `hooks.lock` / `unlock` / `enter` / `leave` | `[]` | Argv arrays run detached with `DS_EVENT`, `DS_PURPOSE`, `DS_MINUTES`, `DS_REASON`, `DS_HELD` |
| `log` | `~/.local/state/omarchy/distraction-space/log` | Where lock reasons, hook output, network batches, and banner decisions go |

With no config file, the first load seeds `list` from your existing `~/.config/omarchy/app-list.json` and `focus.json`, and falls back to the 15 defaults.

The menu can release the window that was focused before the menu opened, for `containment.release_minutes`. Settings includes “Open listed links in the space”, “Block listed sites outside the space”, and “Return moved windows to the space”. Each shows the saved choice separately from its last observed behavior. Browser-routing changes still need `distractions setup`; site blocking that is saved on but has no helper reads “not set up” and the same row turns it on, in a terminal when the password is needed; snap-back is applied on reload but is not independently verified by status. A cancelled or invalid edit leaves the saved choice unchanged.

## Commands

`distractions <command>`, at `~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions`. Exit 0 on success, 1 on a refused or failed action, 2 on usage.

| Command | What it does |
|---|---|
| `status [--json]` | Lock, workspace and containment state, plus `health` reasons and per-service `observed_at`. Site blocking reads `on`, `off`, `unavailable`, or `not set up` when it is switched on with no firewall helper installed. `updated` is the saved state timestamp; `response_at` is this read. Works without a listener and reports it stopped. |
| `open [--app] [url\|path\|name] [browser flags...]` | Deliver an exact listed URL, or launch a list entry or catalog product by name with existing-window reuse. An unlisted URL is forwarded to the previous default browser, as an app window with `--app`; so is a `file:` or `about:` URL as given, and a path to an existing regular file as its `file://` URL, neither of which ever opens in the space. A name is tried before a path, so a file named like a list entry or catalog product wants `./` in front; no target forwards the bare browser, and `-` flags pass through to it unchanged. Exit 1 when no browser can be started or the link had no forwarder, 2 on a malformed URL, any other scheme, or a bare argument that is neither a name nor an existing regular file. |
| `migrate ADDRESS IDENTITY` | Notification action: confirm a separate-profile product launch for the still-matching original window. The notification supplies the identity. Cancelling, failure, and success all leave the original open. |
| `profile import [--from DIR] [--replace]` | Copy the default browser's main profile, or the Chromium profile at `DIR`, into the distraction profile once, skipping caches, and print the destination and the byte count. Exit 1 while either browser runs, when the source is not a Chromium profile or overlaps the destination, or when the destination exists without `--replace`. |
| `toggle` / `enter` / `leave` | Enter or leave the space. `enter` refuses while locked. |
| `next` / `prev` | Cycle occupied workspaces, skipping the space. |
| `lock [MINUTES\|forever] [PURPOSE...]` | Lock. No arguments opens the minutes input, then the purpose input. Leaves the space first when you are on it. |
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
| `refresh` | Ask the running listener to re-resolve the listed hosts and reconcile the table now, without re-reading the config, and to re-run the launcher entry sync. Exit 1 when no listener runs or the batch failed. |
| `setup [--yes] [--remove]` | Install or remove the privileged wrapper, the Hyprland config file and its marked line, the slice unit, the launcher entries, the URL handler, and the patched notification-service clone. The first run asks whether to route links through the space and whether to block listed sites outside it, both before anything asks for a password. The wrapper is installed only for a yes, and a no, a refusal, or a cancelled password costs site blocking alone: every other step still runs, and only the exit code says so. `--yes` takes the config value for links (`true` by default), leaves an unanswered site-block question unanswered, and runs sudo with `-n`, so it never prompts for anything. |
| `site-block on\|off` | Turn site blocking on or off after setup. `on` records the answer, installs the firewall helper when it is missing or out of date — the one moment it asks for a password — and has the listener apply the block; `off` records the answer and the table is destroyed, leaving the helper installed. Exit 1 when the helper could not be installed, with the answer left on, or when `on` has no terminal and no helper; 2 for anything but `on` or `off`. |
