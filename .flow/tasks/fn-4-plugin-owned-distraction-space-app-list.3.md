---
satisfies: [R4, R9]
---
# fn-4-plugin-owned-distraction-space-app-list.3 List editor UI and install docs

## Description
Give the user a plugin UI to add, remove, and change list entries, and update install docs so membership is no longer edited as copied Hypr rules.

**Size:** M
**Files:** BarWidget.qml, distractions, README.md, manifest.json
**Touches:** [BarWidget.qml, README.md, manifest.json, distractions]

### Approach
- Add a helper command that opens a zenity editor (same missing-zenity abort as `prompt_reason` at `distractions:200-221`). Persist via the list file from task 1. Rejected rows stay out. Custom rows must include at least one of class or hosts.
- Launch that command from `BarWidget.qml` without replacing left-click focus toggle (`BarWidget.qml:26-31`). Reuse `Process` + `helperPath` (`BarWidget.qml:12-31`).
- After a successful save, write a reload request to the listener socket from task 2. Do not apply rules or nftables in the editor process. If the listener is dead or the reply is failure, notify and leave enforcement unchanged.
- README Install: drop “edit the o.window lines”. Say the plugin UI owns membership. Keep bindings + autostart copy, chmod, focus.json, reload, listen. Add a migrate line: delete leftover membership `o.window` lines from user hyprland.lua. Document install of `/usr/local/libexec/omarchy-distraction-space/distractions-nft` plus `/etc/sudoers.d/omarchy-distraction-space` (installing uid `NOPASSWD` on that path only), uninstall (remove wrapper, sudoers file, `flush ds`), and that a missing wrapper skips only the site block.
- README Use: shipped general list, exclusive windows, always-on off-space site block, conscious-choice intercept banner, focus mode still locks the space, how to open the editor, Super+Alt+D stays.
- manifest `description` and `barWidget.description` mention the owned list, the always-on off-space site block, and the intercept banner.
- Do not add a new Omarchy `kinds` entry. Do not add notification history or per-app mute toggles.

### Investigation targets
**Required** (read before coding):
- `BarWidget.qml:7-80` — bar process/IPC pattern
- `distractions:200-221` — zenity reason prompt
- `README.md:7-66` — install, use, commands
- `manifest.json:1-23` — kinds and copy

**Optional:**
- `.flow/memory/declined/notification-extra-ui.md` — do not re-open mute extra UI
## Acceptance
- [ ] User can add, remove, and change entries from the plugin UI without rebuild (R4, R9)
- [ ] Rejected edit is omitted; other entries remain
- [ ] Missing zenity aborts, notifies, and leaves the list unchanged
- [ ] Successful save writes a reload request to the listener; the editor does not install rules or call nftables
- [ ] README no longer tells users to edit `o.window` membership lines
- [ ] README includes the leftover-rule migrate line and the `distractions-nft` path, sudoers install/uninstall
- [ ] README states the off-space site block is always on, the intercept banner copy, and that focus mode still locks the space
- [ ] manifest descriptions mention the list, the always-on off-space site block, and the intercept banner
## Done summary
The plugin now edits the distraction list from a zenity helper launched by right-click on the bar (or `edit-list`). Accepted rows persist to the user list file; rejected or colliding rows stay out; a successful save only asks the listener to reload. README and manifest describe the owned list, leftover-rule migrate, nft wrapper/sudoers install and uninstall, the always-on off-space site block, and the intercept banner.

baseline: green
stage: impl-review - skipped(policy: host-deferred - conductor owns the gate)

stage: impl-review - SHIP (host, gpt-5.6-sol-medium)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 578d1b2b5e7e067f09251891f0ce951ceaf56cfc
- Tests: python3 -m py_compile distractions, python3 -c "import ast; ast.parse(open('distractions').read())", python3 -m unittest tests.test_edit_list
- PRs: