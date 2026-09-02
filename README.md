# Omarchy distraction space

Every listed distraction lives on one named Hyprland workspace (`name:distraction`) and stays there. Listed apps open only on that space. Listed sites do not load anywhere else. Reaching for a distraction from a normal workspace earns a nudge that names the app or site and says Super+Ctrl+Shift+D opens the space. A lock makes the space unreachable for a chosen number of minutes, with a purpose stated up front and a written reason to leave early.

While you are off the space, listed apps also stay quiet: their notifications are held and their sounds are muted. When the hold ends, one line from your own agent (or a plain per-app count) says whether anything mattered.

This plugin is a small Python package, one config file an agent can read and edit, one shipped catalog, a shell patch delivered through Omarchy's plugin clone mechanism, and a menu UI built only from `omarchy-menu-select` and `omarchy-menu-input`.

## Install

Omarchy 4+, Hyprland, Python 3.11+.

```bash
omarchy plugin add https://github.com/DanielKillenberger/omarchy-distraction-space.git --enable
```

The bar widget appears in the center section. Move it if you want:

```bash
omarchy bar move distraction-space --section right
```

Copy the Hyprland snippets into your user config by hand. Plugin add does not edit Hyprland for you:

- `hypr/windows.lua` → `~/.config/hypr/hyprland.lua` (or your windows file)
- `hypr/bindings.lua` → `~/.config/hypr/bindings.lua`
- `hypr/autostart.lua` → `~/.config/hypr/autostart.lua`

Then:

```bash
chmod +x ~/.config/omarchy/plugins/distraction-space/distractions
hyprctl reload
```

Autostart owns the long-running listener (`distractions listen`). There is no forking. A second `listen` takes a non-blocking flock on `$XDG_RUNTIME_DIR/distraction-space.lock` and exits 0 with no output. Start it once without logging out if autostart has not run yet:

```bash
~/.config/omarchy/plugins/distraction-space/distractions listen
```

### One-time `distractions setup`

Run it once, and again after an Omarchy update. It does three things in order.

1. **Privileged wrapper.** Asks for sudo in the terminal, copies the wrapper to `/usr/local/libexec/omarchy-distraction-space/distractions-nft` (`install -D -m 0755`), renders the sudoers line into `/etc/sudoers.d/omarchy-distraction-space` (`install -m 0440` after `visudo -cf`), and refuses when any ancestor of either destination is writable by the invoking user. Skipped when the shipped file already matches.
2. **Notification-service clone.** Omarchy's notification service silences only globally (do not disturb). This plugin ships `shell/notifications-silenced-senders.patch`, which adds a per-sender silenced list next to it. While the first-party service under `/usr/share/omarchy/shell/plugins/notifications` lacks that method, setup runs `omarchy-plugin-clone omarchy.notifications`, applies the patch inside the clone (dry run first), and records the SHA-256 of every first-party file plus the patch in `clone.json`. Nothing under `/usr/share` is touched. On a later run: unchanged fingerprint, nothing to do; changed first-party files (an Omarchy update), re-clone and re-apply; a patch that no longer applies, remove the clone so the untouched built-in comes back, report the hold unavailable, exit 1; the built-in now carrying the method, remove the clone. A `<user>.notifications` clone this plugin did not create (no matching `clone.json`) is reported and left alone, and the hold stays unavailable.
3. **Rescan.** `omarchy-shell shell rescanPlugins`, so the shell picks up the clone or its removal. A rescan that is missing from PATH or exits non-zero leaves the installed files in place, prints the failure, and exits 1.

```bash
~/.config/omarchy/plugins/distraction-space/distractions setup
```

A missing wrapper skips only the site block. Window placement still runs. `site_block` in `status --json` becomes `unavailable`. A missing or unpatched notification service skips only the hold: `notification_hold` becomes `unavailable`, capture and mute still run, and one notice names the fix.

To reverse the grant:

```bash
~/.config/omarchy/plugins/distraction-space/distractions setup --remove
```

That flushes table `inet omarchy_ds`, removes both files, removes the notification-service clone when this plugin created it, and rescans the same way.

Removing a clone first disables it through the shell (`omarchy-shell shell setPluginEnabled <id> false`) and refuses to delete the directory when that call fails, so a shell that is down is never left without a notification server.

## Keys

