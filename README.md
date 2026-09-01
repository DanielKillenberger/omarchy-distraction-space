# Omarchy distraction space

A named Hyprland workspace for distractions, plus a **focus mode** that keeps it locked until you write a reason to leave.

The plugin owns one distraction list (Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, and Netflix). Listed apps with a window class open only on that space. While you are on any other workspace, listed sites are blocked at the network. Opening a listed app from a normal workspace shows the helper banner **Consciously choose to view this in your distraction space**. Focus mode does not gate the site block. Focus mode still locks the space.

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

If you previously copied `o.window(...)` membership lines into `~/.config/hypr/hyprland.lua`, delete those leftover lines so the plugin list is the only assigner.

Then:

```bash
chmod +x ~/.config/omarchy/plugins/distraction-space/distractions
cp ~/.config/omarchy/plugins/distraction-space/focus.json ~/.config/omarchy/focus.json
hyprctl reload
~/.config/omarchy/plugins/distraction-space/distractions install
```

The plugin already appears in the bar layout, so Omarchy loads both the bar widget and the notification filter service from that one enablement. `install` is required once after add or update. It runs one `omarchy-shell shell rescanPlugins` and waits for the notification filter to ping ready. Do not run it while focus is already muting banners: rescan unloads live shell services.

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

Turning focus **on** opens a start dialog for a required purpose and minutes until auto-off (the minutes field starts at 25). Confirm mutes banners and sounds from the distraction-space apps. Dismiss leaves focus off. Other apps still notify. If mute cannot apply, a toast says so and notifications stay as they were; focus still turns on. Set `session_start_ui` false for silent on with 25 minutes.

Turning focus **off** by hand opens a zenity field; the reason must be at least 50 characters. When the session minutes elapse, focus turns off without that reason. After focus is off, one closing window can show the purpose, the missed-summary, an optional self-eval, and helpful / not-helpful. A successful lift restores those notifications. When summaries are off, one grouped notice lists a count per app that pinged (and may play one sound). Empty sessions skip that notice. The existing “Focus mode off” toast still appears. If restore fails, a toast says so and the mute may remain until a later successful lift; the closing window can still show purpose and self-eval. There is no mid-focus list of blocked pings.

Reasons append to the log path in `~/.config/omarchy/focus.json` (default `~/.local/state/omarchy/focus-disable.log`).

```json
{
  "log": "~/.local/state/omarchy/focus-disable.log",
  "agent_summaries": false,
  "summary_agent": null,
  "session_start_ui": true,
  "session_start_purpose": true,
  "session_close_ui": true,
  "session_close_purpose": true,
  "session_close_eval": true
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

## Agent summaries

Agent summaries stay off until you enable them in the plugin. An Omarchy default agent is not consent.

Use `distractions agent-summaries` to turn the path on or off. Use `distractions summary-agent` to pick Claude, Grok, or Omarchy default. The picker offers only `claude` and `grok`.

While focus is on and summaries are enabled, a usable agent can parse blocked-ping text in the background. When focus turns off you see one summary of important things, not each original ping. The closing window hosts that summary as “Here's what you missed” or “You didn't miss anything”, with helpful / not-helpful on the same window. Set `session_close_ui` false to keep today's Focus-summary notification and follow-up helpful dialog. After a shown summary you can mark it helpful or not helpful and leave an optional note. That ledger is stored at `~/.local/state/omarchy/focus-summary-ledger.jsonl` and shapes later parses.

If summaries are off, no usable agent is resolved, ping-text is empty, or the parse or display fails, the mute grouped-count catch-up still runs. There is no history screen and no per-app notification toggle.

## Commands

```bash
~/.config/omarchy/plugins/distraction-space/distractions toggle
~/.config/omarchy/plugins/distraction-space/distractions focus
~/.config/omarchy/plugins/distraction-space/distractions focus-status
~/.config/omarchy/plugins/distraction-space/distractions agent-summaries
~/.config/omarchy/plugins/distraction-space/distractions summary-agent
~/.config/omarchy/plugins/distraction-space/distractions log-path
~/.config/omarchy/plugins/distraction-space/distractions destinations
~/.config/omarchy/plugins/distraction-space/distractions destinations-add <name-or-host>
~/.config/omarchy/plugins/distraction-space/distractions destinations-remove <name-or-host>
~/.config/omarchy/plugins/distraction-space/distractions install
~/.config/omarchy/plugins/distraction-space/distractions edit-list
```

## License

MIT
