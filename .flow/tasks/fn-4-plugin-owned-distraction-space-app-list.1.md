---
satisfies: [R2, R3, R4, R7]
---
# fn-4-plugin-owned-distraction-space-app-list.1 App-list store, defaults, and expand map

## Description
Add the plugin-owned list file and the expand map for the shipped distraction names. The helper can load, reject bad entries, and print the expanded matchers and hosts without Hyprland.

**Size:** M
**Files:** distractions, app-list-defaults.json
**Touches:** [distractions, app-list-defaults.json]

### Approach
- Reuse `load_config()` at `distractions:47-54` for the log file. Add a second reader for the app list so a corrupt list cannot hide a good log path.
- A missing user list file always copies shipped defaults into place (first run and later delete are the same recovery). A present invalid file is not overwritten: `notify()` at `distractions:37-44` and keep the last successfully expanded list for apply. Print-expand of a corrupt file may be empty. A present empty list is valid last-good empty.
- Later plugin updates leave a present user file in place.
- Each entry is a product name. Class and hosts are independently optional. Class plus hosts for the six current `o.window` names (`hypr/windows.lua:4-9`): Telegram `web.telegram.org`; Discord `discord.com` and `www.discord.com`; WhatsApp `web.whatsapp.com`; X `x.com`, `www.x.com`, `twitter.com`, and `www.twitter.com`; Signal `signal.org` and `www.signal.org`; Google Messages `messages.google.com`. Hosts-only for Facebook `facebook.com` and `www.facebook.com`; Instagram `instagram.com` and `www.instagram.com`; Threads `threads.net` and `www.threads.net`; Reddit `reddit.com` and `www.reddit.com`; TikTok `tiktok.com` and `www.tiktok.com`; Snapchat `snapchat.com` and `www.snapchat.com`; YouTube `youtube.com`, `www.youtube.com`, `youtu.be`, and `m.youtube.com`; Twitch `twitch.tv` and `www.twitch.tv`; Netflix `netflix.com` and `www.netflix.com`.
- A name missing from the expand map is rejected unless the entry itself supplies at least one of class or hosts.
- Empty name, duplicate name, empty-of-both-fields custom row, colliding sanitized `omarchy-ds-*` names, and malformed JSON are rejected.
- Add a helper subcommand that prints the active expanded list (no hyprctl) so smoke can run in CI.
- Export a stable read shape fn-2 can consume later: product names plus expanded class matchers. Hosts-only rows are in the list and are not window membership. Do not implement mute.

### Investigation targets
**Required** (read before coding):
- `distractions:47-61` — current config load and log path
- `hypr/windows.lua:3-9` — today's six class matchers
- `focus.json:1-3` — existing user config copy

**Optional:**
- `README.md:21-41` — how focus.json is copied today
## Acceptance
- [ ] First run, and any later missing user file, produces a user list containing Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, and Netflix (R3)
- [ ] Expand of the six current windowed names yields a class matcher and exactly the hostname sets listed above
- [ ] Expand of YouTube includes `youtube.com`, `www.youtube.com`, `youtu.be`, and `m.youtube.com`; Netflix includes `netflix.com` and `www.netflix.com`
- [ ] Expand of the other shipped names is hosts-only (no class)
- [ ] A hosts-only custom entry expands hosts and has no class; a class-only custom entry expands class and has no hosts
- [ ] Present corrupt list tells the user, is not overwritten, and does not replace last-good expand (R2)
- [ ] Missing shipped defaults tells the user and starts empty (R3)
- [ ] Rejected entry stays out; other entries still expand (R4)
- [ ] Two names that sanitize to the same `omarchy-ds-*` identifier are rejected (punctuation-only pair)
- [ ] `python3 -m py_compile distractions` is green
- [ ] Helper print-expand runs without Hyprland
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
