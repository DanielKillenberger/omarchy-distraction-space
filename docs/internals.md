# Internals

The [README](../README.md) covers installing and operating the plugin. This page is for reading or changing the code: the listener loop, the state file shapes, how the static network table is kept, what the URL handler and the launcher entries write, and the lifecycle of the patched notification-service clone.

## Layout

`distractions` is the entry point and dispatches to the `ds` package. `ds/cgroup.py` answers whether a process is in `app-distraction.slice`, `ds/launch.py` owns `open` (target resolution, the browser profile, the transient scope, forwarding), `ds/hypr.py` owns window containment, `ds/net.py` and `distractions-nft` own the site block, `ds/feedback.py` owns the routers and the two banners, `ds/hold.py` owns notification capture and sound mute, `ds/summary.py` owns the "While you were away" notice, `ds/setup.py` owns the privileged install, the slice unit, the launcher entries, the URL handler, and the clone, and `ds/listener.py` runs the loop that drives them. The menu UI in `ds/ui.py` calls only `omarchy-menu-select` and `omarchy-menu-input`.

## The slice

The space is two things: the Hyprland workspace `name:distraction` and the systemd slice `app-distraction.slice` under the person's user manager. `systemd-run --user --scope --slice=app-distraction.slice` places a child at `/user.slice/user-<uid>.slice/user@<uid>.service/app.slice/app-distraction.slice/run-<n>.scope`, so `cgroup.in_slice(pid)` reads `/proc/<pid>/cgroup` and tests whether the fifth path component is the slice, the same test the wrapper's `socket cgroupv2 level 5` rule makes. `ancestor_in_slice(pid, hops=8)` walks `/proc/<pid>/stat` parents. An unreadable cgroup file reads as outside. `DS_PROC_ROOT` points the reads at a fake `/proc` in tests.

The slice is a unit file, `install/app-distraction.slice`, not a transient one, because nftables resolves the cgroup path to a kernel id when the rule loads; a slice that systemd garbage-collected while empty would leave the rule pointing at a dead id. `setup` copies the unit to `~/.config/systemd/user/`, runs `daemon-reload`, and starts it; the listener runs `systemctl --user start app-distraction.slice` before every `replace`; `setup --remove` stops it, deletes the file, and reloads. No step here touches root.

## Browser profile

`launch.pick_browser` takes config `browser` when it is an argv array. Otherwise it asks `xdg-settings get default-web-browser` and uses that desktop entry when its id starts with `google-chrome`, `brave`, `microsoft-edge`, `opera`, `vivaldi`, or `helium`, the case list `omarchy-launch-webapp` uses, else `chromium.desktop`. The first token of the entry's `Exec` line is the binary. A web launch is that binary plus `--user-data-dir=$XDG_DATA_HOME/omarchy/distraction-space/browser --profile-directory=Distraction --app=<url>`, and the resulting window class is `<browser>-<host>__-Distraction`. The whole argv runs behind `systemd-run --user --scope --quiet --collect --slice=app-distraction.slice --`, detached in a new session with its standard streams closed, because `systemd-run --scope` blocks until its child exits.

Before launching, `open` looks for a window of that class for the same host in `hyprctl -j clients`. One found off the space is moved there silently; one found while the person is on the space is focused. Either way nothing is launched twice. Chromium's single-instance handoff means a second launch of the profile for another host becomes a new window in the running process, which is already in the slice.

`open` resolves its argument in a fixed order. An argument with a scheme is a URL and only `http` and `https` are accepted; a host that is listed, or a subdomain of a listed host (a port ignored), opens in the profile and any other URL is forwarded. Otherwise the argument is a list entry name, then a catalog name, which launches but is logged as not network-restricted. A native entry with a catalog `desktop` id runs that desktop entry's `Exec` line, read the way `omarchy-launch-webapp` reads a desktop file (key-file escapes, quoting, field codes), skipping the plugin's own launcher entry that setup puts in front of it. Exit 0 after a launch, focus, or forward, 1 when the browser or the forwarder cannot be started, 2 on usage or a malformed URL.

