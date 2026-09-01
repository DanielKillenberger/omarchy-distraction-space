---
satisfies: [R1, R2, R5, R6, R7, R8, R10]
---
# fn-4-plugin-owned-distraction-space-app-list.2 Apply exclusive windows, always-on site block, and intercept banner

## Description
Enforce the loaded list. Matching windows land only on the named distraction workspace. Listed sites are blocked as resolved addresses in this spec's `omarchy_ds_v4` and `omarchy_ds_v6` nftables sets while the active workspace is not that space. Lift those `ds` sets when the user is on it. A live intercept from a normal workspace shows the conscious-choice helper banner.

**Size:** L
**Files:** distractions, hypr/windows.lua, distractions-nft, install/sudoers.omarchy-distraction-space
**Touches:** [distractions, hypr/windows.lua, distractions-nft, install/sudoers.omarchy-distraction-space]

### Approach
- Keep `hl.workspace_rule` for `name:distraction` in `hypr/windows.lua:3`. Remove the six `o.window` membership lines (`hypr/windows.lua:4-9`).
- Placement uses Hyprland named window rules. Deterministic name `omarchy-ds-<sanitized-product>`. For every desired name, always issue three keywords: match:class, silent workspace `name:distraction`, and `windowrule[<name>]:enable true`. A previously disabled name that is re-added must receive `enable true` again. Disable a removed entry with `windowrule[<name>]:enable false`. Order: create/update/enable every desired name first, then disable removed names. Create/update/enable failure: roll back this batch (disable names created that were not in last-good; restore last-good match, workspace effect, and enabled state on names already updated); stop without disabling removed names; notify. Disable failure: notify and retry leftovers; do not undo successful creates. R1/R6 rollback is create/update/enable only. Anonymous `windowrulev2` is not used. Requires Hyprland 0.53+ named rules. `dispatch()` at `distractions:33-34` is only for `movetoworkspacesilent` of already-open clients.
- Persist a crash-safe `omarchy-ds-*` registry under `STATE_DIR` at `distractions:18`. Hyprland 0.53 has no named-rule list API. Write intended names to pending before mutation. After a fully successful create/update/enable plus disable pass, replace last-good and clear pending. On helper start: disable-removed is (last-good ∪ pending) minus desired. Then scan `hyprctl clients -j` via `hyprctl_json` at `distractions:29-30` and silently move matching clients that are not on `name:distraction`. Do not follow the user onto the space. Do not show the R10 banner on this scan. A valid empty list disables last-good ∪ pending.
- From `listen()` at `distractions:237-260`, on socket2 `openwindow`, if the client matches a listed class and the active workspace is not `name:distraction`, call `notify()` at `distractions:37-44` with title `Consciously choose to view this in your distraction space` and the product name as the body when known (R10), even when the named rule already placed that window on the space. On `movewindow`, if the client matches and is not on the space, silent-move it, then notify the same way. Do not call `show()` or `enter()`. Debounce one banner per product name per 30 seconds. A listed window that opens while the user is already on the space does not notify. Super+Alt+D at `hypr/bindings.lua:17` stays for unlisted windows (R5).
- Harden `notify()` at `distractions:37-44` so FileNotFoundError and nonzero from both `omarchy-notification-send` and `notify-send` are absorbed. A failed `notify` does not leave `listen()`, roll back the move, or skip the `ds` block. The R10 banner is helper-owned. fn-2 mute of space apps must not hide it. Hosts-only site attempts have no banner.
- Create/update/enable failure: roll back this batch to last-good and notify. Disable failure: keep desired names, leave leftovers enabled, persist last-good still including leftovers, notify, retry. Corrupt list load: keep last-good expanded list; do not disable rules. Valid empty list: disable last-good ∪ pending.
- Network: resolve each listed hostname to A and AAAA. Never invoke `nft`. Call `sudo -n /usr/local/libexec/omarchy-distraction-space/distractions-nft replace ds` (stdin: one IP per line) when `on_distractions()` is false, and `… flush ds` when it is true. Focus mode does not gate apply or lift. Refresh resolutions on apply, on list save while blocked, and on a short interval while blocked. Resolve off the listen path with a 2-second timeout per hostname. Stalled or slow DNS keeps last-good for that host and does not block socket2, reload, placement, or the focus lock. Serialize `replace ds` / `flush ds` on one worker. At most one resolve/replace job is in flight. A periodic tick while a job is in flight is skipped. Each job captures a generation incremented on workspace apply/lift and on list reload. Before submit, discard a stale generation and re-check current workspace and list. DNS failure for a host keeps that host's last-good addresses; `replace` uses the merged map. Never omit a previously blocked host because DNS failed.
- Wrapper: target `ds` only. Owns table `inet omarchy_ds`, sets `omarchy_ds_v4`/`omarchy_ds_v6`, and output-hook filter drops for those sets. Create-if-missing on first `replace ds`. Validates addresses. Commits both sets in one nft transaction. Refuses other tables. Leave `is_focus` / `hide` / `enter` / `blocked_message` as they are.
- Install path `/usr/local/libexec/omarchy-distraction-space/distractions-nft` root:root 0755. Auth is `/etc/sudoers.d/omarchy-distraction-space` (0644) granting only the installing uid `NOPASSWD` on that exact path. No polkit. Uninstall removes wrapper and sudoers file and `flush ds`. Missing wrapper or `sudo -n`: `notify` and skip network half.
- Persist last successfully submitted per-host addresses under `STATE_DIR` after a successful `replace ds`. Load on helper start. No kernel read. Wrapper failure: keep last-good map; assume kernel unchanged. DNS failure for a never-submitted host omits only that host. A persisted host is never dropped because DNS failed.
- Own a listener-side reload socket beside `LISTEN_LOCK` at `distractions:21`. `listen()` handles the request: re-read the list, apply placement and `ds`, update last-good, reply. The editor process only writes the request. Periodic DNS and later socket2 events use the new last-good. Dead listener: notify, leave enforcement unchanged.
- Injected-command tests: fake `hyprctl` / fake wrapper / socket2 lines for named-rule update/enable/disable, remove-then-re-add, existing-client move, apply/lift, resolve-then-replace/flush, last-good on load failure, missing-wrapper skip, a reload that changes subsequent window and DNS handling, `openwindow` banner while off-space with the client already on `name:distraction`, `movewindow` banner after a silent move, 30-second debounce, start-scan silence, restart after a remove while the listener was dead, restart after a valid empty list, restart from a leftover pending file without live rule enumeration, notify absorb when both senders are missing or nonzero, stalled DNS that does not block a later socket2 event, a stale DNS generation discarded after flush or reload, and an overlapping periodic tick skipped while a resolve is in flight. Assert the helper never calls `nft`.
- Wrapper tests: run `distractions-nft` against a fake `nft`. Assert accepted IPv4/IPv6 replace, rejected hostnames/paths, rejected non-`ds` targets, table confinement to `inet omarchy_ds`, and one nft transaction for both sets. Manual Hyprland, install-present/missing, focus-lock, and banner-copy checks stay out of CI.

