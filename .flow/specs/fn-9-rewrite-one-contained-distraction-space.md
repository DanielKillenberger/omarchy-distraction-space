# Rewrite: one contained distraction space, one config, native menu UI

## Goal & Context
<!-- scope: business -->
<!-- Source-tag breakdown: 60% [user] / 25% [paraphrase] / 15% [inferred] -->

Every distraction lives on one named Hyprland workspace and stays there. Listed apps open only on that space. Listed sites do not load anywhere else. Reaching for a distraction from a normal workspace earns a nudge that names the app or site and says Super+D opens the space. Entering the space is a deliberate choice behind a confirm. A lock makes the space unreachable for a chosen number of minutes, with a purpose stated up front and a written reason to leave early.

The current tree does this across 5,700 lines in one script plus 1,600 lines of a second network stack, three membership lists, three dialog toolkits, two config files, and 1,700 lines of agent sandboxing. This spec replaces that with a small Python package, one config file that an agent can read and edit, one shipped catalog, and a menu UI built only from `omarchy-menu-select` and `omarchy-menu-input`. Notification holding, sound muting, and the agent summary move to fn-10, which builds on the listener, config schema, and state file defined here. The user chose, on 2026-09-01: do not start locked at login (so the schema carries no start-locked key), keep the purpose prompt on by default and configurable, fold fn-8 (block page, fast HTTPS fail, entry confirm) in, and rewrite as a package rather than trim.

## Architecture & Data Models
<!-- scope: technical -->

**Components.** The plugin directory ships:

- `distractions` - CLI entry (argparse, thin dispatch to the package). The dispatcher holds the final command table mapping every command to one `ds.<module>.cmd_<name>` function; a target that raises `NotImplementedError` exits 2 with "not yet". Wave 1 creates every module below with its contracted signatures as `NotImplementedError` stubs so later tasks never edit the dispatcher or another task's module.
- `ds/config.py` - schema, defaults, load/save with atomic write under a per-config flock, dot-key get/set, migration from `app-list.json` and `focus.json`.
- `ds/catalog.py` - shipped catalog plus expansion of every list entry into `{name, classes, hosts, senders, audio}`.
- `ds/state.py` - `state.json`, `lock.json`, `expansion.json` read/write, state and runtime directory paths, atomic JSON helpers.
- `ds/hypr.py` - hyprctl wrappers, workspace queries, named window rules, silent moves, cycle.
- `ds/net.py` - hostname resolution with last-good cache, keep-reachable subtraction, calls to the sudo wrapper, batch logging.
- `ds/feedback.py` - loopback HTTP block page and TLS ClientHello SNI catcher (fn-8 design).
- `ds/lock.py` - lock state, lazy expiry, reason log, hook runner, `enter`/`leave`/`toggle`/`next`/`prev`, the entry confirm.
- `ds/ui.py` - menu tree, prompts, list editor, settings, notices, all through `omarchy-menu-select` / `omarchy-menu-input` / `omarchy-notification-send`.
- `ds/listener.py` - the one long-running process: socket2 events, enforcement, network sync, timer expiry, feedback servers, reload socket, `state.json` and `expansion.json` writer, observed enter/leave hooks. fn-10 adds hold, capture, and sound mute to it.
- `ds/setup.py` - privileged wrapper install and removal, then plugin rescan. fn-10 adds the notification-service clone lifecycle as a step before the rescan.
- `distractions-nft` - root-owned wrapper owning table `inet omarchy_ds` (sets, reject chain, nat redirect chain).
- `catalog.json`, `BarWidget.qml`, `hypr/{windows,bindings,autostart}.lua`, `install/sudoers.omarchy-distraction-space`, `manifest.json` (kind `bar-widget` only), `README.md`, `tests/` (with `tests/harness.py`, the fake-binary-on-PATH helper owned by wave 1; wave 2 tasks add fixtures only inside their own test file).