`distractions profile import` (`ds/profile.py`) copies a Chromium profile into `Distraction` once. The source is `Default` under the config directory of the browser `open` would pick (the recorded previous handler when the plugin is the default, the binary name when config `browser` is an argv), or the `--from` directory; it must hold a `Preferences` file and must neither be nor contain the destination. Before a byte moves, `/proc` (`DS_PROC_ROOT` in tests) is scanned for a process of this user carrying `--user-data-dir=` of the source directory or of the distraction directory, or the source browser's binary running without one, and the source's `SingletonLock` counts when it names a live pid on this host. The copy is `shutil.copytree` with symlinks preserved, skipping `Cache`, `Code Cache`, `GPUCache`, the Dawn and shader caches, `Service Worker/CacheStorage` and `ScriptCache`, and the singleton files, into a sibling `Distraction.import-<pid>` that is renamed into place only when it completed; a leftover sibling from an interrupted run is moved to `.stale`, and with `--replace` an existing destination is renamed to `Distraction.bak-<YYYYMMDD-HHMMSS>` (a counter on collision) first and never deleted. A failed copy leaves the sibling and the backup in place and names both. Nothing is written to `state.json`.

## URL handler

`setup` writes `~/.local/share/applications/io.github.danielkillenberger.distraction-space.desktop` with `MimeType=x-scheme-handler/http;x-scheme-handler/https` and `Exec=<plugin>/distractions open %u`, records what `xdg-settings get default-web-browser` printed as `previous_handler` in `entries.json`, and runs `xdg-settings set default-web-browser` on its own id. `open_links_in_space: false` hands the default back before the handler file goes, and keeps the file with `links: displaced` when that cannot be shown to have happened.

While the plugin is the default browser, Omarchy's own launchers resolve to it: `omarchy-launch-browser` runs the default's `Exec` first token bare, or with `--incognito` (`--private-window`, `--inprivate`) for the private keybind, and `omarchy-launch-webapp` matches the id against its Chromium-family case list, misses, and falls back to Chromium. So `open` forwards whatever it does not own (`launch.forward`). `split_args` reads the argv after `open` without argparse: `--app` anywhere is the flag, the target is the first token with a URL scheme, else the first that does not start with `-`, and every other token is a browser flag kept in order and never interpreted (a flag with a value wants `--flag=value`). No target, or only flags, runs the previous handler's `Exec` with the URL field code removed and the flags appended; an unlisted URL runs it with the URL substituted for the field code, or with `--app=<url>` appended when `--app` was given, the way `omarchy-launch-webapp` runs it; a listed target opens in the space as always, where `--app` changes nothing and the flags are logged as not applied. The forward is detached and never inside the slice. When no previous handler is recorded, the record names the plugin itself, or its `Exec` does not parse, the forward goes to `omarchy-launch-browser` with `BROWSER` dropped from the environment; when that script would only resolve the default browser back to the plugin, nothing is launched and `open` exits 1 with one notice. `distractions` with no subcommand, or with a leading `-` token, is `open`, which is how the keybind's bare `Exec` reaches it.

Chrome shows its "make Chrome your default browser?" prompt per profile, governed by `browser.check_default_browser` in the profile's `Preferences`, and rewrites that file on exit. `launch.ensure_profile` therefore creates the `Distraction` profile directory with a `Preferences` holding the key at `false` before the first launch, building it as a sibling and renaming it into place so a racing launch sees no profile or a complete one; an existing directory is never touched. `profile import` sets the same key in the copied `Preferences` after the copy. The main profile is never modified.

