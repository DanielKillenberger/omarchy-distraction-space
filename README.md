# Omarchy distraction space

Every listed distraction lives on one named Hyprland workspace (`name:distraction`) and stays there. Listed apps open only on that space. Listed sites do not load anywhere else. Reaching for a distraction from a normal workspace earns a nudge that names the app or site and says Super+Ctrl+Shift+D opens the space. A lock makes the space unreachable for a chosen number of minutes, with a purpose stated up front and a written reason to leave early.

This plugin is a small Python package, one config file an agent can read and edit, one shipped catalog, and a menu UI built only from `omarchy-menu-select` and `omarchy-menu-input`. Notification holding, sound muting, and the agent summary are not in this release; they land in fn-10 on the listener, schema, and state file defined here. Between the two, listed apps notify normally.

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

Install the privileged nftables wrapper once (or again after an update, when the shipped file differs). This asks for sudo in the terminal, copies the wrapper to `/usr/local/libexec/omarchy-distraction-space/distractions-nft` (`install -D -m 0755`), renders the sudoers line into `/etc/sudoers.d/omarchy-distraction-space` (`install -m 0440` after `visudo -cf`), and refuses when any ancestor of either destination is writable by the invoking user. The last step is `omarchy-shell shell rescanPlugins`. A rescan that is missing from PATH or exits non-zero leaves the installed files in place, prints the failure, and exits 1.

```bash
~/.config/omarchy/plugins/distraction-space/distractions setup
```

A missing wrapper skips only the site block. Window placement still runs. `site_block` in `status --json` becomes `unavailable`.

To reverse the grant:

```bash
~/.config/omarchy/plugins/distraction-space/distractions setup --remove
```

That flushes table `inet omarchy_ds`, removes both files, and rescans the same way. fn-10 will insert its notification-service clone step before that rescan.

## Keys

| Action | Keys |
|---|---|
| Open or leave the distraction space | Super+Ctrl+Shift+D (`distractions toggle`) |
| Move the focused window there | Super+Alt+D |
| Lock or unlock | Super+Ctrl+Shift+F (unlock when locked, otherwise lock) |
| Next occupied workspace (skips the space) | Super+Tab |
| Previous occupied workspace (skips the space) | Super+Shift+Tab |

The workspace rule is `hl.workspace_rule({ workspace = "name:distraction", persistent = true })`. Super+1–0 and the bar never land here.

Bar widget (eye glyph, urgent color while locked, tooltip with deadline and purpose; watches `state.json`, never polls):

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

`hold_notifications` is one of `off-space`, `locked`, `never`. `summary.command` is `auto`, `off`, or an argv array. Both are validated here and consumed in fn-10. `mute_sounds` is the same: stored now, used in fn-10.

`hooks.*` are argv arrays run detached with env `DS_EVENT`, `DS_PURPOSE`, `DS_MINUTES`, `DS_REASON`, `DS_HELD` (JSON object of app to count; `"{}"` until fn-10 fills it). stdout and stderr go to `log`. Failures are ignored.

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

Native (class plus the `pwa` host; messaging apps ship `hosts: []` so they are never blocked; `senders` and `audio` are carried through for fn-10):

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
| `status [--json]` | Human summary, or the `state.json` shape computed live (lock, `on_space`, `site_block` from the last listener write, `listener_pid` null when absent or dead). Works without a listener. Missing hyprctl sets `on_space` null. |
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
| `setup [--remove]` | Install or remove the wrapper and sudoers, then rescan, as above. |

## State files

Under `~/.local/state/omarchy/distraction-space/` (`$XDG_STATE_HOME` honored):

| File | Writer | Shape |
|---|---|---|
| `lock.json` | `lock` / `unlock` only | `{"locked": true, "since": "<iso>", "until": "<iso>\|null", "purpose": "<text>"}` |
| `state.json` | Listener only, on every change; the bar watches this | `{"locked": false, "until": null, "purpose": "", "on_space": false, "site_block": "on", "listener_pid": 1234, "updated": "<iso>"}`. `site_block` is `on`, `off` (on the space or empty list), or `unavailable`. Without a listener the file goes stale; `status --json` still works from `lock.json` and hyprctl. fn-10 appends its own keys. |
| `expansion.json` | Listener after every successful config load or reload | Last validated expansion (the full `{name, classes, hosts, senders, audio}` list plus `keep_reachable` and `nudges`). Invalid-config fallback: enforce from this cache; with no cache, enforce nothing and report `site_block: off`. |
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

Hook ownership: `lock` / `unlock` commands run those hooks because they write `lock.json`. The listener runs `unlock` for a lazy expiry it observes, and `enter` / `leave` on every observed workspace transition onto or off the space. `enter`, `leave`, and `toggle` never run hooks themselves. Without a listener, `enter`/`leave` hooks and the expiry `unlock` hook do not fire.

## Listener

Hyprland autostart starts one listener per session with the shipped line in `hypr/autostart.lua`. Production connects to `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock`. Tests may set `DS_SOCKET2` to a Unix socket.

On start, on every workspace change off the space, on reload, and every 30 s while off the space, the listener resolves listed hosts (`getent ahosts`, 2 s per host, 10 s batch deadline), subtracts `keep_reachable` addresses, and pipes one address per line to `sudo -n /usr/local/libexec/omarchy-distraction-space/distractions-nft replace ds` (the installed path the sudoers grant names). Entering the space sends `flush ds`. The wrapper's filter output chain `reject`s set members (TCP reset for TCP, ICMP unreachable otherwise) and a nat output chain redirects TCP 80 to 28080 and TCP 443 to 28443 on set members.

When `nudges.block_page` is true, loopback HTTP on 28080 serves a block page naming the Host header with the Super+Ctrl+Shift+D line (and a lock note when locked). Port 28443 reads the ClientHello (SNI) and closes; one banner per host per 30 s. Nothing is served on 28443 beyond that read.

Window rules: one named rule per class in every expanded entry (`windowrule[omarchy-ds-<slug>-<n>]`), recorded in `rules.json`. socket2 `openwindow` / `movewindow` silently moves a listed client found off the space. When `nudges.app_banner` is on and the person is off the space, one banner per app per 30 s: title "`<Name>` lives in the distraction space", body "Super+Ctrl+Shift+D opens it.", click action `distractions enter`.

Config mutations already call reload after a successful write.

## What fn-10 adds later

This schema already validates and round-trips three keys whose behavior is not implemented here:

- **Notification hold** (`hold_notifications`: `off-space`, `locked`, or `never`). Listed apps stay quiet while hold is effective. The listener will push sender keys into Omarchy's notification service (a cloned patched service until that lands upstream). Held pings go to `held.jsonl`.
- **Sound mute** (`mute_sounds`). Streams of listed apps are muted while hold is on and unmuted when it ends.
- **Summary** (`summary.command` `auto` / `off` / argv, `summary.timeout_seconds`). When a lock ends or the space is entered, one notification titled "While you were away" shows the agent's one-liner, or a grouped per-app count. `DS_HELD` on the `unlock` and `enter` hooks will carry those counts.

fn-10 also adds `hold`, `held`, and `notification_hold` to `state.json`, files `held.jsonl` / `muted.json` / `clone.json`, a `distractions senders` command, and a clone step inside `setup` before the plugin rescan. Until that merge, listed apps notify and play sound as usual.

## License

MIT