### Investigation targets
**Required** (read before coding):
- `distractions:25-34` — `hyprctl`, `hyprctl_json`, `dispatch`
- `distractions:37-44` — `notify`
- `distractions:64-78` — `current` / `is_distraction` / `on_distractions`
- `distractions:140-160` — `blocked_message` / `enter` (leave alone)
- `distractions:237-260` — listen loop and lock
- `hypr/windows.lua:3-9` — rule to keep vs rules to delete
- `hypr/bindings.lua:17` — manual move to leave alone

**Optional:**
- `hypr/autostart.lua:2` — listen start path
## Acceptance
- [ ] Listed app windows open on `name:distraction` without user-copied membership rules (R1, R2)
- [ ] A listed window does not remain on another workspace after open or move (R6)
- [ ] An unlisted window is not assigned by this list (R5)
- [ ] Named rules use `omarchy-ds-<product>`; desired names are enabled with `enable true`; removed entries are disabled with `enable false`; remove-then-re-add places again
- [ ] Off the space, the helper calls `sudo -n …/distractions-nft replace ds` with resolved IPv4 and IPv6 lines; on the space it calls `flush ds`; focus mode does not gate this (R8)
- [ ] A DNS job started before a flush or list reload is discarded and does not submit `replace ds` after that newer state
- [ ] A periodic tick while a resolve/replace is in flight is skipped so two jobs cannot submit out of order
- [ ] Wrapper create-if-missing owns table `inet omarchy_ds`, both sets, and output-hook drops
- [ ] Missing wrapper or sudoers notifies and skips only the network half
- [ ] Named-rule replace is create/update-first; a failed create/update rolls back this batch to last-good names and effects
- [ ] DNS failure keeps last-good addresses for that host, including after a helper restart from the persisted map; periodic refresh runs while blocked
- [ ] Create/update/enable failure rolls back this batch to last-good; disable failure keeps desired names and leftovers until retry
- [ ] Corrupt list load keeps last-good; a valid empty list clears this spec's rules and `ds` sets
- [ ] After a remove or empty-list write while the listener is dead, the next helper start disables orphaned `omarchy-ds-*` names from last-good ∪ pending with no live Hyprland rule enumeration
- [ ] Listener-owned reload applies the new list, updates last-good, and later window/DNS handling uses that state; the editor does not apply
- [ ] Live `openwindow` while the user is off the space calls `notify` with title `Consciously choose to view this in your distraction space` even when the client is already on `name:distraction`, and does not switch workspace (R10)
- [ ] Live `movewindow` of a listed window off the space silent-moves then notifies; a listed window opened while the user is on the space does not notify
- [ ] R10 debounce is one banner per product per 30 seconds; helper-start client scan moves without a banner
- [ ] `is_focus` / `hide` / `enter` / `blocked_message` stay the existing focus lock
- [ ] Injected-command tests cover the cases above including notify absorb and stalled DNS; helper never calls `nft`
- [ ] Wrapper tests with fake `nft` cover validation, target rejection, table confinement, and atomic dual-set replace
- [ ] `hypr/windows.lua` no longer contains the six membership `o.window` lines
- [ ] `python3 -m py_compile distractions` is green
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