Setup makes the default-browser change a choice (`setup.ask_links`), asked before anything asks for a password. When the config file has no explicit `open_links_in_space`, setup prints the explanation naming the previous browser by its desktop entry's `Name` (the id `xdg-settings` reports, unless that is the plugin's handler, then the recorded previous handler; the id without its suffix when the entry has no `Name`; "your previous browser" when none is known) and, on a terminal without `--yes`, asks `Route links through the distraction space? [Y/n]`; an empty line or end of input is yes, an unclear answer is asked again. `--yes`, or a stdin that is not a terminal, prints the explanation as a notice and takes the config value, true by default. Either way the answer is written to the config file, so setup never asks twice; a rerun prints `links: on|off -- change it with: distractions config set open_links_in_space <value>`. No leaves the handler unregistered and `links: off` while the entries, the rewritten web apps included, are still written. An answer that cannot be recorded (config busy, unwritable file) stops setup with exit 1 before anything is installed, so the question returns next time. `--yes` suppresses every prompt: the root transaction then runs `sudo -n`, and a first install that needs a password fails with one line naming that instead of asking.

The listener's `check_links` runs on start, on reload, and every 60 seconds. It answers `off` when the switch is off or the manifest names no handler, so `xdg-settings` is never asked on a machine where setup never registered one; otherwise `on` while the reported default is the plugin's id and `displaced` when it is another id or the query went unanswered. The displaced notice fires once per listener lifetime.

## Launcher entries and `entries.json`

Omarchy's own launcher runs the browser directly rather than through the URL handler, so app-menu clicks are routed by desktop entries, not by the handler. For every list entry `setup` writes one file under `~/.local/share/applications/` with `Exec=<plugin>/distractions open <name>`: `<desktop-id>.desktop` for a native product with a catalog `desktop` id, which shadows the system entry under `/usr/share/applications` through ordinary XDG precedence, and `<Name>.desktop` for a web product, the name Omarchy gives its own web-app entry in that same directory. A file already at that path that the manifest does not own is moved whole into `entries-backup/` under the state directory and recorded beside the entry; nothing the plugin did not write is ever edited or deleted.

Every other `.desktop` file in that directory whose main-group `Exec` starts with `omarchy-launch-webapp` is an Omarchy web app that is not a listed product, and `_forward_entry` rewrites it: the original is backed up under `entries-backup/` and recorded in `entries.json` exactly like a shadowed same-name file, and the written entry keeps every byte of the original except the `Exec` value, which becomes `<plugin>/distractions open --app <url> [extra args]` with the URL and any extra arguments carried over through the desktop-entry grammar both ways. An unlisted web app therefore opens in the previous browser as an app window, a listed one in the space, and Omarchy's menus see no difference. An entry whose `Exec` cannot be parsed is named once per process on stderr and left alone, and one the plugin already owns that Omarchy regenerated with a malformed `Exec` is kept as recorded rather than restored from its stale backup. A file at a planned path that is not this plugin's launcher is Omarchy's and becomes the backup, replacing an older one, so a reinstalled web app's new file survives; an owned launcher that is gone was removed by the person or Omarchy's remover, and its backup goes with the record instead of resurrecting the web app. A listed product dropped from the list keeps a forwarder at its Omarchy file rather than handing the file back.

The file half of the sync, `_sync_files`, is a no-op when nothing changed. `setup.refresh_entries` re-runs it from the listener on `refresh` and once a period, only once setup has written the manifest, so an entry Omarchy regenerates (a web app installed or reinstalled) is rewritten within a minute; the listener never touches the default browser (the handler file stays as recorded, the recorded previous handler stands, `xdg-settings` is not asked). Setup, remove, and the listener's sync take one flock on `$XDG_RUNTIME_DIR/distraction-space.entries.lock`: setup and remove wait up to 90 seconds and report busy past it, the listener gives way at once and tries again next period, and whether a manifest still exists is decided under that lock so a remove that finished first leaves nothing to recreate.

The manifest is `{"files": [{"path": ..., "backup": ... | null}], "previous_handler": "<id>.desktop" | null}`, written after every file it names, and refused whole when a path is not a direct child of the applications directory or a backup is not its twin under the backup directory. A write failure rolls the run back from a journal, including the exact bytes of owned files it was replacing. `remove_entries` restores the previous default while the plugin still holds it, deletes exactly the manifest's paths, moves each backup home, drops the manifest, and prints the kept profile path; an unanswered `xdg-settings` query or a failed restore keeps everything for a retry. `update-desktop-database` runs afterwards when present, best effort.

