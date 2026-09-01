# Plugin-owned distraction-space app list

> HTML render lens: [.flow/artifacts/fn-4-plugin-owned-distraction-space-app-list/spec.html](../artifacts/fn-4-plugin-owned-distraction-space-app-list/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "how did you make it that apps go into distraction plane automatically?"
> user (turn 2): "ok that should be a native configuration list in the plugin should we spec that?"
> user (turn 3): "can we make sure that in any other workspace they don't open at all (even the website versions)"
> user (turn 4): "should that be in this spec or separate?"
> user (turn 5): "i think we can just block corresponding sites on the network level as we are on any other workspace than distraction space?"
> user (turn 6): "i wouldn't decline extra ui by default"
> user (turn 7): "fold it in"
> user (turn 8): "why just chat names? should be distractions generally"
> user (turn 9): "every distraction that's in the list should only open in distraction space and be blocked everywhere else (during focus mode)"
> user (turn 10): "well no" / "it should be blocked everywhere else" / "always"
> user (turn 11): "and distraction space should be locked during focus mode"
> user (turn 12): "if we're in a normal workspace trying to open one of those things it'd be cool to have some sort of message that shows \"Consciously choose to view this in your distraction space\""

## Overview

The plugin owns one distraction list. Shipped defaults are Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, and Netflix. The user edits that list through a plugin UI. A listed app window with a class matcher lands only on the named distraction workspace. While the active workspace is not that space, the plugin always blocks the listed sites at the network. An intercept of a listed window from a normal workspace shows the helper banner "Consciously choose to view this in your distraction space". Focus mode does not gate the site block. Focus mode still locks the space. A shared-browser tab stays where it is. The site does not load.

## Goal & Context
<!-- scope: business -->

The person using this plugin already has a named distraction workspace and a focus-mode lock. Winning is one plugin-owned list of distractions. Every listed name is exclusive to that space (window, if it has a class) and blocked on every other workspace at all times. Opening a listed app from a normal workspace leaves the user where they are and tells them to choose the space on purpose. Focus mode keeps the space locked, as it does today. The user maintains the list through a plugin UI.

## Architecture & Data Models
<!-- scope: technical -->

One plugin-owned list of product-name entries. Each entry has a required name. Class matcher and hostname set are independently optional. Placement uses entries that have a class (from the expand map or the entry). Network apply uses entries that have hosts. A custom name the expand map does not know must supply at least one of class or hosts. Hosts-only entries get no window assignment. Class-only entries get no site block. The six names that already have `o.window` lines expand to class plus hosts. The other shipped names are hosts-only. fn-2 mute later reads product names plus expanded class matchers (hosts-only rows are not window membership). This spec does not implement mute.

First run copies the shipped defaults into a user file beside the existing focus log config whenever that user file is absent. A later delete of the file is the same recovery: copy shipped defaults again. A present but unreadable or invalid file is not overwritten: notify and keep the last successfully applied expanded list. Print-expand may show empty. Do not clear already-applied rules or nftables members. If there is no last-good list yet, apply nothing. A present valid empty list is a user empty list: that becomes the new last-good and clears this spec's rules and `ds` sets. Later plugin updates do not overwrite a present user file.

Window rules are helper-owned Hyprland named window rules from expanded class matchers. Anonymous `windowrulev2` lines cannot be updated at runtime. Each class entry gets a deterministic name `omarchy-ds-<sanitized-product>`. Two accepted names that sanitize to the same identifier are a rejected collision (R4). For every desired name, always issue match:class, the silent workspace effect for `name:distraction`, and `windowrule[<name>]:enable true` (including a name that was previously disabled and is re-added). Disable a removed entry with `windowrule[<name>]:enable false`. Replace order: create or update and enable every desired name first, then disable names that are no longer desired. If any create/update/enable fails, roll back this batch: disable names this batch created that were not in last-good, restore last-good match, workspace effect, and enabled state on names this batch already updated, then stop without disabling removed names. Notify. If a later disable fails, notify and retry disable of the leftovers; do not undo successful creates. R1 and R6 apply-failure rollback covers create/update/enable only. A disable failure leaves desired names applied and leftover removed names enabled until a later disable succeeds. Requires Hyprland named window rules (0.53+; current Omarchy). `dispatch()` at `distractions:33-34` only moves already-open clients (`movetoworkspacesilent`). It does not install rules. Hyprland 0.53 has no `hyprctl` listing of named window rules. The persisted registry under `STATE_DIR` at `distractions:18` is authoritative. Write the intended `omarchy-ds-*` name set to a pending file (atomic replace) before mutation. After a fully successful create/update/enable plus disable pass, replace last-good with that intended set and clear pending. On helper start, disable-removed is (last-good ∪ pending) minus desired. Do not enumerate live Hyprland rule names. Then scan `hyprctl clients -j` via `hyprctl_json` at `distractions:29-30` and silently move matching clients that are not on `name:distraction`. From `listen()` at `distractions:237-260`, treat socket2 `openwindow` and `movewindow` the same way. Super+Alt+D at `hypr/bindings.lua:17` stays for unlisted windows. The named-workspace rule stays a one-time Hypr snippet. The six copied `o.window` membership lines go away.

Live intercept banner (R10). Named rules place new listed windows on `name:distraction` before `openwindow` is seen, so the banner is not gated on performing a move. On socket2 `openwindow`, if the active workspace is not `name:distraction` and the client matches a listed class, `listen()` calls `notify()` at `distractions:37-44` with title `Consciously choose to view this in your distraction space` and the product name as the body when known, even when that window is already on the space. On `movewindow`, if the client matches and is not on the space, silent-move it, then notify the same way. The banner does not call `show()` or `enter()`. The user stays on the current workspace. Focus mode still locks Super+D / `enter()` through existing `is_focus` / `hide` / `blocked_message` at `distractions:140-154`. Debounce is one banner per product name per 30 seconds. The helper-start client scan moves without a banner (a restart is not a user attempt). A listed window that opens while the user is already on `name:distraction` does not notify. Harden `notify()` at `distractions:37-44` so FileNotFoundError and nonzero exits from both `omarchy-notification-send` and `notify-send` are absorbed. A notify failure never leaves `listen()`. This banner is helper-owned (`omarchy-notification-send` / `notify-send`), not a notification from the listed app. fn-2 mute of distraction-space apps must not hide it. Hosts-only site attempts have no window event and no SNI. This spec does not claim a per-navigation banner for a YouTube tab in Chrome. The page fail is the site enforcement.

Live reload is listener-owned. The editor process writes a reload request to a socket beside `LISTEN_LOCK` at `distractions:21`. It does not apply rules or nftables itself. The `listen()` process re-reads the list file, applies placement and the `ds` block, updates last-good expand/rules/addresses, then replies success or failure. Later `openwindow` / `movewindow` and periodic DNS refresh use that new last-good. If the listener is dead, the editor notifies and leaves enforcement unchanged.

Site block is not a hostname match in nftables. nftables cannot store IPv4 and IPv6 in one set. This spec owns table `inet omarchy_ds` with sets `omarchy_ds_v4` (`ipv4_addr`) and `omarchy_ds_v6` (`ipv6_addr`), and an `output` hook at filter priority that drops `ip daddr @omarchy_ds_v4` and `ip6 daddr @omarchy_ds_v6`. The wrapper create-if-missing that table, those sets, and those drop rules on first `replace ds`. It never installs input, forward, or any other table. The unprivileged helper resolves each listed hostname to A and AAAA. It never invokes `nft`. Auth is constrained sudoers, not polkit: helper always runs

`sudo -n /usr/local/libexec/omarchy-distraction-space/distractions-nft replace ds`

with one IP per stdin line, or `flush ds` to empty both `ds` sets (drop rules stay; empty sets match nothing). Install writes `/etc/sudoers.d/omarchy-distraction-space` (0644) granting only the installing uid `NOPASSWD` on that exact wrapper path. Uninstall removes wrapper and sudoers file and `flush ds`. If wrapper or `sudo -n` fails closed, notify and skip network apply and lift; window placement still runs. The wrapper splits lines into v4/v6, validates they are addresses (reject hostnames and paths), and commits both `ds` sets in one nft transaction. It refuses any other table and any other target than `ds`. Apply whenever `on_distractions()` is false. Lift only this spec's `ds` sets when it is true. Focus mode does not gate apply or lift. Focus mode continues to lock the space through existing `is_focus` / `hide` / `enter` at `distractions:124-160`. This spec does not re-implement that lock. The helper snapshots the last successfully submitted per-host address lists in userspace and persists that map under `STATE_DIR` (atomic replace after a successful `replace ds`). On helper start it loads the map. It does not read kernel sets. On wrapper failure it keeps that last-good map and assumes the kernel did not change. If DNS fails for a host with no persisted last-good, omit only that never-submitted host from this replace. Never drop a persisted host. Refresh resolutions on apply, on list save while blocked, and on a short interval while blocked. Resolve A/AAAA off the listen path with a 2-second timeout per hostname. A stalled or slow lookup keeps that host's last-good addresses and does not block socket2, reload replies, placement, or the focus lock. Network mutations (`replace ds` / `flush ds`) are serialized on one worker. At most one resolve/replace job is in flight. A periodic tick while a job is in flight is skipped. Each job captures a generation incremented on workspace apply/lift and on list reload. Before submit, discard a stale generation and re-check current workspace and list. A job started while blocked must not `replace` after the user has entered the space. If a hostname's DNS fails, keep that host's last-good addresses and still replace with the merged map (successes updated, failures retained). Never call `replace` with a set that drops a previously blocked host because DNS failed. Shared CDN addresses are accepted collateral. Already-open TCP survives; only new connects fail.

## Approach

- Extend the existing helper config loader. Keep the focus log key. Add a sibling user file for the app list so a bad list cannot swallow the log path.
- Ship a fixed expand map. Class plus hosts for the six current `o.window` names (`hypr/windows.lua:4-9`): Telegram `web.telegram.org`; Discord `discord.com` and `www.discord.com`; WhatsApp `web.whatsapp.com`; X `x.com`, `www.x.com`, `twitter.com`, and `www.twitter.com`; Signal `signal.org` and `www.signal.org`; Google Messages `messages.google.com`. Hosts-only for Facebook `facebook.com` and `www.facebook.com`; Instagram `instagram.com` and `www.instagram.com`; Threads `threads.net` and `www.threads.net`; Reddit `reddit.com` and `www.reddit.com`; TikTok `tiktok.com` and `www.tiktok.com`; Snapchat `snapchat.com` and `www.snapchat.com`; YouTube `youtube.com`, `www.youtube.com`, `youtu.be`, and `m.youtube.com`; Twitch `twitch.tv` and `www.twitch.tv`; Netflix `netflix.com` and `www.netflix.com`. Every shipped apex also includes its `www.` name. YouTube also includes `youtu.be` and `m.youtube.com`. Do not add CDN or media hosts.
- Custom entries: at least one of class or hosts. Editor rejects a nameless, duplicate, empty-of-both-fields, or colliding-sanitized-name row.
- Apply placement through named Hyprland window rules (`windowrule[<name>]`) plus `dispatch` moves of existing clients. Do not ask the user to paste membership rules. Do not move a shared browser for hosts-only rows.
- On a live `openwindow` while the user is off the space, `notify()` the conscious-choice banner even when the named rule already placed the window on `name:distraction`. On `movewindow` of a listed window that is not on the space, silent-move then `notify()`. Debounce 30 seconds per product. Skip the banner on the helper-start client scan and when the user is already on the space. Do not follow the user onto the space.
- README tells existing users to delete leftover membership `o.window` lines from their Hypr config so the plugin list is the only assigner. README states the off-space site block is always on, that an intercept from a normal workspace shows the conscious-choice banner, and that focus mode still locks the space.
- Reuse `notify` for apply failures and for R10. Harden it so both senders' missing-binary and nonzero exits are absorbed. Keep last-good expanded list, last-good named-rule properties, and last-good submitted addresses in userspace, and persist a crash-safe named-rule registry (pending before mutate, last-good after full success) under `STATE_DIR` so a restart after a dead-listener edit can still disable removed `omarchy-ds-*` names. Do not enumerate live Hyprland rule names. A failed named-rule batch rolls back to last-good. Wrapper failure leaves `ds` sets as the wrapper last committed them.
- List UI is a helper command plus a bar launch into the existing zenity pattern. Do not add an Omarchy settings kind.
- Live reload is listener-owned IPC. The editor only requests reload. The listener applies and updates last-good. It does not restart the listener process.
- Leave `is_focus` / `hide` / `enter` as they are. Do not add a second lock.

## Quick commands

```bash
python3 -m py_compile distractions
python3 -c "import ast; ast.parse(open('distractions').read())"
```

There is no test suite today. Task work adds a Hyprland-free expand/print check that asserts the shipped hostname sets above, plus injected-command tests: fake `hyprctl` and fake `distractions-nft` plus recorded socket2 lines covering rule replace, existing-client move, workspace apply/lift, resolve-then-`replace`/`flush`, rollback, missing-wrapper skip, UI-save signaling, `openwindow` banner while off-space with the client already on `name:distraction`, `movewindow` banner after a silent move, debounce, start-scan silence, restart after a remove while the listener was dead, and restart after a valid empty list. A separate wrapper test drives `distractions-nft` with a fake `nft` and asserts address validation, command/target rejection, table confinement, and one transaction for both `ds` sets. Injected tests also cover notify absorb (both senders missing or nonzero), stalled DNS that does not block socket2, a stale DNS generation discarded after flush or reload, and an overlapping periodic tick skipped while a resolve is in flight, and restart from pending-plus-last-good without live rule enumeration. The unprivileged helper must not invoke `nft`. Documented manual checks (real Hyprland session, wrapper install present and missing, focus lock still blocks enter, intercept banner copy) stay out of CI.

## Boundaries
<!-- scope: business -->

- Focus-mode lock of the distraction space stays the existing helper behavior. This spec does not re-implement it.
- fn-1 no longer owns a sibling extras destination list. Those names ship here. fn-1 must be replanned against this list before any fn-1 work.
- Notification mute stays fn-2. fn-2 reads this list. This spec does not mute. fn-2 must not hide this spec's helper-owned intercept banner.
- fn-2 extra notification UI (history, per-app toggles) stays declined in `.flow/memory/declined/notification-extra-ui.md`.
- Notification allow-list and urgent bypass stay declined in `.flow/memory/declined/notification-exceptions.md`.
- The existing manual send-to-workspace action stays.
- A file-only maintenance path with no plugin UI is out of scope.
- Native-app protocol traffic beyond the listed websites is out of scope for the network block.
- SNI or HTTP Host inspection is out of scope.
- A per-navigation banner for a hosts-only site in a shared browser is out of scope.
- Killing already-open TCP flows is out of scope.
- Moving Chrome to follow a YouTube or similar tab is out of scope.
- Auto-switching the user onto the distraction space from the intercept banner is out of scope.
- A live Hyprland or root-net CI harness is out of scope.

## Decision Context
<!-- scope: both -->

The list is distractions generally, not chat-only. The six `o.window` names were the first members because they already auto-placed. The user asked to ship the general set.

Every listed distraction opens only on the distraction space when it has a window class. Listed sites are blocked on every other workspace at all times. Focus mode does not turn that block on or off. "During focus mode" in the user's correction means the space stays locked, which `enter` and `hide` already do.

Website versions are enforced by R8 (always-on off-space network block). R7 means the same membership set, not moving a shared browser window onto the distraction space. Shipped host sets include each product's apex `www.` name. YouTube also ships `youtu.be` and `m.youtube.com`. CDN and media hosts stay out (shared-CDN collateral remains accepted).

A listed app opened from a normal workspace lands on the space via the named rule, so `openwindow` sees it already there. Gating the banner on a helper move would miss the primary launch path. The banner fires from the user's active workspace, not from the window's assigned workspace. The user asked for the helper banner "Consciously choose to view this in your distraction space" on that attempt. The banner is a desktop notification from `notify()`. It does not switch workspaces. A zenity modal would steal the current workspace. `notify()` at `distractions:37-44` matches `blocked_message()` at `distractions:140-144`. Debounce is 30 seconds per product so a reconnect storm does not stack banners. The helper-start scan is silent. A hosts-only YouTube tab has no class event and no SNI, so this spec does not invent a per-navigation banner for it.

The user declined a file-only default. A plugin UI is required. A file backs that UI. A missing user file always copies shipped defaults. Later plugin updates do not overwrite a present user file. A corrupt present file is an error, not a recopy, and it does not clear last-good enforcement. Only a valid empty list clears.

Window apply is helper-owned named Hyprland rules with create/update-first then disable-removed. The last-applied `omarchy-ds-*` set is persisted so a restart can disable names removed while the listener was dead. Network apply resolves hosts to addresses, then `sudo -n /usr/local/libexec/omarchy-distraction-space/distractions-nft replace|flush ds` against table `inet omarchy_ds`. Auth is sudoers.d for the installing uid only. One-time privileged install is required. Missing install skips only the network half.

This list is fn-2 window membership. fn-1 and fn-2 wait on this spec. fn-1's capture of a separate extras list is stale. Implementers must not follow fn-1's current R3/R5/R7 as written.

Rejected as overkill: a second Omarchy plugin kind, a 3800-hostname dump, overlay-merge of defaults on every upgrade, gating the off-space block on focus mode, moving Chrome to follow a discord.com or youtube.com tab, SNI inspection, conntrack kill, a choice dialog or auto-switch from the intercept banner.

R5 (unlisted apps stay off this list's assigner) is a scout-confirmed complement of R1 and Super+Alt+D. It is a normal criterion.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** Apps on the plugin configuration list that have a class matcher open on the distraction workspace automatically. Hosts-only rows do not assign windows. Errors: if create/update/enable of desired names fails, the plugin tells the user and rolls back that batch to last-good placement. A later disable of a removed name is not this failure. Desired names stay. Leftovers stay enabled until a later disable succeeds.
- **R2:** The list is native plugin configuration. Maintaining it does not require the user to copy window rules into the window manager. Errors: a present but unreadable or invalid list tells the user and keeps the last successfully applied list. A missing user file copies shipped defaults and is not this error. A valid empty list clears this spec's placement and `ds` block.
- **R3:** Shipped defaults are Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, and Netflix. Errors: a missing defaults set tells the user and starts with an empty list.
- **R4:** The user can add, remove, and change list entries without rebuilding or reinstalling the plugin. Errors: a rejected entry does not join the active list; other entries still apply. Two names that sanitize to the same `omarchy-ds-*` identifier are rejected.
- **R5:** An app that is not on the list does not open on the distraction workspace because of this list. Errors: no error surface beyond R1.
- **R6:** A listed app with a class matcher does not open on any workspace other than the distraction workspace. Errors: if create/update/enable of desired names fails, the plugin tells the user and rolls back that batch to last-good placement. A later disable of a removed name is not this failure.
- **R7:** Website versions of listed apps are in the same set as the apps. Errors: no error surface beyond R1, R6, and R8.
- **R8:** While the active workspace is not the distraction workspace, the plugin always blocks network access to the listed sites. Focus mode does not gate this block. Switching onto the distraction workspace lifts this spec's block. Errors: if apply or lift fails, the plugin tells the user and leaves the previous network state unchanged. If the privileged nftables install is missing, the plugin tells the user and skips network apply and lift. If DNS for a listed host fails, that host keeps its last-good addresses.
- **R9:** The user can add, remove, and change list entries through a plugin UI. Errors: a rejected edit does not join the active list; other entries still apply. Missing zenity aborts the edit, tells the user, and leaves the list unchanged.
- **R10:** While the active workspace is not the distraction workspace, a live `openwindow` of a listed app window shows the helper notification titled `Consciously choose to view this in your distraction space`, even when the named rule already placed that window on the space. A live `movewindow` of a listed window that is not on the space shows the same banner after the silent move. The banner does not switch the user onto the space. Errors: if notify fails, placement and the site block still apply, and `listen()` stays up. A helper-start client scan does not show this banner. A listed window opened while the user is already on the space does not show this banner. A hosts-only site in a shared browser has no banner in this spec.

## Early proof point

Task fn-4-plugin-owned-distraction-space-app-list.1 validates that the helper can load a user list, ship the R3 names, expand the six current windowed names to class plus hosts, and expand the rest to hosts only, without Hyprland. If expand or first-run copy fails, fix the schema before applying rules or nftables.

## Open Questions

None. Already-open TCP stays up (new connects only). Privileged nftables install is required; missing install skips the network half. Focus lock stays the existing helper. Hosts-only site attempts have no intercept banner.

## Requirement coverage

| Req | Description | Task(s) | Gap justification |
|-----|-------------|---------|-------------------|
| R1 | Listed classed apps auto-open on the distraction workspace | fn-4-plugin-owned-distraction-space-app-list.2 | — |
| R2 | Native plugin list, no copied membership rules | fn-4-plugin-owned-distraction-space-app-list.1, fn-4-plugin-owned-distraction-space-app-list.2 | — |
| R3 | Shipped general distraction defaults | fn-4-plugin-owned-distraction-space-app-list.1 | — |
| R4 | Add/remove/change without rebuild | fn-4-plugin-owned-distraction-space-app-list.1, fn-4-plugin-owned-distraction-space-app-list.3 | — |
| R5 | Unlisted apps are not assigned by this list | fn-4-plugin-owned-distraction-space-app-list.2 | — |
| R6 | Listed classed apps do not open on other workspaces | fn-4-plugin-owned-distraction-space-app-list.2 | — |
| R7 | Website versions share membership | fn-4-plugin-owned-distraction-space-app-list.1, fn-4-plugin-owned-distraction-space-app-list.2 | — |
| R8 | Always-on off-space network block of listed sites | fn-4-plugin-owned-distraction-space-app-list.2 | — |
| R9 | Plugin UI edits the list | fn-4-plugin-owned-distraction-space-app-list.3 | — |
| R10 | Off-space launch or move of a listed window shows the conscious-choice banner | fn-4-plugin-owned-distraction-space-app-list.2 | — |
