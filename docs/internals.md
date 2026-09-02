# Internals

The [README](../README.md) covers installing and operating the plugin. This page is for reading or changing the code: the listener loop, the state file shapes, how the network generation counter works, and the lifecycle of the patched notification-service clone.

## Layout

`distractions` is the entry point and dispatches to the `ds` package. `ds/hypr.py` owns window containment, `ds/net.py` and `distractions-nft` own the site block, `ds/hold.py` owns notification capture and sound mute, `ds/summary.py` owns the "While you were away" notice, `ds/setup.py` owns the privileged install and the clone, and `ds/listener.py` runs the loop that drives them. The menu UI in `ds/ui.py` calls only `omarchy-menu-select` and `omarchy-menu-input`.

## Window containment

`hyprctl keyword` refuses on Omarchy 4's Lua config parser, exiting 0 with the refusal on stdout, so rules go through `hyprctl eval` with `hl.window_rule`. Each expanded class gets one named rule, `omarchy-ds-<slug>-<digest>-<n>`, where `<digest>` is the first 8 hex characters of the SHA-1 of the entry name, and the names go into `rules.json`. The eval snippet keeps the rule handles in a Lua global table, so a later disable or re-apply can reach the exact handle. It disables the old handle under a name before creating the new one, because whether Hyprland replaces or duplicates a rule by name is unverified.

Hyprland drops every eval-created rule on a config reload. The listener watches socket2 for `configreloaded` and re-applies the whole set from `rules.json` and the cached expansion. The socket2 `openwindow` and `movewindow` events are the safety net. A listed client found off the space is moved with `hl.dsp.window.move` and `follow = false`, so focus stays where you put it.

The workspace itself is declared with `hl.workspace_rule({ workspace = "name:distraction", persistent = true })` in `hypr/windows.lua`. Super+1 through Super+0 and the bar's workspace list never reach a named workspace, which is what keeps the space out of ordinary navigation.

## Listener loop

Hyprland autostart starts one listener per session from the line in `hypr/autostart.lua`. A second `distractions listen` takes a non-blocking flock on `$XDG_RUNTIME_DIR/distraction-space.lock`, finds it held, and exits 0 with no output. There is no forking. Production connects to `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock`; tests point `DS_SOCKET2` at their own Unix socket.

The loop ticks once a second and reacts to socket2 events. It notices a lazy lock expiry, rewrites `state.json`, notifies "Lock ended", and runs the `unlock` hook. `$XDG_RUNTIME_DIR/distraction-space.sock` accepts two verbs, `reload` and `refresh`, and answers `ok` or `error`. An invalid config on reload answers `error` and leaves both the window rules and the site block as they were. SIGTERM calls `net.shutdown()` so an in-flight `getent` cannot hold exit past about 3 seconds.

## Network generations

The listener re-resolves listed hosts on start, on every workspace change off the space, on reload, and every 30 seconds while off the space. `resolve_batch` in `ds/net.py` takes a monotonically increasing generation number and a reason string, calls `getent ahosts` with a 2 second budget per host and a 10 second deadline for the whole batch, subtracts every address that also serves a `keep_reachable` host, and writes the result to `addrs.json` as the last good resolution per host. The batch is logged as `net gen=<n> reason=<why>`, which is how you tell a scheduled refresh from one caused by a config reload when reading the log.

The addresses go to `sudo -n /usr/local/libexec/omarchy-distraction-space/distractions-nft replace ds`, one per line on stdin. That path is the one the sudoers grant names, so the wrapper is the only privileged surface. Entering the space sends `flush ds` instead. The wrapper owns table `inet omarchy_ds` with sets `omarchy_ds_v4` and `omarchy_ds_v6`, a filter output chain that rejects set members (TCP reset for TCP, ICMP unreachable otherwise), and a nat output chain that redirects TCP 80 to 28080 and TCP 443 to 28443.

Port 28080 serves the block page, naming the site from the Host header and adding the lock note while a lock is active. Port 28443 reads the ClientHello, takes the SNI, and closes without writing anything. Only the 28443 path raises the "Blocked on this workspace" banner, because the block page is its own feedback on 80. `_maybe_banner` in `ds/feedback.py` debounces it to once per catalog entry per 30 seconds and drops it when the fetching window is on the space, which it decides from the connection's peer port.

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

Sound mute reads `pactl -f json list sink-inputs` and a `pactl subscribe` feed, matching the catalog's `audio.name` and `audio.binary` against `application.name` and `application.process.binary`. For a Chromium web app it also looks for `--app=<url>` or `--app-id=<host>` in the command line of the stream's process or up to eight ancestors. A bare browser stream is never treated as a listed app. `muted.json` maps sink-input index to `pid:starttime`, and only a recorded index whose identity still matches is unmuted, so a reused index is left alone. A stream that could not be unmuted is retried every 16 seconds until it is.

## Summary

When a lock ends or the space is entered, the records in `held.jsonl` are claimed by renaming the file away and then reading it. The per-app counts go to the `unlock` or `enter` hook as `DS_HELD`, and one notification titled "While you were away" shows. Zero records show nothing. Whoever marks the boundary does this work: `distractions unlock` for a manual unlock, and the listener for a lock expiry or for entering the space. Because the claim is atomic, the hook's counts and the notice come from the same records, a second boundary during a slow agent call has nothing to repeat, and pings held meanwhile wait for the next summary.