## Window containment

`hyprctl keyword` refuses on Omarchy 4's Lua config parser, exiting 0 with the refusal on stdout, so rules go through `hyprctl eval` with `hl.window_rule`. One named rule, `omarchy_ds_profile`, matches every window of the distraction profile, class `^[a-z-]+-.+__-Distraction$`. Each native class of an expanded entry gets one rule, `omarchy-ds-<slug>-<digest>-<n>`, where `<digest>` is the first 8 hex characters of the SHA-1 of the entry name; a listed product's version 2 web-app pattern `^chrome-<host>__.*$` is left out of the rules on purpose, because a web-app window of the distraction profile is the profile rule's and one from any other profile is adoption's. The names go into `rules.json` and the name-to-class pairs into `rule-specs.json`. The eval snippet keeps the rule handles in a Lua global table, so a later disable or re-apply can reach the exact handle. It disables the old handle under a name before creating the new one, because whether Hyprland replaces or duplicates a rule by name is unverified. Hyprland drops every eval-created rule on a config reload; the listener watches socket2 for `configreloaded` and re-applies the whole set.

`hypr.classify(klass, pid)` is the one decision, three layers, first match wins. `class`: the profile pattern or a native class. `slice`: the window's pid, or an ancestor within eight hops, is in the slice, which covers popups and helper windows with a plain browser class. `adopt`: the class is a listed product's web app in a browser profile other than `Distraction`, so the window belongs to a browser outside the slice and can never reach its host. `hypr.contain(client)` runs it on every socket2 `openwindow`, `movewindow`, and `movewindowv2` event and once per client on the boot scan. A move goes through `hl.dsp.window.move` with `follow = false`, so focus stays where the person put it. Adoption remembers the window address first, runs `distractions open <name>` synchronously with a 30 second cap, closes the window only on exit 0, and on a failed `open` moves the window by class with one `adopt:` log line. A close Hyprland refused is retried on the window's next event without launching again. The handled set is capped at 256 addresses and pruned on `closewindow`.

Two things sit in front of the layers. The released set `{address: until}` in `hypr._released` is checked before `classify`, so a released window is skipped by every layer; `release <address> <until>` on the listener socket adds one, `closewindow` forgets it, and each tick `expire_released` drops past deadlines and, with `containment.snap_back` on, contains each expired window once. `hypr.snap_back`, set by the listener from the config on every enforce, makes `_handle_event` return early for move events when it is `false`, so only a fresh `openwindow` is placed.

The workspace itself is declared with `hl.workspace_rule({ workspace = "name:distraction", persistent = true })` in `hypr/windows.lua`. Super+1 through Super+0 and the bar's workspace list never reach a named workspace, which is what keeps the space out of ordinary navigation.

## Listener loop

Hyprland autostart starts one listener per session from the line in `hypr/autostart.lua`. A second `distractions listen` takes a non-blocking flock on `$XDG_RUNTIME_DIR/distraction-space.lock`, finds it held, and exits 0 with no output. There is no forking. Production connects to `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock`; tests point `DS_SOCKET2` at their own Unix socket.

The loop ticks once a second and reacts to socket2 events. It notices a lazy lock expiry, rewrites `state.json`, notifies "Lock ended", and runs the `unlock` hook; it expires released windows; and every 60 seconds it re-checks the URL handler, re-runs the launcher entry sync, and, with the block enabled, requests a resolution. A workspace change runs the `enter` and `leave` hooks and re-syncs the hold, nothing else. `$XDG_RUNTIME_DIR/distraction-space.sock` accepts three verbs, `reload`, `refresh`, and `release <address> <until-iso>`, and answers `ok` or `error`. `reload` re-reads the config; an invalid one answers `error` and leaves the window rules and the site block as they were. `refresh` re-resolves without re-reading the config, re-runs the entry sync, and with the block disabled retries a refused flush. `release` refuses a past or unreadable deadline and a window `hyprctl clients` no longer lists. SIGTERM calls `net.shutdown()` so an in-flight `getent` cannot hold exit past about 3 seconds.