Deleted in this spec: `focus_block.py`, `focus_dns.py`, `NotificationFilter.qml`, `PingCapture.qml`, `notification-members.json`, `app-list-defaults.json`, `defaults/destinations.json`, `focus.json`, and every current test file. The old notification mute goes with them; fn-10 brings holding back on the new base.

**Config file** at `~/.config/omarchy/distraction-space.json` (`$XDG_CONFIG_HOME` honored). The shape below is the whole schema, including the three keys whose behavior lands in fn-10 (`hold_notifications`, `mute_sounds`, `summary`); this spec validates and round-trips them and does nothing else with them. Missing keys take the defaults shown. Unknown keys are kept on save and ignored. There is no start-locked key: the lock never starts on its own.

```json
{
  "list": ["Telegram", "Discord", "x.com", {"name": "Slack", "class": "^Slack$", "hosts": ["slack.com", "app.slack.com"]}],
  "keep_reachable": [],
  "nudges": {"app_banner": true, "block_page": true, "entry_confirm": true},
  "hold_notifications": "off-space",
  "mute_sounds": true,
  "lock": {"default_minutes": 25, "ask_purpose": true, "reason_min_chars": 50},
  "summary": {"command": "auto", "timeout_seconds": 60},
  "hooks": {"lock": [], "unlock": [], "enter": [], "leave": []},
  "log": "~/.local/state/omarchy/distraction-space/log"
}
```

- `list` entries are a catalog name, a hostname (contains a dot, no scheme or path), a string `class=<regex>`, or an object with `name` and at least one of `class` or `hosts`. A hostname entry expands to itself plus its `www.` twin; a `class=` entry has no hosts.
- `hold_notifications` is one of `off-space`, `locked`, `never`. `summary.command` is `auto`, `off`, or an argv array. Both are validated here and consumed in fn-10.
- `hooks.*` are argv arrays run detached with env `DS_EVENT`, `DS_PURPOSE`, `DS_MINUTES`, `DS_REASON`, `DS_HELD` (JSON object of app to count; `{}` until fn-10 fills it).

**Config mutation contract.** Every write goes through `config.update(fn)`: take an exclusive `flock` on `$XDG_RUNTIME_DIR/distraction-space.config.lock` (blocking, 5 s timeout; on timeout refuse with exit 1 and the notice "config busy"), read the file, run `fn(cfg)`, validate, write atomically, release. `config set`, `list add`, `list remove`, and every menu action use it; nothing else writes the file. Two concurrent valid mutations therefore both land. Reads (`config get`, `list`, `status`) take no lock.

**Catalog** `catalog.json` maps product name to identity. Two shapes exist, native and PWA. Expansion produces `classes`, a list: the native `class` when present, plus for every host-bearing entry the automatic PWA class `^chrome-<host>__.*$` for its first host (the `pwa` host when given), so any listed site's installed web app is contained alongside the native app.

```json
{
  "Telegram": {"class": "org.telegram.desktop", "hosts": ["web.telegram.org", "telegram.org", "t.me"],
               "senders": ["Telegram Desktop", "org.telegram.desktop"],
               "audio": {"name": ["Telegram Desktop"], "binary": ["telegram-desktop", "Telegram"]}},
  "Discord": {"pwa": "discord.com", "hosts": ["discord.com", "discordapp.com", "discord.gg", "discord.media", "discordapp.net"]},
  "YouTube": {"hosts": ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"]}
}
```

Telegram therefore expands to `classes: ["org.telegram.desktop", "^chrome-web\\.telegram\\.org__.*$"]`; a `class=` entry expands to one class and no hosts. `senders` and `audio` are carried through expansion for fn-10 and unused here. Shipped defaults for a fresh `list` are the current fifteen: Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, Netflix. The catalog also carries Bluesky, Pinterest, Tumblr, LinkedIn.

**State** under `~/.local/state/omarchy/distraction-space/` (`$XDG_STATE_HOME` honored):

