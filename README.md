# Omarchy distraction space

A named Hyprland workspace for chat and social apps, plus a **focus mode** that keeps it locked until you write a reason to leave.

Focus mode is on by default. Super+1–0, Super+Tab, and the workspace bar never land on the distraction space. Super+D is the only way in, and only after you turn focus mode off.

While focus mode is on, the plugin also blocks the active distraction list at the network level: it sinkholes those hostnames in `/etc/hosts` and drops their resolved addresses with an `nftables` table named `omarchy_focus`. Turning focus off removes that table and the marked hosts block. Apply or lift failures are reported and leave the previous network state in place.

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
```

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

Turning focus **on** is instant. Turning it **off** opens a zenity field; the reason must be at least 50 characters. Reasons append to the log path in `~/.config/omarchy/focus.json` (default `~/.local/state/omarchy/focus-disable.log`).

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
```

## License

MIT