## Network

The wrapper renders one static table. Its first rule in both chains accepts traffic whose socket is in the slice's cgroup, `socket cgroupv2 level 5 "user.slice/user-<uid>.slice/user@<uid>.service/app.slice/app-distraction.slice" accept`, with the path derived from `SUDO_UID` alone; a missing or non-numeric value is refused with exit 2, and a slice whose cgroup directory is missing under `/sys/fs/cgroup` is refused with exit 1 and `refused: slice cgroup missing`, which the listener reports as `site_block: unavailable`. After it, in order: the splice source-port range 61000 to 61999 is accepted, set members are rejected (TCP reset for TCP, ICMP unreachable otherwise), and TCP 80 and 443 to set members are redirected to 28080 and 28443. The wrapper owns table `inet omarchy_ds` with sets `omarchy_ds_v4` and `omarchy_ds_v6`, takes `replace ds` with one address per line on stdin or `flush ds` with none, and its argv and stdin grammar, byte and address caps, and table confinement are unchanged from version 2, so the sudoers grant is too. `flush` destroys the table outright and renders nothing in its place, so it needs neither the slice nor a kernel that accepts the cgroup matcher: switching the block off, and `setup --remove`, work even where `replace` reports `unavailable`.

The listener resolves listed hosts on start, on `reload`, on `refresh`, and every 60 seconds, regardless of workspace. `resolve_batch` in `ds/net.py` takes a monotonically increasing generation number and a reason string, calls `getent ahosts` with a 2 second budget per host and a 10 second deadline for the whole batch, subtracts every address that also serves a `keep_reachable` host, and writes the result to `addrs.json` as the last good resolution per host. The batch is logged as `net gen=<n> reason=<why>`. A stale generation is dropped, a failed batch keeps the last good set with one notice, and a refused wrapper call answers `error` to whoever asked for that generation. The addresses go to `sudo -n /usr/local/libexec/omarchy-distraction-space/distractions-nft replace ds`, the one path the grant names, after `systemctl --user start app-distraction.slice`. Entering or leaving the space sends nothing. `site_block.enabled: false` flushes once on start and reload, never resolves, and reports `site_block: off`.

Port 28080 serves the block page, naming the site from the Host header and adding the lock note while a lock is active. Port 28443 reads the ClientHello, takes the SNI, and closes without writing anything.

## Banners

Two kinds, one path. `feedback.opened(entry_name)` is called by `hypr.contain` after a confirmed landing on the space and by the boot scan; the title is `<Product> opened in the distraction space`, the body names the key that enters, or reads `Locked until HH:MM.` while a lock is active, and the action is `distractions enter`. `feedback.blocked(host)` is called by the 28443 router for a listed SNI; the title is `Blocked here`, the body names the product and the key, and the action is `distractions open https://<host>/`, the site root since the SNI never carries a path. The block page is its own feedback on 80, so only the 28443 path raises a banner. An unlisted SNI raises nothing.

Both go through `_fire`: one debounce table keyed by list entry name, 60 seconds per entry shared by the two kinds, and a `hypr.on_space()` check that skips on the space and skips with a log line when Hyprland cannot answer. Every decision writes `banner: host=<h> entry=<name> decision=shown|debounced` to the log synchronously, and `distractions banners` prints any `banner:` line, version 2 ones included. `nudges.app_banner` gates Opened, `nudges.block_page` gates Blocked and the page. There is no attribution: a blocked connection is from outside the slice by construction.

## Notification-service clone lifecycle

Omarchy's notification service silences globally through do not disturb and has no per-sender list. `shell/notifications-silenced-senders.patch` adds one. While the first-party service under `/usr/share/omarchy/shell/plugins/notifications` lacks the method, `distractions setup` runs `omarchy-plugin-clone omarchy.notifications`, applies the patch inside the clone after a dry run, and records the SHA-256 of every first-party file plus the patch in `clone.json`. Nothing under `/usr/share` is written.