- `lock.json` - `{"locked": true, "since": "<iso>", "until": "<iso>|null", "purpose": "<text>"}`. Written by `lock` / `unlock` only.
- `state.json` - written only by the listener on every change, watched by the bar widget. `{"locked": false, "until": null, "purpose": "", "on_space": false, "site_block": "on", "listener_pid": 1234, "updated": "<iso>"}`. `site_block` is `on`, `off` (on the space or empty list) or `unavailable` (wrapper missing or refused). fn-10 appends its own keys to this shape.
- `expansion.json` - the last validated expansion (the full `{name, classes, hosts, senders, audio}` list plus `keep_reachable` and `nudges`), written by the listener after every successful config load or reload. This is the invalid-config fallback: when the config file is missing, unreadable, or fails validation, the listener loads `expansion.json` and enforces from it unchanged; when neither exists it enforces nothing and reports `site_block: off`.
- `addrs.json` - last good resolution per host. `rules.json` - window-rule names this plugin set. `log` - reason, lock, and network batch lines.

Runtime files in `$XDG_RUNTIME_DIR`: `distraction-space.lock` (single listener), `distraction-space.confirm` (one confirm dialog at a time), `distraction-space.config.lock` (config mutation), and `distraction-space.sock` (reload/refresh). Nothing else.

**Lock expiry is lazy.** `is_locked()` reads `lock.json` and treats `until` in the past as unlocked. No timer process exists. The listener's one-second tick notices the transition, rewrites `state.json`, notifies "Lock ended", and runs the `unlock` hook.

**Hook ownership.** Each hook has exactly one owner, so no action fires a hook twice. The `lock` and `unlock` commands run the `lock` and `unlock` hooks because they write `lock.json`; the listener runs the `unlock` hook for a lazy expiry it observes. The listener alone runs the `enter` and `leave` hooks, on every observed workspace transition onto or off the space, whatever caused it (Super+D, a click, the CLI, or a mouse move). `enter`, `leave`, and `toggle` never run hooks themselves. Without a listener, `enter`/`leave` hooks and the expiry `unlock` hook do not fire; that is the documented cost of running without it.

**Network.** Only the listener's main loop applies rules; worker threads resolve. Each sync is a generation-numbered job with a reason (`start`, `workspace`, `reload`, `periodic`, `refresh`): a `ThreadPoolExecutor` of eight resolves every listed host with a 2 s timeout each and a 10 s batch deadline (hosts still pending at the deadline use last-good), then posts `(generation, addresses)` to the main loop. At most one job runs; a request while one runs sets a rerun flag, so periodic and event jobs coalesce into one follow-up. The main loop discards a result whose generation is older than the latest requested, re-checks `on_space` immediately before applying, and only then merges with last-good addresses, subtracts `keep_reachable` addresses, and pipes one address per line to `sudo -n distractions-nft replace ds`. Jobs are requested on start, on every workspace change off the space, on reload, and every 30 s while off the space. Entering the space sends `flush ds` on the main loop and any in-flight result for an earlier generation is dropped. Each batch writes one log line: generation, reason, host count, resolved and failed counts, stale or coalesced marker, apply result, elapsed milliseconds. The wrapper renders, per fn-8, a filter output chain with `reject` (TCP reset for TCP, ICMP unreachable otherwise) on set members and a nat output chain redirecting TCP 80 to 28080 and TCP 443 to 28443 on set members. Wrapper interface stays exactly `replace|flush ds`, address-only stdin, table confinement.

**Feedback servers** (when `nudges.block_page` is true) bind 127.0.0.1 and ::1 on 28080 (HTTP block page naming the Host header, HTML-escaped, with the Super+D line and a note about the lock when locked) and 28443 (read ClientHello up to 2 s and 16 KiB, parse SNI, close; one banner per host per 30 s under a lock). Bind failure per socket notifies once and continues.

