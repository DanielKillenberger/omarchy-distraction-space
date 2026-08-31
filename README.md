# Omarchy distraction space

A named Hyprland workspace for chat and social apps, plus a **focus mode** that keeps it locked until you write a reason to leave.

Focus mode is on by default. Super+1–0, Super+Tab, and the workspace bar never land on the distraction space. Super+D is the only way in, and only after you turn focus mode off.

## Install

Omarchy 4+, Hyprland, zenity.

```bash
omarchy plugin add https://github.com/DanielKillenberger/omarchy-distraction-space.git --enable
```

The bar widget appears in the center section. Move it if you want:

```bash
omarchy bar move daniel.focus --section right
```

Copy the Hyprland snippets into your user config (plugin add does not edit Hyprland for you):

- `hypr/windows.lua` → `~/.config/hypr/hyprland.lua`
- `hypr/bindings.lua` → `~/.config/hypr/bindings.lua`
- `hypr/autostart.lua` → `~/.config/hypr/autostart.lua`

Then:

```bash
chmod +x ~/.config/omarchy/plugins/daniel.focus/distractions
cp ~/.config/omarchy/plugins/daniel.focus/focus.json ~/.config/omarchy/focus.json
hyprctl reload
```

Start the listener once if you do not want to log out:

```bash
~/.config/omarchy/plugins/daniel.focus/distractions listen &
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

## Commands

```bash
~/.config/omarchy/plugins/daniel.focus/distractions toggle
~/.config/omarchy/plugins/daniel.focus/distractions focus
~/.config/omarchy/plugins/daniel.focus/distractions focus-status
~/.config/omarchy/plugins/daniel.focus/distractions log-path
```

## License

MIT