A later `setup` run takes one of five branches:

| Observed state | What setup does |
|---|---|
| Fingerprint unchanged | Nothing |
| First-party files changed (an Omarchy update) | Re-clone and re-apply the patch |
| Patch no longer applies | Remove the clone, report the hold unavailable, exit 1 |
| Built-in now carries the method | Remove the clone |
| A `<user>.notifications` clone with no matching `clone.json` | Report it, leave it alone, hold stays unavailable |

Removing a clone first disables it with `omarchy-shell shell setPluginEnabled <id> false` and refuses to delete the directory when that call fails, so a shell that is down is never left with no notification server at all. After any create, refresh, or removal, setup runs `omarchy-shell shell rescanPlugins` and then probes the running shell, calling `omarchy restart shell` when the notification service did not swap. On Omarchy 4 the rescan reloads the files while the running service keeps the old code, which is why the probe exists.

## Notification capture and sound mute

The listener keeps `busctl --user monitor` on the session bus for its whole life, restarting it with 1, 4, and 16 second backoff if it exits. While the hold is in effect it appends every Notify from a listed sender to `held.jsonl` under the list entry's name. A sender key is the notification's `app_name` or, for a Chromium-derived sender, the site host Chromium prepends to the body. Matching is case-insensitive and ignores a leading `www.`. A Notify it cannot attribute is left alone, and a missing `busctl` turns capture off with one log line while holding and muting continue.

Keys the listener pushed are recorded in `silenced-owned.json` and only those are removed when the hold ends or the listener exits cleanly, so a key you silenced by hand in the shell survives in both directions. The shell persists its own list, so a hold survives a shell restart.

Sound mute reads `pactl -f json list sink-inputs` and a `pactl subscribe` feed. A sink input whose `application.process.id` is in the slice is a member first, whatever its window class, so an unlisted page open in a distraction-profile window is muted with everything else; an unreadable or missing cgroup file falls through. Outside the slice it matches the catalog's `audio.name` and `audio.binary` against `application.name` and `application.process.binary`, and for a Chromium web app it also looks for `--app=<url>` or `--app-id=<host>` in the command line of the stream's process or up to eight ancestors; a bare browser stream outside the slice is never treated as a listed app. `muted.json` maps sink-input index to `pid:starttime`, and only a recorded index whose identity still matches is unmuted, so a reused index is left alone. A stream that could not be unmuted is retried every 16 seconds until it is.

## Summary

When a lock ends or the space is entered, the records in `held.jsonl` are claimed by renaming the file away and then reading it. The per-app counts go to the `unlock` or `enter` hook as `DS_HELD`, and one notification titled "While you were away" shows. Zero records show nothing. Whoever marks the boundary does this work: `distractions unlock` for a manual unlock, and the listener for a lock expiry or for entering the space. Because the claim is atomic, the hook's counts and the notice come from the same records, a second boundary during a slow agent call has nothing to repeat, and pings held meanwhile wait for the next summary.

The body comes from `summary.command`. `auto` runs `claude -p --output-format text` when `claude` is on PATH, else `grok -p`, else the grouped count. An argv array runs as given. `off` always uses the grouped count. The command reads the prompt on stdin (a request for one or two plain sentences in the second person, followed by the records as JSON lines) and answers on stdout. At most 64 KiB of stdout and 4 KiB of stderr are read, and the reply is collapsed to one line and clipped to 800 bytes. A non-zero exit, a timeout at `summary.timeout_seconds`, or an empty reply falls back to the grouped count, `Telegram 3 · Discord 1`, most held first. The command runs on your machine as you, with no sandbox beyond the timeout and the clip.

## State files

Under `~/.local/state/omarchy/distraction-space/`, honoring `$XDG_STATE_HOME`:

