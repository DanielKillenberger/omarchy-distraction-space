# Omarchy distraction space

A named Hyprland workspace for distractions, plus a **focus mode** that keeps it locked until you write a reason to leave.

The plugin owns one distraction list (Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, and Netflix). Listed apps with a window class open only on that space. While you are on any other workspace, listed sites are blocked at the network. Opening a listed app from a normal workspace shows the helper banner **Consciously choose to view this in your distraction space**. Focus mode does not gate the site block. Focus mode still locks the space.

Focus mode is on by default. Super+1–0, Super+Tab, and the workspace bar never land on the distraction space. Super+D is the only way in, and only after you turn focus mode off.

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

If you previously copied `o.window(...)` membership lines into `~/.config/hypr/hyprland.lua`, delete those leftover lines so the plugin list is the only assigner.

Then:

```bash
chmod +x ~/.config/omarchy/plugins/distraction-space/distractions
cp ~/.config/omarchy/plugins/distraction-space/focus.json ~/.config/omarchy/focus.json
hyprctl reload
```

Install the privileged site-block wrapper once (installing uid only, `NOPASSWD` on that path):

```bash
WRAPPER=/usr/local/libexec/omarchy-distraction-space/distractions-nft
sudo install -D -m 0755 ~/.config/omarchy/plugins/distraction-space/distractions-nft "$WRAPPER"
sudo sed "s/__INSTALL_USER__/${USER}/" \
  ~/.config/omarchy/plugins/distraction-space/install/sudoers.omarchy-distraction-space \
  | sudo tee /etc/sudoers.d/omarchy-distraction-space >/dev/null
sudo chmod 0644 /etc/sudoers.d/omarchy-distraction-space
```

A missing wrapper skips only the site block. Window placement still runs.

To uninstall the wrapper:

```bash
sudo /usr/local/libexec/omarchy-distraction-space/distractions-nft flush ds
sudo rm -f /usr/local/libexec/omarchy-distraction-space/distractions-nft \
  /etc/sudoers.d/omarchy-distraction-space
```

Start the listener once if you do not want to log out:

```bash
~/.config/omarchy/plugins/distraction-space/distractions listen &
```

Membership lives in the plugin list (`~/.config/omarchy/app-list.json`). Edit it from the bar widget or `edit-list`. Do not add window-rule membership lines to Hyprland.

## Use

| Action | Keys |
|---|---|
| Toggle focus mode | Super+Ctrl+Shift+F, or left-click the eye icon on the bar |
| Edit the distraction list | Right-click the eye icon, or `edit-list` |
| Open / leave the distraction space | Super+D (blocked while focus is on) |
| Send the focused window there | Super+Alt+D (stays for unlisted windows) |

The shipped list is exclusive: classed apps land only on the distraction space. Listed sites are blocked on every other workspace at all times. An intercept from a normal workspace shows **Consciously choose to view this in your distraction space**. Focus mode still locks the space.

Turning focus **on** is instant. Turning it **off** opens a zenity field; the reason must be at least 50 characters. Reasons append to the log path in `~/.config/omarchy/focus.json` (default `~/.local/state/omarchy/focus-disable.log`).

```json
{
  "log": "~/.local/state/omarchy/focus-disable.log"
}
```

## Commands

```bash
~/.config/omarchy/plugins/distraction-space/distractions toggle
~/.config/omarchy/plugins/distraction-space/distractions focus
~/.config/omarchy/plugins/distraction-space/distractions focus-status
~/.config/omarchy/plugins/distraction-space/distractions log-path
~/.config/omarchy/plugins/distraction-space/distractions edit-list
```

## License

MIT