| Action | Keys |
|---|---|
| Open or leave the distraction space | Super+Ctrl+Shift+D (`distractions toggle`) |
| Move the focused window there | Super+Alt+D |
| Lock or unlock | Super+Ctrl+Shift+F (unlock when locked, otherwise lock) |
| Next occupied workspace (skips the space) | Super+Tab |
| Previous occupied workspace (skips the space) | Super+Shift+Tab |

The workspace rule is `hl.workspace_rule({ workspace = "name:distraction", persistent = true })`. Super+1–0 and the bar never land here.

Bar widget (eye glyph, urgent color while locked, the held total after the glyph while pings are waiting, tooltip with deadline, purpose, and held count; watches `state.json`, never polls):

| Click | Command |
|---|---|
| Left | `distractions lock` or `unlock` |
| Right | `distractions menu` |
| Middle | `distractions toggle` |

## Config

Path: `~/.config/omarchy/distraction-space.json` (`$XDG_CONFIG_HOME` honored). Missing keys take the defaults shown. Unknown keys are kept on save and ignored. There is no start-locked key: the lock never starts on its own.

```json
{
  "list": ["Telegram", "Discord", "x.com", {"name": "Slack", "class": "^Slack$", "hosts": ["slack.com", "app.slack.com"]}],
  "keep_reachable": [],
  "nudges": {"app_banner": true, "block_page": true},
  "hold_notifications": "off-space",
  "mute_sounds": true,
  "lock": {"default_minutes": 25, "ask_purpose": true, "reason_min_chars": 50},
  "summary": {"command": "auto", "timeout_seconds": 60},
  "hooks": {"lock": [], "unlock": [], "enter": [], "leave": []},
  "log": "~/.local/state/omarchy/distraction-space/log"
}
```

Defaults for a fresh file (no migration sources):

- `list`: Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, Netflix
- `keep_reachable`: `[]`
- `nudges.app_banner`, `nudges.block_page`: `true`
- `hold_notifications`: `"off-space"`
- `mute_sounds`: `true`
- `lock.default_minutes`: `25`
- `lock.ask_purpose`: `true`
- `lock.reason_min_chars`: `50`
- `summary.command`: `"auto"`
- `summary.timeout_seconds`: `60`
- `hooks.lock` / `unlock` / `enter` / `leave`: `[]`
- `log`: `~/.local/state/omarchy/distraction-space/log`

`list` entries are a catalog name, a hostname (contains a dot, no scheme or path), a string `class=<regex>`, or an object with `name` and at least one of `class` or `hosts`. A hostname entry expands to itself plus its `www.` twin; a `class=` entry has no hosts.

`hold_notifications` is one of `off-space`, `locked`, `never` and `mute_sounds` is a boolean; both are described under Notification hold. `summary.command` is `auto`, `off`, or an argv array and `summary.timeout_seconds` bounds it; see Summary.

`hooks.*` are argv arrays run detached with env `DS_EVENT`, `DS_PURPOSE`, `DS_MINUTES`, `DS_REASON`, `DS_HELD`. `DS_HELD` is a JSON object of app name to held-notification count on `unlock` and `enter` (the counts the summary is about to show) and `"{}"` on `lock` and `leave`. stdout and stderr go to `log`. Failures are ignored.

Every write goes through a flock on `$XDG_RUNTIME_DIR/distraction-space.config.lock` (blocking, 5 s timeout). On timeout the command exits 1 with "config busy" and the file is unchanged. `config set`, `list add`, `list remove`, and every menu save use it. Reads take no lock. A successful mutation asks the running listener to reload.

Addresses that also serve a `keep_reachable` host are left out of the nftables set, so a shared CDN address does not take an allowed host down with a listed one.

### Migration

On first load with no `distraction-space.json`, `list` is seeded from names in `~/.config/omarchy/app-list.json` and `destinations` in `~/.config/omarchy/focus.json` (union), else the fifteen defaults. `log` is taken from the old `focus.json` when present. Old files stay untouched. Old state files under `~/.local/state/omarchy/` are ignored. Unreadable old files fall back to defaults.

## Catalog

### What gets moved, and what gets blocked

Two independent things happen to a listed app: its windows (native app and installed web app) move to the distraction space, and its hosts are dropped from the network off-space. Every catalog product gets the first. Messaging apps skip the second, so a chat still connects while you work and only its window is kept out of sight.