| File | Writer | Shape |
|---|---|---|
| `lock.json` | `lock` and `unlock` only | `{"locked": true, "since": "<iso>", "until": "<iso>\|null", "purpose": "<text>"}` |
| `state.json` | Listener, on every change; the bar watches this | `{"locked": false, "until": null, "purpose": "", "on_space": false, "site_block": "on", "listener_pid": 1234, "hold": true, "held": {"Telegram": 3}, "notification_hold": "on", "pass_through": "on", "links": "on", "browser": null, "released": {"0x55d1c0a2b3c0": "<iso>"}, "updated": "<iso>"}` |
| `expansion.json` | Listener after every successful config load or reload | The last validated expansion (`name`, `classes`, `hosts`, `senders`, `audio`, `desktop` per entry, plus `keep_reachable`, `nudges`, and `site_block.enabled`); a version 2 file reads with `desktop: null` and the block enabled |
| `entries.json` | `setup` | `{"files": [{"path": "<applications-dir>/<file>.desktop", "backup": "<state-dir>/entries-backup/<file>.desktop\|null"}], "previous_handler": "<id>.desktop\|null"}` |
| `entries-backup/` | `setup` | The files that were at a launcher entry's path before setup wrote there, moved whole |
| `held.jsonl` | Listener while the hold is in effect | One line per held notification: `{"at": "<iso>", "app": "Telegram", "title": "<summary>", "body": "<body>"}`, fields clipped at 4096 bytes, newest kept under 64 KiB |
| `muted.json` | Listener while the hold is in effect | Sink-input index to `pid:starttime` for every stream this plugin muted |
| `silenced-owned.json` | Listener | The sender keys this plugin pushed into the shell's silenced list |
| `clone.json` | `setup` | Plugin id, paths, and SHA-256 of each first-party file and of the patch; its presence marks the clone as this plugin's |
| `addrs.json` | Network resolver | Last good resolution per host |
| `rules.json` | Window containment | JSON array of the Hyprland rule names this plugin set |
| `rule-specs.json` | Window containment | Rule name to class pattern, so a rollback can restore the previous set |
| `log` | Lock reasons, hook output, network batches, banner decisions | Text, path overridable with config `log` |

`state.json.site_block` is `on`, `off` (`site_block.enabled: false`, or an empty address set), or `unavailable` (no privileged wrapper, `sudo -n` refused, `nft` rejected the table, or the slice cgroup was missing). `links` is `on`, `off` (the switch is off or no handler is registered), or `displaced` (another default browser, or `xdg-settings` did not answer). `browser` is the distraction browser's basename, read at start and reload the way `open` picks it (the config `browser` argv, else the default browser's desktop entry), or `null` when no Chromium-family browser resolves. `released` maps each exempt window address to its deadline. `notification_hold` is `on`, `off`, or `unavailable` (the shell has no silenced list). Without a listener running, `state.json` goes stale and `distractions status --json` still answers from `lock.json` and hyprctl.

Runtime files live in `$XDG_RUNTIME_DIR`: `distraction-space.lock` (single listener), `distraction-space.config.lock` (config mutation flock), `distraction-space.entries.lock` (one launcher-entry transaction at a time across setup, remove, and the listener), and `distraction-space.sock` (reload, refresh, release). The browser profile lives under data, not state: `~/.local/share/omarchy/distraction-space/browser`, honoring `$XDG_DATA_HOME`, and `setup --remove` leaves it in place.

Lock expiry is lazy. `is_locked()` treats an `until` in the past as unlocked, and the listener's one-second tick is what turns that into a `state.json` write, a notice, and the `unlock` hook. `lock` leaves the space first when the person is on it, through the same cycle `leave` uses, and stays put when no other workspace is occupied.

## Hooks

`hooks.lock`, `hooks.unlock`, `hooks.enter`, and `hooks.leave` are argv arrays, run detached with `DS_EVENT`, `DS_PURPOSE`, `DS_MINUTES`, `DS_REASON`, and `DS_HELD` in the environment. `DS_HELD` is a JSON object of app name to held count on `unlock` and `enter`, the same counts the summary is about to show, and `"{}"` on `lock` and `leave`. stdout and stderr go to the configured `log`, and failures are ignored.