The body comes from `summary.command`. `auto` runs `claude -p --output-format text` when `claude` is on PATH, else `grok -p`, else the grouped count. An argv array runs as given. `off` always uses the grouped count. The command reads the prompt on stdin (a request for one or two plain sentences in the second person, followed by the records as JSON lines) and answers on stdout. At most 64 KiB of stdout and 4 KiB of stderr are read, and the reply is collapsed to one line and clipped to 800 bytes. A non-zero exit, a timeout at `summary.timeout_seconds`, or an empty reply falls back to the grouped count, `Telegram 3 · Discord 1`, most held first. The command runs on your machine as you, with no sandbox beyond the timeout and the clip.

## State files

Under `~/.local/state/omarchy/distraction-space/`, honoring `$XDG_STATE_HOME`:

| File | Writer | Shape |
|---|---|---|
| `lock.json` | `lock` and `unlock` only | `{"locked": true, "since": "<iso>", "until": "<iso>\|null", "purpose": "<text>"}` |
| `state.json` | Listener, on every change; the bar watches this | `{"locked": false, "until": null, "purpose": "", "on_space": false, "site_block": "on", "listener_pid": 1234, "hold": true, "held": {"Telegram": 3}, "notification_hold": "on", "updated": "<iso>"}` |
| `expansion.json` | Listener after every successful config load or reload | The last validated expansion (`name`, `classes`, `hosts`, `senders`, `audio` per entry, plus `keep_reachable` and `nudges`) |
| `held.jsonl` | Listener while the hold is in effect | One line per held notification: `{"at": "<iso>", "app": "Telegram", "title": "<summary>", "body": "<body>"}`, fields clipped at 4096 bytes, newest kept under 64 KiB |
| `muted.json` | Listener while the hold is in effect | Sink-input index to `pid:starttime` for every stream this plugin muted |
| `silenced-owned.json` | Listener | The sender keys this plugin pushed into the shell's silenced list |
| `clone.json` | `setup` | Plugin id, paths, and SHA-256 of each first-party file and of the patch; its presence marks the clone as this plugin's |
| `addrs.json` | Network resolver | Last good resolution per host |
| `rules.json` | Window containment | JSON array of the Hyprland rule names this plugin set |
| `log` | Lock reasons, hook output, network batches | Text, path overridable with config `log` |

`state.json.site_block` is `on`, `off` (on the space, or an empty list), or `unavailable` (no privileged wrapper). `notification_hold` is `on`, `off`, or `unavailable` (the shell has no silenced list). Without a listener running, `state.json` goes stale and `distractions status --json` still answers from `lock.json` and hyprctl.

Runtime files live in `$XDG_RUNTIME_DIR`: `distraction-space.lock` (single listener), `distraction-space.config.lock` (config mutation flock), and `distraction-space.sock` (reload and refresh).

Lock expiry is lazy. `is_locked()` treats an `until` in the past as unlocked, and the listener's one-second tick is what turns that into a `state.json` write, a notice, and the `unlock` hook.

## Hooks

`hooks.lock`, `hooks.unlock`, `hooks.enter`, and `hooks.leave` are argv arrays, run detached with `DS_EVENT`, `DS_PURPOSE`, `DS_MINUTES`, `DS_REASON`, and `DS_HELD` in the environment. `DS_HELD` is a JSON object of app name to held count on `unlock` and `enter`, the same counts the summary is about to show, and `"{}"` on `lock` and `leave`. stdout and stderr go to the configured `log`, and failures are ignored.

The `lock` and `unlock` commands run their own hooks because they write `lock.json`. The listener runs `unlock` for an expiry it observes, and `enter` and `leave` on every workspace transition onto or off the space. The `enter`, `leave`, and `toggle` commands never run hooks themselves. With no listener running, the `enter` and `leave` hooks, the expiry `unlock` hook, and the summary for those two boundaries do not fire, while a manual `distractions unlock` still summarizes.

## Catalog shapes

`catalog.json` maps a product name to its identity in one of three shapes. Expansion produces `classes`: the native `class` when present, plus, for every host-bearing entry, the automatic web-app class `^chrome-<host>__.*$` built from its first host (the `pwa` host when given).

Native, with the `pwa` host, empty `hosts` so a messaging app is never blocked, `senders` for the hold, and `audio` for the mute:

```json
"Telegram": {
  "class": "org.telegram.desktop",
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

Hosts only, moved as an installed web app and blocked:

```json
"YouTube": {"hosts": ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"]}
```

Telegram therefore expands to `classes: ["org.telegram.desktop", "^chrome-web\\.telegram\\.org__.*$"]`. A `class=<regex>` list entry expands to one class and no hosts.

## Config writes and migration

Every write takes a blocking flock on `$XDG_RUNTIME_DIR/distraction-space.config.lock` with a 5 second timeout. On timeout the command exits 1 with "config busy" and leaves the file unchanged. `config set`, `list add`, `list remove`, and every menu save go through it; reads take no lock. A successful mutation asks the running listener to reload.

On the first load with no `distraction-space.json`, `list` is seeded from the union of the names in `~/.config/omarchy/app-list.json` and the `destinations` in `~/.config/omarchy/focus.json`, falling back to the fifteen defaults. `log` is taken from the old `focus.json` when it is present. The old files stay untouched, old state files under `~/.local/state/omarchy/` are ignored, and unreadable old files fall back to the defaults.

## Tests

```bash
python3 -m unittest discover -s tests
```

239 tests as of this commit, all offline. `tests/harness.py` builds a temporary XDG root per test, and the socket2 feed, `hyprctl`, `getent`, `busctl`, `pactl`, and the nft wrapper are all replaced with fakes, so nothing in the suite touches your real session, your real config, or the firewall.