| | Windows moved | Network blocked off-space |
|---|---|---|
| Telegram, Discord, WhatsApp, Signal, Google Messages | yes | **no** |
| X, Facebook, Instagram, Threads, Reddit, TikTok, Snapchat, YouTube, Twitch, Netflix | yes | yes |

A custom entry with `hosts` is moved and blocked; a custom entry with only `class` is only moved.


Shipped `catalog.json` maps product name to identity. Two shapes exist, native and PWA. Expansion produces `classes`, a list: the native `class` when present, plus for every host-bearing entry the automatic PWA class `^chrome-<host>__.*$` for its first host (the `pwa` host when given), so any listed site's installed web app is contained alongside the native app.

Native (class plus the `pwa` host; messaging apps ship `hosts: []` so they are never blocked; `senders` are the app's notification sender names and `audio` its PulseAudio stream identity, both used by the hold):

```json
"Telegram": {
  "class": "org.telegram.desktop",
  "pwa": "web.telegram.org",
  "hosts": [],
  "senders": ["Telegram Desktop", "org.telegram.desktop"],
  "audio": {"name": ["Telegram Desktop"], "binary": ["telegram-desktop", "Telegram"]}
}
```

PWA only (`pwa` host, empty `hosts`, so the web app is moved and nothing is blocked):

```json
"Discord": {"pwa": "discord.com", "hosts": []}
```

Hosts only:

```json
"YouTube": {"hosts": ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"]}
```

Telegram therefore expands to `classes: ["org.telegram.desktop", "^chrome-web\\.telegram\\.org__.*$"]`. A `class=` list entry expands to one class and no hosts.

Catalog products: the fifteen defaults above, plus Bluesky, Pinterest, Tumblr, LinkedIn (add those yourself). `distractions catalog` prints every product name, one per line.

## CLI

`distractions <command>`. Exit 0 on success, 1 on a refused or failed action, 2 on usage. The helper path is `~/.config/omarchy/plugins/distraction-space/distractions`.

| Command | What it does |
|---|---|
| `status [--json]` | Human summary, or the `state.json` shape computed live (lock, `on_space`, `site_block`, `hold`, `held`, and `notification_hold` from the last listener write, `listener_pid` null when absent or dead). Works without a listener. Missing hyprctl sets `on_space` null. |
| `toggle` | Super+Ctrl+Shift+D: enter when off the space, leave when on it. |
| `enter` | Switch to `name:distraction` immediately. Refuses with the lock notice while locked. |
| `leave` | Cycle to the next occupied workspace, skipping the space. |
| `next` / `prev` | Cycle occupied workspaces (`windows > 0`), skipping `name:distraction`. |
| `lock [MINUTES\|forever] [PURPOSE...]` | No args opens the duration menu (default_minutes, 50, 90, Until I unlock, Other…) then the purpose input when `ask_purpose`. Already locked is a no-op with exit 0. Escape on the duration menu locks nothing. Escape on the purpose input still locks with an empty purpose. |
| `unlock [REASON...]` | Expired or unlocked is a no-op. Manual unlock requires `reason_min_chars` characters (default 50); shorter refuses with exit 1 and a notice. `reason_min_chars` 0 unlocks without a prompt. Appends timestamp, purpose, and reason to `log`. |
| `list` | Print each entry's display name, one per line. |
| `list add <entry>` | Append a catalog name, hostname, `class=<regex>`, or JSON object. Duplicate names are ignored. |
| `list remove <name>` | Remove by display name. Missing name exits 1. |
| `list expand` | JSON of the expansion (`name`, `classes`, `hosts`, `senders`, `audio`). |
| `catalog` | Product names, one per line. |
| `config path` | Print the config file path. |
| `config get <dot.key>` | Print the value as JSON. |
| `config set <dot.key> <json-or-string>` | Validate against the schema and write. Invalid values refuse with exit 1; the file is unchanged. |
| `config edit` | Open `$EDITOR` or `omarchy-launch-editor` on the config file. |
| `menu` | Select menu: Lock… / Unlock…, Open the space / Leave the space, Edit list, Settings. Edit list toggles catalog products and custom entries. Settings flips booleans, cycles enums, prompts integers; `keep_reachable`, `hooks.*`, and `log` are read-only with a notice naming `config set`. |
| `listen` | The daemon. Autostart starts one per session. SIGTERM calls `net.shutdown()` so an in-flight `getent` cannot pin exit past about 3 s. |
| `reload` | Connect to `$XDG_RUNTIME_DIR/distraction-space.sock`, send `reload\n`, wait for `ok\n` or `error\n`. Exit 1 with "No listener running" when none runs. An invalid config on reload answers `error` and leaves window rules and the site block unchanged. `refresh\n` is the other socket verb (same reply). |
| `setup [--remove]` | Install or remove the wrapper and sudoers, create, refresh, or remove the notification-service clone, then rescan, as above. |
| `senders` | The sender keys the listener pushes into the shell's silenced list, one per line. |

## State files

Under `~/.local/state/omarchy/distraction-space/` (`$XDG_STATE_HOME` honored):

| File | Writer | Shape |
|---|---|---|
| `lock.json` | `lock` / `unlock` only | `{"locked": true, "since": "<iso>", "until": "<iso>\|null", "purpose": "<text>"}` |
| `state.json` | Listener only, on every change; the bar watches this | `{"locked": false, "until": null, "purpose": "", "on_space": false, "site_block": "on", "listener_pid": 1234, "hold": true, "held": {"Telegram": 3}, "notification_hold": "on", "updated": "<iso>"}`. `site_block` is `on`, `off` (on the space or empty list), or `unavailable`. `hold` is whether the hold is in effect, `held` the per-app count of notifications held so far, `notification_hold` is `on`, `off`, or `unavailable` (the shell lacks the silenced list). Without a listener the file goes stale; `status --json` still works from `lock.json` and hyprctl. |
| `expansion.json` | Listener after every successful config load or reload | Last validated expansion (the full `{name, classes, hosts, senders, audio}` list plus `keep_reachable` and `nudges`). Invalid-config fallback: enforce from this cache; with no cache, enforce nothing and report `site_block: off`. |
| `held.jsonl` | Listener while the hold is in effect; consumed by the summary | One line per held notification: `{"at": "<iso>", "app": "Telegram", "title": "<summary>", "body": "<body>"}`, fields clipped at 4096 bytes, the newest kept under 64 KiB. Removed when the summary takes them. |
| `muted.json` | Listener while the hold is in effect | Sink-input index to `pid:starttime` of every stream this plugin muted; cleared once all are unmuted. |
| `clone.json` | `setup` | What the notification-service clone was made from: plugin id, paths, SHA-256 of each first-party file and of the patch. Its presence is what marks the clone as this plugin's. |
| `addrs.json` | Network resolver | Last good resolution per host. |
| `rules.json` | Window containment | JSON array of Hyprland rule-name strings this plugin set. |
| `log` | Lock reasons, lock/unlock/enter/leave hook output, network batches | Text. Override with config `log`. |

Runtime files in `$XDG_RUNTIME_DIR`:

| File | Role |
|---|---|
| `distraction-space.lock` | Single listener |
| `distraction-space.config.lock` | Config mutation flock |
| `distraction-space.sock` | Reload / refresh |

Lock expiry is lazy. `is_locked()` treats `until` in the past as unlocked. The listener's one-second tick notices the transition, rewrites `state.json`, notifies "Lock ended", and runs the `unlock` hook.

Hook ownership: `lock` / `unlock` commands run those hooks because they write `lock.json`. The listener runs `unlock` for a lazy expiry it observes, and `enter` / `leave` on every observed workspace transition onto or off the space. `enter`, `leave`, and `toggle` never run hooks themselves. Without a listener, `enter`/`leave` hooks, the expiry `unlock` hook, and the summary for those two boundaries do not fire; a manual `unlock` still summarizes.

## Listener

Hyprland autostart starts one listener per session with the shipped line in `hypr/autostart.lua`. Production connects to `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock`. Tests may set `DS_SOCKET2` to a Unix socket.

On start, on every workspace change off the space, on reload, and every 30 s while off the space, the listener resolves listed hosts (`getent ahosts`, 2 s per host, 10 s batch deadline), subtracts `keep_reachable` addresses, and pipes one address per line to `sudo -n /usr/local/libexec/omarchy-distraction-space/distractions-nft replace ds` (the installed path the sudoers grant names). Entering the space sends `flush ds`. The wrapper's filter output chain `reject`s set members (TCP reset for TCP, ICMP unreachable otherwise) and a nat output chain redirects TCP 80 to 28080 and TCP 443 to 28443 on set members.

When `nudges.block_page` is true, loopback HTTP on 28080 serves a block page naming the Host header with the Super+Ctrl+Shift+D line (and a lock note when locked). Port 28443 reads the ClientHello (SNI) and closes; one banner per host per 30 s. Nothing is served on 28443 beyond that read.

Window rules: one named rule per class in every expanded entry (`windowrule[omarchy-ds-<slug>-<n>]`), recorded in `rules.json`. socket2 `openwindow` / `movewindow` silently moves a listed client found off the space. When `nudges.app_banner` is on and the person is off the space, one banner per app per 30 s: title "`<Name>` lives in the distraction space", body "Super+Ctrl+Shift+D opens it.", click action `distractions enter`.

Config mutations already call reload after a successful write.

## Notification hold

The hold is in effect when `hold_notifications` is `off-space` and you are not on the space, or `locked` and a lock is active. `never` turns it off. While it is in effect, listed apps do not pop a banner; the notification service takes its do-not-disturb path for them (no popup, written to history) and the plugin records each one.

**Who is quiet.** The listener pushes sender keys into the shell's silenced list: the catalog `senders` of every listed native app, the `pwa` host of every PWA entry, and the hosts of every plain or custom hostname entry. `distractions senders` prints them. A sender key is the notification's `app_name` or, for a Chromium-derived sender (any browser or installed web app), the site host Chromium prepends to the body. Matching is case-insensitive and ignores a leading `www.`. Keys you silenced by hand in the shell are kept in both directions; when the hold ends only the plugin's keys are removed, and a clean listener exit removes them too. The shell persists its list, so a hold survives a shell restart.

**What is recorded.** The listener keeps `busctl --user monitor` on the session bus for its whole life (restarted with 1, 4, 16 s backoff if it exits) and, while the hold is in effect, appends every Notify from a listed sender to `held.jsonl` under the list entry's name. `state.json.held` carries the per-app counts and the bar shows the total after the glyph. A Notify it cannot attribute is left alone. Missing `busctl` turns capture off with one log line; holding and muting still work and the summary has nothing to show.

**Unavailable.** If the shell has no silenced list (setup has not run, or the patch could not be applied), `notification_hold` is `unavailable`, one notice points at `distractions setup`, and banners appear as usual while capture and mute continue. Everything from before the hold (containment, site block, lock, menu, hooks) behaves the same either way.

## Sound mute

With `mute_sounds` true, streams of listed apps are muted while the hold is in effect and unmuted when it ends. The listener identifies streams from `pactl -f json list sink-inputs` and a `pactl subscribe` feed by catalog `audio.name` / `audio.binary` against `application.name` / `application.process.binary`, or, for a Chromium web app, by the `--app=<url>` or `--app-id=<host>` flag in the command line of the stream's process or one of up to eight ancestors. A bare browser stream is never treated as a listed app. What the plugin muted is recorded in `muted.json` as index to `pid:starttime`; only a recorded index whose identity still matches is unmuted, so a stream you muted yourself and a reused index are both left alone. A stream that cannot be attributed stays audible; a web app opened into an already running browser shares that browser's process and is one such case. Missing `pactl` turns the feature off with one log line. A stream that could not be unmuted is retried every 16 s until it is.

## Summary

When a lock ends or the space is entered, the records in `held.jsonl` are claimed (the file is renamed away, then read), their per-app counts go to the `unlock` or `enter` hook as `DS_HELD`, and one notification titled "While you were away" shows. Zero records show nothing. Whoever marks the boundary does this: `distractions unlock` for a manual unlock (the command returns after the notice), the listener for a lock expiry and for entering the space. Because the claim is atomic, the hook's counts and the notice come from the same records, a second boundary during a slow agent call has nothing to repeat, and pings held meanwhile wait for the next summary.

The body comes from `summary.command`:

- `auto`: `claude -p --output-format text` when `claude` is on PATH, else `grok -p`, else the grouped count.
- an argv array: run as given.
- `off`: the grouped count.

The command gets the prompt on stdin (a request for one or two plain sentences in the second person on whether anything needs attention, followed by the records as JSON lines) and answers on stdout. At most 64 KiB of stdout and 4 KiB of stderr are read; the reply is collapsed to one line and clipped to 800 bytes. A non-zero exit, a timeout at `summary.timeout_seconds`, or an empty reply falls back to the grouped count, `Telegram 3 · Discord 1`, most held first. The command runs on the person's own machine as the person; there is no sandbox beyond the timeout and the clip.

## License

MIT