The `lock` and `unlock` commands run their own hooks because they write `lock.json`. The listener runs `unlock` for an expiry it observes, and `enter` and `leave` on every workspace transition onto or off the space. The `enter`, `leave`, and `toggle` commands never run hooks themselves. With no listener running, the `enter` and `leave` hooks, the expiry `unlock` hook, and the summary for those two boundaries do not fire, while a manual `distractions unlock` still summarizes.

## Catalog shapes

`catalog.json` maps a product name to its identity in one of three shapes. Expansion produces `classes`: the native `class` when present, plus, for every host-bearing entry, the web-app class `^chrome-<host>__.*$` built from its first host (the `pwa` host when given). Containment does not set a rule for that web-app class any more, but `hold.py`, `launch.py`, and the adoption layer still read the host out of it. A native product may carry `desktop`, the id of its system desktop entry without the suffix; `open` runs that entry and `setup` shadows it.

Native, with the `pwa` host, empty `hosts` so a messaging app is never blocked, `senders` for the hold, `audio` for the mute, and `desktop` for the launch:

```json
"Telegram": {
  "class": "org.telegram.desktop",
  "desktop": "org.telegram.desktop",
  "pwa": "web.telegram.org",
  "hosts": [],
  "senders": ["Telegram Desktop", "org.telegram.desktop"],
  "audio": {"name": ["Telegram Desktop"], "binary": ["telegram-desktop", "Telegram"]}
}
```

Web app only, moved and never blocked:

```json
"Discord": {"pwa": "discord.com", "hosts": []}
```

Hosts only, moved as a web app of the distraction profile and blocked outside it:

```json
"YouTube": {"hosts": ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"]}
```

Telegram therefore expands to `classes: ["org.telegram.desktop", "^chrome-web\\.telegram\\.org__.*$"]` and `desktop: "org.telegram.desktop"`; Discord and YouTube expand with `desktop: null`. A `class=<regex>` list entry expands to one class and no hosts.

## Config writes and migration

Every write takes a blocking flock on `$XDG_RUNTIME_DIR/distraction-space.config.lock` with a 5 second timeout. On timeout the command exits 1 with "config busy" and leaves the file unchanged. `config set`, `list add`, `list remove`, and every menu save go through it; reads take no lock. A successful mutation asks the running listener to reload. `config set` validates before the write: `site_block.enabled`, `open_links_in_space`, and `containment.snap_back` must be booleans, `browser` must be `"auto"` or a non-empty argv of non-empty strings, and `containment.release_minutes` an integer from 1 to 10080.

`open_links_in_space` is the one default that stays out of the file until something sets it. In memory every load carries it at its default, but `update` hands the mutation the file's own keys, treats an assignment of the key, whatever the value, as the answer, and writes the file without it otherwise; `config.links_answered()` reports whether the file states it and `config.set_links(value)` answers. That is how `setup` knows whether it has asked, across every `list add` and menu save made in between.

On the first load with no `distraction-space.json`, `list` is seeded from the union of the names in `~/.config/omarchy/app-list.json` and the `destinations` in `~/.config/omarchy/focus.json`, falling back to the fifteen defaults. `log` is taken from the old `focus.json` when it is present. The old files stay untouched, old state files under `~/.local/state/omarchy/` are ignored, and unreadable old files fall back to the defaults. A version 2 config file loads with every version 3 key at its default.

## Tests

```bash
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
```

384 tests as of this commit, all offline. `tests/harness.py` builds a temporary XDG root per test, and the socket2 feed, `hyprctl`, `getent`, `busctl`, `pactl`, `systemctl`, `systemd-run`, `xdg-settings`, `update-desktop-database`, the nft wrapper, and the `/proc` cgroup and cmdline reads (`DS_PROC_ROOT`) are all replaced with fakes, so nothing in the suite touches your real session, your user manager, your real config, or the firewall.
