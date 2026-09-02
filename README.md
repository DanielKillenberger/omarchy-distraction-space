# Omarchy distraction space

One named Hyprland workspace for the apps and sites that take your attention, and a plugin that keeps them there.

![The Omarchy bar showing the distraction-space eye glyph with three held notifications, and the "While you were away" notice listing the per-app count](preview.png)

You list Telegram, X, YouTube, and whatever else pulls you off task. Their windows open on the workspace `name:distraction` and get moved back when they land anywhere else. Their sites are refused at the network while you work elsewhere, so the tab you opened out of habit gets a block page instead of the feed. Their notifications wait, native apps' sounds stay muted, the bar shows how many are waiting, and when you come back one notice tells you what was held, per app, or, if you turn it on, one line from your own agent saying whether any of them needed you. Lock the space for 25 minutes and it refuses to open until the timer runs out or you type 50 characters saying why you are leaving early.

## Install

Omarchy 4, Hyprland, Python 3.11.

```bash
omarchy plugin add https://github.com/DanielKillenberger/omarchy-distraction-space.git --enable
```

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

`setup` asks for sudo one time. It installs the nftables wrapper at `/usr/local/libexec/omarchy-distraction-space/distractions-nft` and the grant at `/etc/sudoers.d/omarchy-distraction-space`, then clones and patches the notification service so the hold has a per-sender silenced list to write to. Run it again after an Omarchy update. `distractions setup --remove` reverses all of it. The bar widget lands in the center section; `omarchy bar move io.github.danielkillenberger.distraction-space --section right` moves it.

Installs from before 2.1.0 used the id `distraction-space`. To move to the new id: `omarchy plugin remove distraction-space`, add the plugin again with the command above, copy the three snippets again (the helper path changed), and run `distractions setup`.

Autostart owns the long-running listener. To start it now without logging out:

```bash
~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions listen
```

## What it does

**Windows stay on one workspace.** The listener installs one named Hyprland rule per listed window class through `hyprctl eval` and `hl.window_rule`, so a listed app opens on `name:distraction` directly. Hyprland drops those rules on every config reload, and the listener re-applies them when socket2 reports `configreloaded`. The socket2 `openwindow` event is the safety net. A listed window that lands elsewhere anyway gets moved there without stealing focus. Super+Tab and Super+Shift+Tab skip the space, so cycling workspaces never drops you into it.

**Listed sites stop loading off the space.** Every 30 seconds while you are off the space, the listener resolves each listed host and drops the addresses into the nftables sets `omarchy_ds_v4` and `omarchy_ds_v6`. The wrapper rejects traffic to a member address with a TCP reset, except ports 80 and 443, which it redirects to the plugin's routers on 28080 and 28443. The router reads the Host header or the SNI from the ClientHello. A listed host, or a subdomain of one, gets the block page on 80 and a closed connection on 443. Any other hostname on that shared address is spliced to its real destination, so Google Safe Browsing keeps working while YouTube is listed. The splices leave through TCP source ports 61000 to 61999, which the wrapper lets past the block, and at most 256 run at once. `site_block.pass_through: false` restores the plain address block. Entering the space flushes the sets, so the same sites load normally once you are there.

**A banner names what you reached for.** A listed window that opens off the space raises one notification starting with the app's name. A blocked HTTPS fetch raises one titled "Blocked on this workspace", built from the host in the SNI. HTTP gets the block page instead of a banner. Both banners name Super+Ctrl+Shift+D as the way in and fire at most once per catalog entry per 30 seconds, and the blocked-fetch one fires only for fetches from windows outside the space, so a page you left open on the space keeps working without nagging you. `nudges.app_banner` turns off the window banner, and `nudges.block_page` turns off the block page and the HTTPS banner together.

**Notifications wait, with a visible count.** While the hold is in effect, the listener pushes each listed app's sender keys into the notification service's per-sender silenced list, one IPC call per key. Those apps write to history and pop no banner. Each held ping goes into `held.jsonl`, the running total shows after the eye glyph in the bar, and the listener removes only the keys it added. `hold_notifications` chooses when the hold applies: `off-space` (the default), `locked`, or `never`.

