# Omarchy distraction space

A named Hyprland workspace for chat and social apps, plus a **focus mode** that keeps it locked until you write a reason to leave.

Focus mode is on by default. Super+1–0, Super+Tab, and the workspace bar never land on the distraction space. Super+D is the only way in, and only after you turn focus mode off. While focus is on, apps in that space send no banner and no sound. Other apps keep notifying. When focus turns off, one grouped notice lists a count per app that pinged.

While focus mode is on, the plugin also blocks the active distraction list at the network level: it sinkholes those hostnames in `/etc/hosts` (IPv4 and IPv6), drops their resolved addresses with an `nftables` table named `omarchy_focus`, and makes suffix DNS (for example `*.googlevideo.com`) fail through the resolver that is actually answering queries. On systemd-resolved it writes a drop-in that routes those suffixes to a local sinkhole and reloads resolved; on dnsmasq it writes `address=/suffix/0.0.0.0` plus `::` and reloads dnsmasq; otherwise it points `/etc/resolv.conf` at the sinkhole and uses the nameservers captured before apply as upstream. Apply refuses an empty expansion instead of installing an empty block. Apply or lift failures are reported and leave the previous network state in place; a failed apply does not turn focus on. `nft` is required. Permanent destinations still expand if the shipped defaults file is missing.

## Install

Omarchy 4+, Hyprland, zenity.

```bash
omarchy plugin add https://github.com/DanielKillenberger/omarchy-distraction-space.git --enable
```

The bar widget appears in the center section. Move it if you want:

```bash
omarchy bar move distraction-space --section right
```

Copy the Hyprland snippets into your user config (plugin add does not edit Hyprland for you):

- `hypr/windows.lua` → `~/.config/hypr/hyprland.lua`
- `hypr/bindings.lua` → `~/.config/hypr/bindings.lua`
- `hypr/autostart.lua` → `~/.config/hypr/autostart.lua`

Then:

```bash
chmod +x ~/.config/omarchy/plugins/distraction-space/distractions
cp ~/.config/omarchy/plugins/distraction-space/focus.json ~/.config/omarchy/focus.json
hyprctl reload
~/.config/omarchy/plugins/distraction-space/distractions install
```

The plugin already appears in the bar layout, so Omarchy loads both the bar widget and the notification filter service from that one enablement. `install` is required once after add or update. It runs one `omarchy-shell shell rescanPlugins` and waits for the notification filter to ping ready. Do not run it while focus is already muting banners: rescan unloads live shell services.

Start the listener once if you do not want to log out:

```bash
~/.config/omarchy/plugins/distraction-space/distractions listen &
```

Edit the `o.window(...)` lines in the windows snippet if your chat apps use different classes.

## Use

| Action | Keys |
|---|---|
| Toggle focus mode | Super+Ctrl+Shift+F, or the eye icon on the bar |
| Open / leave the distraction space | Super+D (blocked while focus is on) |
| Send the focused window there | Super+Alt+D |

Turning focus **on** is instant and mutes banners and sounds from the distraction-space apps. Other apps still notify. If mute cannot apply, a toast says so and notifications stay as they were; focus still turns on.

Turning focus **off** opens a zenity field; the reason must be at least 50 characters. A successful lift restores those notifications, then one grouped notice lists a count per app that pinged (and may play one sound). Empty sessions skip that notice. The existing “Focus mode off” toast still appears. If restore fails, a toast says so and the mute may remain until a later successful lift; focus can still turn off. There is no mid-focus list of blocked pings.

Reasons append to the log path in `~/.config/omarchy/focus.json` (default `~/.local/state/omarchy/focus-disable.log`).

```json
{
  "log": "~/.local/state/omarchy/focus-disable.log"
}
```

Until you change it, the active network-block list is the shipped default: Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, and Netflix. Bluesky, Pinterest, and Tumblr are in the catalog but not defaults — add them yourself if you want them.

Edit the list without rebuilding the plugin. Product names from the catalog and extra hostnames are accepted; a rejected entry is ignored and the rest of the list still applies:

```bash
~/.config/omarchy/plugins/distraction-space/distractions destinations
~/.config/omarchy/plugins/distraction-space/distractions destinations-add Bluesky
~/.config/omarchy/plugins/distraction-space/distractions destinations-remove YouTube
```

`destinations-add` / `destinations-remove` write a `destinations` array into `~/.config/omarchy/focus.json`. Until that key exists, the plugin keeps using the shipped defaults.

## Commands

```bash
~/.config/omarchy/plugins/distraction-space/distractions toggle
~/.config/omarchy/plugins/distraction-space/distractions focus
~/.config/omarchy/plugins/distraction-space/distractions focus-status
~/.config/omarchy/plugins/distraction-space/distractions log-path
~/.config/omarchy/plugins/distraction-space/distractions destinations
~/.config/omarchy/plugins/distraction-space/distractions destinations-add <name-or-host>
~/.config/omarchy/plugins/distraction-space/distractions destinations-remove <name-or-host>
~/.config/omarchy/plugins/distraction-space/distractions install
```

## License

MIT