**Window containment.** The listener sets one named Hyprland rule per class in every expanded entry (`windowrule[omarchy-ds-<slug>-<n>]`, `n` indexing the entry's `classes`), records the names in `rules.json`, and disables names present in `rules.json` but absent from the new expansion. It also watches socket2 `openwindow` and `movewindow` and silently moves any client matching any listed class found off the space, then, when `nudges.app_banner` is on and the person is off the space, sends one banner per app per 30 s: glyph, title "<Name> lives in the distraction space", body "Super+D opens it.", click action `distractions enter`.

**UI.** `BarWidget.qml` shows the eye glyph, urgent color while locked, tooltip with lock deadline and purpose; it watches `state.json` and never polls. Left click runs `distractions lock` or `unlock`, right click `distractions menu`, middle click `distractions toggle`. `distractions menu` is a select menu with rows Lock… / Unlock…, Open the space / Leave the space, Edit list, Settings. Edit list shows every catalog product and every custom entry with a checked or unchecked glyph and toggles on select, plus "Add a site or app…" (input) and Back; each toggle saves and reloads. Settings shows one row per key below with the current value as subtext, plus Back:

- Booleans flip on select: `nudges.app_banner`, `nudges.block_page`, `nudges.entry_confirm`, `mute_sounds`, `lock.ask_purpose`.
- Enums cycle on select: `hold_notifications` (off-space, locked, never); `summary.command` cycles auto and off, and an argv array shows as "custom" and cycles to auto.
- Integers prompt an input and refuse non-integers or values below 0 with a notice: `lock.default_minutes`, `lock.reason_min_chars`, `summary.timeout_seconds`.
- `list` opens Edit list. `keep_reachable`, `hooks.*`, and `log` are shown read-only with their value as subtext; selecting one shows a notice naming the `distractions config set` form. They are edited by an agent or by hand, never from the menu.

**Setup.** `distractions setup` installs or refreshes the wrapper when the file on disk differs from the shipped one or is absent, with `sudo install -D -m 0755` into `/usr/local/libexec/omarchy-distraction-space/` and the rendered sudoers line with `sudo install -m 0440` after `visudo -cf`, refusing when any ancestor of the destination is writable by the invoking user, then runs `omarchy-shell shell rescanPlugins` as the last step. A rescan that is missing from PATH or exits non-zero leaves the installed files in place, prints the failure, and exits 1. No staging, no pin chain, no revalidation ladder. `distractions setup --remove` flushes the table and removes both files, then rescans the same way. fn-10 inserts its clone step before the rescan.

**Migration.** On first load with no new config file, `list` is seeded from names in `~/.config/omarchy/app-list.json` and `destinations` in `~/.config/omarchy/focus.json` (union), else the fifteen defaults; `log` is taken from the old `focus.json` when present. Old files stay untouched. Old state files under `~/.local/state/omarchy/` are ignored.

## API Contracts
<!-- scope: technical -->

CLI (`distractions <command>`), exit 0 on success, 1 on a refused or failed action, 2 on usage:

- `status [--json]` - human summary or the `state.json` shape computed live (lock, on_space, site_block from the last listener write, `listener_pid` null when absent).
- `toggle` / `enter` / `leave` - Super+D semantics. `enter` refuses with the lock notice while locked; with `nudges.entry_confirm` it shows the confirm first.
- `next` / `prev` - cycle occupied workspaces, skipping the space.
- `lock [MINUTES|forever] [PURPOSE...]` - no args opens the duration menu (default_minutes, 50, 90, Until I unlock, Other…) then the purpose input when `ask_purpose`. Already locked is a no-op with exit 0.
- `unlock [REASON...]` - expired or unlocked is a no-op. Manual unlock requires `reason_min_chars` characters; shorter refuses with exit 1 and a notice.
- `list` / `list add <entry>` / `list remove <name>` / `list expand` (JSON of the expansion).
- `catalog` - product names, one per line.
- `config path` / `config get <dot.key>` / `config set <dot.key> <json-or-string>` / `config edit` (opens `$EDITOR` or `omarchy-launch-editor`). `set` validates against the schema and refuses invalid values with exit 1.
- `menu` - the UI root.
- `listen` - the daemon. `reload` - asks the running listener to re-read config; exit 1 with a notice when none runs.
- `setup [--remove]`.

`ds.ui` module contract (task 6 implements, task 5 calls; wave 1 ships the signatures as stubs):

- `select(prompt, rows, timeout=None) -> int | None` - index of the chosen row, `None` on Escape or timeout. `input(prompt, timeout=None) -> str | None`. Both raise `ui.Unavailable` when the menu binary is missing or exits with a launch failure.
- `notify(title, body, *, glyph=None, action=None, urgent=False) -> None` - never raises.
- `confirm_enter(timeout=30) -> "enter" | "stay" | "unavailable"` - Enter row gives `enter`; Stay, Escape, or timeout give `stay`; `Unavailable` is caught and returned as `unavailable`.
- `prompt_lock(cfg) -> None | tuple[int | None, str]` - `None` when the duration menu is cancelled; otherwise minutes (`None` for Until I unlock) and the purpose (empty when `ask_purpose` is off or the purpose input is cancelled). Raises `Unavailable`.
- `prompt_reason(min_chars) -> str | None` - `None` on cancel. Raises `Unavailable`.
- `menu() -> int` - the UI root, returns the exit code.

`ds.lock` contract: `is_locked() -> bool`, `lock(minutes, purpose) -> int`, `unlock(reason) -> int`, `expire_if_due() -> bool` (true once per transition), `run_hook(name, env) -> None`, `enter() -> int`, `leave() -> int`, `toggle() -> int`.

Reload socket protocol: client sends `reload\n` or `refresh\n`, listener answers `ok\n` or `error\n` after the apply completes.

Wrapper: `distractions-nft replace ds` (stdin addresses) and `distractions-nft flush ds`; anything else exits 2.

Hyprland snippets keep today's bindings: Super+D toggle, Super+Alt+D move window, Super+Ctrl+Shift+F lock/unlock, Super+Tab and Super+Shift+Tab cycle, plus `hl.workspace_rule({ workspace = "name:distraction", persistent = true })` and the autostart line.

## Edge Cases & Constraints
<!-- scope: technical -->

- Listener absent: `lock`, `unlock`, `enter`, `status` still work from `lock.json` and hyprctl; `state.json` goes stale and the bar shows the last write; `enter`/`leave` hooks and the expiry `unlock` hook do not fire. `reload` reports it.
- Config missing, unreadable, or invalid JSON or schema, at listener start or on reload: notify once, load `expansion.json` and enforce from it (rules and site block unchanged), never flush the site block because of a parse error. With no `expansion.json` either, enforce nothing.
- Wrapper missing or `sudo -n` refused: `site_block` becomes `unavailable`, one notice per listener run, window containment continues.
- Every host unresolvable: keep last-good addresses; an empty final address set sends `flush`, never an empty `replace` that would install nothing while reporting `on`.
- Resolution finishing after the person entered the space: the main loop re-checks `on_space` before applying and drops the result, so a flushed block is never reinstalled from a stale job.
- Lock turned on while the confirm menu is open: `enter` re-checks the lock after the menu returns and shows the lock notice instead of switching.
- Second Super+D while a confirm is open: non-blocking flock on `distraction-space.confirm` makes it a silent no-op.
- Menu tooling missing (`omarchy-menu-select` not on PATH or the shell down): confirm fails open and enters; lock and unlock fall back to their argument forms and report the missing prompt.
- Config busy (another mutation holds the flock past 5 s): refuse with exit 1 and a notice; the file is unchanged.
- Hooks never block: spawned with `start_new_session=True`, stdout and stderr to the log, failures ignored.
- The nat redirect only rewrites flows whose destination is in the sets; redirected flows have a loopback destination and never meet the reject rule.
- No MITM: nothing is served on 28443 beyond reading the ClientHello.
- Python 3.11+ standard library only. No `gi`, no zenity.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** A window whose class matches any class of a listed entry, native or automatic PWA, opens on the distraction space from any workspace, and a listed window moved elsewhere returns there silently. Errors: hyprctl failure on a move is logged and skipped; the listener keeps running; a listener started against a corrupt config enforces the last validated expansion.
- **R2:** Off the space, TCP 80 to a listed address lands on the local block page naming the host; TCP 443 fails within a few seconds and one banner per host per 30 s names the host and Super+D; other traffic to listed addresses is rejected fast. On the space all of it flows, and a resolution that completes after entering the space never reinstalls the block. Errors: no SNI means fast fail without a banner; a bind failure notifies once and the redirect yields connection refused; wrapper missing yields `site_block: unavailable` and no other loss.
- **R3:** With `nudges.app_banner` true, opening a listed app from a normal workspace shows one banner per app per 30 s whose click enters the space. Errors: notification send failure is ignored.
- **R4:** With `nudges.entry_confirm` true and the lock off, Super+D onto the space asks Enter / Stay; Stay, Escape, or 30 s leaves the workspace unchanged; leaving the space never asks. Errors: menu tooling missing enters with one notice; lock turned on mid-dialog shows the lock notice instead.
- **R5:** `lock` with no arguments offers durations and, when `ask_purpose`, a purpose input; the lock persists with `until` and `purpose`; Super+D while locked shows the lock notice and does not switch. Errors: Escape on the duration menu locks nothing; Escape on the purpose input still locks with an empty purpose.
- **R6:** A lock ends by itself when `until` passes, observed lazily by every command and within one second by the listener, which notifies and runs the `unlock` hook. Errors: none beyond R13.
- **R7:** Manual `unlock` requires `reason_min_chars` characters and appends timestamp, purpose, and reason to `log`; `reason_min_chars` 0 unlocks without a prompt. Errors: a short reason refuses with a notice and keeps the lock.
- **R8:** `config get`, `config set`, `list add`, `list remove` read and write only `distraction-space.json`, validate against the schema including the fn-10 keys, mutate under the config flock so concurrent valid changes both land, and trigger a listener reload; every menu action writes through the same functions. Errors: invalid values refuse with exit 1 and the file is unchanged; a held flock past 5 s refuses with exit 1.
- **R9:** `status --json` prints the documented shape and works without a listener. Errors: none beyond a missing hyprctl, which sets `on_space` null.
- **R10:** First run without the new config seeds `list` from the old `app-list.json` and `focus.json` destinations when present, else the fifteen defaults, and writes the new file. Errors: unreadable old files fall back to defaults.
- **R11:** `setup` installs or refreshes the wrapper and sudoers in one sudo session, refuses a user-writable destination chain, runs the plugin rescan last, and `setup --remove` reverses it. Errors: sudo denied leaves no partial grant; a failed rescan leaves the files installed and exits 1.
- **R12:** The bar widget reflects `state.json` within its file-watch latency, left click locks or unlocks, right click opens the menu, middle click toggles the space. Errors: a missing `state.json` shows the unlocked idle state.
- **R13:** Each hook has one owner: `lock`/`unlock` commands run their hooks, the listener runs `enter`/`leave` on observed transitions and `unlock` on expiry, all detached with the documented env; one action never fires a hook twice. Errors: a failing hook never affects the action.
- **R14:** The repository contains none of the deleted files, `python3 -m unittest discover tests` passes, and the tree's Python outside `tests/` stays under 2,000 lines.

## Boundaries
<!-- scope: business -->

- No second network stack: no `/etc/hosts` edits, no resolver drop-ins, no DNS sinkhole, no `pkexec`. Suffix-DNS coverage is given up; the address set is the block.
- No MITM certificate or served HTTPS page.
- No notification holding, sound muting, held-ping capture, or agent summary in this spec; fn-10 owns them. Between the two merges, listed apps notify normally.
- No start-locked-at-login behavior and no key for it.
- No helpful / not-helpful ledger, no self-eval closing window, no history screen, no per-app notification toggles (declined memory entries stand).
- No settings panel in the shell; Omarchy ships no renderer for `barWidget.schema`, so the menu is the UI.
- No automatic editing of `~/.config/hypr/*`; snippets are still copied by hand.
- Killing established TCP flows on a workspace switch stays out of scope; they die by reject on their next packet.
- fn-8 is superseded by this spec and closed; its tasks are not worked separately.

## Execution plan
<!-- scope: technical -->

Eight tasks in three waves. Wave 1 creates every module as a stub with the contracted signatures, the final dispatcher table, and `tests/harness.py`. Wave 2 tasks each own one module and its test file, import only from wave 1, never edit the dispatcher, another module, or the harness, and can be dispatched in parallel.

1. **Foundation.** Package skeleton with stubbed modules, `config.py` (flocked `update`), `catalog.py` (`classes` expansion), `state.py` (`expansion.json` included), the dispatcher, `tests/harness.py`. Satisfies R8, R9, R10.
2. **Window containment** (`hypr.py`). R1, R3. Depends on 1.
3. **Site block and setup** (`net.py`, `distractions-nft`, `setup.py` including the rescan, sudoers template). R2 network half, R11. Depends on 1.
4. **Feedback servers** (`feedback.py`). R2 page and banner half. Depends on 1.
5. **Lock, hooks, entry confirm** (`lock.py`). R4, R5, R6, R7, R13 command half. Depends on 1.
6. **Menus and bar widget** (`ui.py`, `BarWidget.qml`). R12, menu half of R8. Depends on 1.
7. **Listener.** Wires 2 to 6 into `listener.py`: socket2 loop, reload socket, tick, generation-tagged network sync, `state.json` and `expansion.json`, observed hooks. R1, R2, R6, R9, R13 listener half end to end. Depends on 2, 3, 4, 5, 6.
8. **Cutover.** Deletions, hypr snippets, manifest, README, migration run against a copy of the old files, the line cap. R10, R14. Depends on 7.

## Decision Context
<!-- scope: both -->

### Motivation
<!-- scope: business -->

The person wants distractions contained in one space with nudges elsewhere, configurable by an agent and by a menu. Eight specs of accretion buried that under features whose maintenance cost outgrew their value. The choices recorded above were made in conversation on 2026-09-01 and are the contract for the rewrite.

### Implementation Tradeoffs
<!-- scope: technical -->

One network mechanism because a locked space is by definition off-space, so the always-on block already covers the lock; the focus block only added suffix DNS at the cost of arbitrary root escalation the sudoers file never granted. Lazy expiry instead of a timer process because every reader can compare a timestamp and the listener already ticks. A single `state.json` written by one process instead of nine locks and a generation protocol because QML file watching is cheap and the data is tiny. A separate `expansion.json` because rule names and addresses cannot rebuild classes, hosts, or names, and a corrupt config must not drop enforcement. Generation-tagged resolution with the apply on the main loop because a two-second-per-host resolve can outlive a workspace switch, and the only safe place to decide "still off-space" is the thread that sees workspace events. A config flock because atomic replace prevents torn files but not lost updates, and an agent and a menu can both write. Hooks with one owner each because the listener sees every transition and the CLI sees only its own. `omarchy-menu-select` and `omarchy-menu-input` for every prompt because they are the shell's own dialogs and remove zenity and GTK. A package with stubbed modules from wave 1 because each module can be tested with a fake binary on PATH, the existing test convention, and because disjoint write sets are what make wave 2 parallel. The whole config schema lands here, fn-10 keys included, so fn-10 adds behavior and never a migration. The fn-8 redirect design is kept as written because it was already reviewed and the user asked for exactly that feedback. Splitting notification holding into fn-10 because it carries a cloned notification server and an upstream conversation, which deserve their own review, and because this spec is already the size of one readable PR.