**One line when you come back.** Entering the space or ending a lock shows a single notification titled "While you were away". By default its body is the per-app count, and nothing you were sent leaves the machine. Set `summary.command` to `auto` and the body comes from the agent you chose with `omarchy default agent` (`~/.config/omarchy/defaults/agent`), run once with the held records on stdin: `grok -p`, `claude -p --output-format text`, `codex exec -s read-only --skip-git-repo-check -`, `gemini -p`, `opencode run`, or `copilot -p`. pi, omp, and crush have no such one-shot form, so they, no chosen agent, and an agent missing from PATH show the count and write one line to the log. The agent gets `summary.timeout_seconds` (60 by default) before the count takes over; a `claude -p` reply took about 7 seconds when this was measured. Zero held notifications show nothing at all.

**Sounds of listed apps mute.** With `mute_sounds` on, the listener mutes the PulseAudio streams of listed apps for the length of the hold, matching the catalog's audio identity against `application.name` and `application.process.binary`. It records what it muted as sink-input index plus `pid:starttime`, and unmutes only a stream whose identity still matches, so a stream you muted yourself stays muted.

**The lock runs for a set time.** `distractions lock` asks for a duration (25 minutes by default) and what the time is for, then refuses `enter` until the deadline. Leaving early takes `distractions unlock` with a reason of at least 50 characters, and the plugin appends the time, the purpose, and the reason to its log. There is no start-locked setting, so the lock never begins on its own.

## Keys

| Action | Keys |
|---|---|
| Open or leave the space | Super+Ctrl+Shift+D |
| Move the focused window there | Super+Alt+D |
| Lock, or unlock when locked | Super+Ctrl+Shift+F |
| Next occupied workspace, skipping the space | Super+Tab |
| Previous occupied workspace, skipping the space | Super+Shift+Tab |

The bar widget answers a left click with lock or unlock, a right click with the menu, and a middle click with the toggle.

## Moved, and blocked

Two separate things happen to a listed app. Its windows move to the distraction space, and its hosts leave the reachable network while you are elsewhere. Every catalog product gets the first. Messaging apps skip the second, so a chat still delivers while its window stays out of sight.

| | Windows moved | Network blocked off-space |
|---|---|---|
| Telegram, Discord, WhatsApp, Signal, Google Messages | yes | no |
| X, Facebook, Instagram, Threads, Reddit, TikTok, Snapchat, YouTube, Twitch, Netflix | yes | yes |

[`catalog.json`](catalog.json) ships 19 products, the 15 above plus Bluesky, Pinterest, Tumblr, and LinkedIn. The default list is the 15. `distractions catalog` prints every name, and `distractions list add <name>` adds one. A custom entry with `hosts` is moved and blocked; a custom entry with only `class=<regex>` is moved and never blocked.

## Limits

- The hostname router cannot see through Encrypted Client Hello. A listed site served behind ECH presents the provider's public name in the outer ClientHello, so it passes through.
- The pass-through exemption is TCP source ports 61000 to 61999, above the default `net.ipv4.ip_local_port_range` ceiling of 60999. On a machine whose sysctl widens that range past 61000, an ordinary connection can draw an exempt port and bypass the block.
- HTTPS cannot show the block page without a certificate your browser trusts. The banner is the only feedback on port 443.
- A web app running inside a shared Chrome window plays its audio through Chrome's single audio service process, so the plugin cannot attribute that stream to the web app and cannot mute it. WhatsApp Web's message tone still plays.
- The notification hold needs the patched service clone until Omarchy ships a per-sender silenced list of its own. Without it, `status` reports `notification_hold: unavailable`, one notice names the fix, and everything else keeps working.
- `hyprctl keyword` refuses on Omarchy 4's Lua config, which is why the window rules go through `hyprctl eval`.
- `setup` needs sudo once and writes two root-owned files. Read [`distractions-nft`](distractions-nft) and [`install/sudoers.omarchy-distraction-space`](install/sudoers.omarchy-distraction-space) before you run it.

## Configure

`~/.config/omarchy/distraction-space.json`, honoring `$XDG_CONFIG_HOME`. Missing keys take the default. Unknown keys survive a save. `distractions config get <key>` and `distractions config set <key> <value>` read and write one key; `distractions menu` does the same from a menu.

| Key | Default | What it sets |
|---|---|---|
| `list` | the 15 defaults | Catalog name, hostname, `class=<regex>`, or an object with `name` plus `class` or `hosts` |
| `keep_reachable` | `[]` | Hosts whose addresses stay out of the block, even when a listed site shares one |
| `site_block.pass_through` | `true` | Splice unlisted hostnames on a blocked address to their real destination; `false` refuses every connection to the address |
| `nudges.app_banner` | `true` | The banner when a listed app opens off the space |
| `nudges.block_page` | `true` | The block page on port 80, and the banner for a blocked HTTPS fetch |
| `hold_notifications` | `"off-space"` | When the hold applies: `off-space`, `locked`, or `never` |
| `mute_sounds` | `true` | Mute listed apps' audio streams during the hold |
| `lock.default_minutes` | `25` | The duration the lock menu offers first |
| `lock.ask_purpose` | `true` | Ask what the locked time is for |
| `lock.reason_min_chars` | `50` | Characters required to unlock early; `0` unlocks with no prompt |
| `summary.command` | `"off"` | `off`, `auto` (the agent from `omarchy default agent`), or an argv array that reads the held records on stdin |
| `summary.timeout_seconds` | `60` | How long that command gets before the per-app count takes over |
| `hooks.lock` / `unlock` / `enter` / `leave` | `[]` | Argv arrays run detached with `DS_EVENT`, `DS_PURPOSE`, `DS_MINUTES`, `DS_REASON`, `DS_HELD` |
| `log` | `~/.local/state/omarchy/distraction-space/log` | Where lock reasons, hook output, and network batches go |

With no config file, the first load seeds `list` from your existing `~/.config/omarchy/app-list.json` and `focus.json`, and falls back to the 15 defaults.

## Commands

`distractions <command>`, at `~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space/distractions`. Exit 0 on success, 1 on a refused or failed action, 2 on usage.

| Command | What it does |
|---|---|
| `status [--json]` | Lock, `on_space`, `site_block`, `hold`, `held`, `notification_hold`, and `pass_through`. Works with no listener running. |
| `toggle` / `enter` / `leave` | Enter or leave the space. `enter` refuses while locked. |
| `next` / `prev` | Cycle occupied workspaces, skipping the space. |
| `lock [MINUTES\|forever] [PURPOSE...]` | Lock. No arguments opens the duration menu, then the purpose input. |
| `unlock [REASON...]` | Unlock early with a reason of at least `lock.reason_min_chars` characters. |
| `list` / `list add` / `list remove` / `list expand` | Read and edit the list; `expand` prints the resolved classes, hosts, senders, and audio identity as JSON. |
| `catalog` | Every catalog product name, one per line. |
| `config path` / `get` / `set` / `edit` | Read and write the config file. `set` validates before it writes. |
| `menu` | The full menu: lock, enter or leave, edit the list, settings. |
| `senders` | The sender keys the hold pushes into the shell's silenced list. |
| `listen` | The listener. Autostart runs one per session; a second one exits 0 immediately. |
| `reload` | Ask the running listener to re-read the config. |
| `setup [--remove]` | Install or remove the privileged wrapper and the patched notification-service clone. |

## Internals

State file shapes, the listener loop, the network generation counter, the clone lifecycle, and the catalog format are in [`docs/internals.md`](docs/internals.md).

## Contributing

```bash
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
```

256 tests, offline, about 100 seconds. `tests/harness.py` gives every test its own temporary XDG root and puts fake `hyprctl`, `getent`, `busctl`, `pactl`, and nft binaries at the front of `PATH`, so a run never touches your session, your config, or your firewall. The `/usr/bin` prefix keeps a shim-based version manager out of the way. Under mise's `python3` shim, 20 of the 27 cases in `tests/test_hypr.py` fail here, because the child process resolves the real `hyprctl` instead of the fake. Plain `python3 -m unittest discover -s tests` is enough on a machine without one. Keep the suite offline in a pull request.

Lint the bar widget with `qmllint` from `qt6-declarative`; it is not on `PATH`. Quickshell maps `qs.*` onto the shell root, so a bare `-I "$OMARCHY_PATH/shell"` cannot resolve `qs.Commons` or `qs.Ui`. Give it an import directory whose `qs` entry links to the shell instead.

```bash
mkdir -p /tmp/qmlimports && ln -sfn "${OMARCHY_PATH:-/usr/share/omarchy}/shell" /tmp/qmlimports/qs
/usr/lib/qt6/bin/qmllint -I /tmp/qmlimports BarWidget.qml
```

One warning remains, `Member "iconSlot" not found on type "QObject"` at `Style.bar.iconSlot`. `Style.bar` is an inline `QtObject` whose declared properties qmllint cannot see through the bare `QObject` type, so the warning is noise. Anything else is a finding.

## License

MIT. See [`LICENSE`](LICENSE).
