# Notification hold, sound mute, and the agent one-liner

## Goal & Context
<!-- scope: business -->
<!-- Source-tag breakdown: 65% [user] / 25% [paraphrase] / 10% [inferred] -->

While the person is off the distraction space, listed apps stay quiet: no banner and no sound. When a hold ends, one line from the person's own agent says whether anything mattered ("you missed basically nothing, no reason to check"), with a plain per-app count when no agent is available. The user chose on 2026-09-01: hold whenever off-space, mute the apps' own sounds too, and keep the summary as the outcome while dropping the sandboxing around it.

The holding itself belongs in Omarchy's notification service, which already has a do-not-disturb path that skips the popup and writes the notification to history. That path had no per-sender hook. This spec adds one as a shell patch, ships that patch with the plugin through Omarchy's clone mechanism until it is upstream, and builds the plugin side on the listener, config schema, and `state.json` that fn-9 defines.

## Architecture & Data Models
<!-- scope: technical -->

**Shell patch.** Branch `notifications-silenced-senders` in `~/Projects/omarchy` (commit "Silence individual notification senders alongside DND") adds to the notifications service: a persisted `silenced` string list next to `dnd` in `~/.local/state/omarchy/notifications.json`; `NotificationLogic.senderOrigin`, `normalizeSilenced`, `isSilencedSender`; `handleNotification` taking the DND path when `doNotDisturb` or `isSilencedSender(notification)` holds and the bypass rules do not; IPC methods on target `notifications`: `silencedSenders` (JSON array), `setSilencedSenders <json array>`, `silence <sender>`, `unsilence <sender>`; docs in `docs/notifications.md`; eleven assertions in `test/shell.d/notifications-test.sh`. A sender key is an `app_name` or, for a Chromium-derived sender, the origin host Chromium prepends to the body (Chromium reports every web app under the browser's own `app_name` and `desktop-entry`). Matching is case-insensitive and ignores a leading `www.`. The plugin ships this as `shell/notifications-silenced-senders.patch`, a unified diff of `Service.qml` and `NotificationLogic.js` only.

**Clone lifecycle** (second step of `distractions setup`, after fn-9's wrapper step and before its rescan). If the built-in service answers `omarchy-shell notifications silencedSenders`, remove any clone this plugin created and stop. Otherwise, if no `<user>.notifications` clone exists, run `omarchy plugin clone omarchy.notifications`, apply the patch with `patch -p1 --dry-run` then for real, and record in `~/.local/state/omarchy/distraction-space/clone.json` the SHA-256 of each first-party source file that was cloned. If the clone exists and `clone.json` matches the current first-party files, nothing to do. If the first-party files changed (an Omarchy update landed), re-clone: remove the plugin-created clone, clone again, re-apply, update `clone.json`. If the patch fails to apply, remove the clone so the untouched built-in comes back, and report that the hold is unavailable until the patch is refreshed. A `<user>.notifications` clone this plugin did not create (no `clone.json`) is never touched; setup reports it and leaves the hold unavailable. `setup --remove` removes only a plugin-created clone. The listener runs the same hash comparison once at start and, on drift, notifies once that `distractions setup` is needed; it never re-clones by itself, because the notification server changes hands during the rescan.

**Effective hold** = (`hold_notifications` is `off-space` and not on the space) or (`locked` and the lock is active). `never` is always false.

**Hold push** (`ds/hold.py`, driven by the listener). On every transition of effective hold, on reload, and at start, the listener reads the shell's current list with `silencedSenders`, then calls `setSilencedSenders` with that list plus (hold on) or minus (hold off) the plugin's sender keys: the catalog `senders` of every listed native entry, the `pwa` host of every PWA entry, and the hosts of every plain hostname entry. Keys the person added by hand survive both directions. A clean listener exit removes the plugin's keys. If the IPC fails because the method is missing, `notification_hold` is `unavailable` and one notice names the fix (`distractions setup`).

**Capture** (`ds/hold.py`). The listener keeps `busctl --user monitor --json=short --match "interface='org.freedesktop.Notifications',member='Notify'"` running for its whole life, restarting it with backoff (1, 4, 16 s) if it exits. Each line is one JSON object whose `payload.data` is `[app_name, replaces_id, app_icon, summary, body, actions, hints, timeout]`. While effective hold is on, a Notify whose sender matches the plugin's keys (same rule as the shell patch) appends `{"at": "<iso>", "app": "<catalog name>", "title": "<summary>", "body": "<body>"}` to `held.jsonl`, fields clipped at 4096 bytes, newest kept under 64 KiB. Verified on this machine on 2026-09-01: one `omarchy-notification-send` produced exactly one such line.

**Sound mute** (`ds/hold.py`). With `mute_sounds` true and hold on, `pactl -f json list sink-inputs` plus a `pactl subscribe` stream identify streams of listed apps by catalog `audio.name` / `audio.binary` against `application.name` / `application.process.binary`, or by `--app-id=<pwa host>` in the cmdline of the stream's process or one of up to eight ancestors. The listener mutes them and records index to `pid:starttime` in `muted.json`. When hold ends it unmutes only recorded indexes whose identity still matches, then clears the file. A stream that cannot be attributed stays audible. A bare browser name or binary is never member identity.

**Summary** (`ds/summary.py`). Runs when a lock ends (timer or manual) and when the space is entered, over the records in `held.jsonl`, then clears them. Zero records means no notice. With `summary.command` = `auto`, the command is `claude -p --output-format text` when `claude` is on PATH, else `grok -p` (flags before `-p`), else the count. A custom argv receives the prompt on stdin and answers on stdout. The prompt asks for one or two plain sentences in the second person on whether anything needs attention, given the records as JSON lines. The reply, clipped to 800 bytes, shows as one notification titled "While you were away". On `off`, command failure, timeout at `summary.timeout_seconds`, or an empty reply, the body is the grouped count ("Telegram 3 · Discord 1"). The `unlock` and `enter` hooks receive the counts as `DS_HELD`.

**State.** `state.json` gains `"hold": true, "held": {"Telegram": 3}, "notification_hold": "on"`. `notification_hold` is `on`, `off`, or `unavailable`. New files: `held.jsonl`, `muted.json`, `clone.json`. The bar widget shows the held total after the glyph when above zero.

## API Contracts
<!-- scope: technical -->

- `distractions senders` - the sender keys the listener pushes, one per line.
- `distractions setup [--remove]` - gains the clone step described above; exit 1 when the patch cannot be applied, with the built-in restored.
- `distractions status --json` - includes the three new keys.
- Shell IPC used: `omarchy-shell notifications silencedSenders` and `setSilencedSenders '<json>'`. Nothing else in the shell is called.
- `held.jsonl` line shape and `state.json` additions as shown above are the contract for hooks and for any external reader.

## Edge Cases & Constraints
<!-- scope: technical -->

- The shell restarts (update, crash) and comes back with the persisted `silenced` list, so a hold survives it; the listener re-pushes on the next transition and on reload.
- The person toggles global DND themselves: unaffected, the two lists are independent in the shell.
- The clone carries the whole notification service, so a bug in the clone means no notification server at all. The dry run and remove-on-failure cover a patch that does not apply; a logic bug is what the upstream tests and the live check in task 4 are for.
- Omarchy fixes to the notification service reach the machine only after the next `distractions setup`. Accepted until the patch is upstream.
- `busctl` missing: capture is off, logged once; holding and muting still work, the summary falls back to the count of zero and shows nothing.
- A held ping from a sender the catalog does not name (custom hostname entry) is attributed to that entry's `name`.
- A lock ending while on the space: summary runs once; entering the space afterwards finds no records and shows nothing.
- No agent sandboxing beyond the timeout and the output clip; the summary command is the person's own CLI on their own machine.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** `setup` creates the `<user>.notifications` clone with the shipped patch applied when the built-in lacks `silencedSenders`, records the cloned first-party hashes, re-clones and re-applies after an Omarchy update changed those files, and removes the clone once the built-in answers `silencedSenders`. Errors: a patch that no longer applies removes the clone, restores the built-in, and reports the hold unavailable; a clone the plugin did not create is left alone and reported; `setup --remove` removes only a plugin-created clone.
- **R2:** While effective hold is on, the shell's silenced list contains every plugin sender key and banners from listed apps do not appear; when hold ends only the plugin's keys are removed and hand-added keys survive. Errors: a shell without the method yields `notification_hold: unavailable` with one notice while capture and mute continue.
- **R3:** Each held Notify seen on the bus is appended to `held.jsonl` and `state.json.held` carries the per-app counts. Errors: a Notify the matcher cannot attribute is left alone; `busctl` exiting is restarted with backoff and logged; an unwritable state dir drops the record.
- **R4:** With `mute_sounds` true, streams attributable to listed apps are muted while hold is on and the ones this plugin muted are unmuted when it ends. Errors: `pactl` missing disables the feature with one log line; an unattributable stream stays audible; an index reused by another stream is never unmuted by mistake.
- **R5:** When a lock ends or the space is entered with held records present, one notification titled "While you were away" shows the agent's one-liner, or the grouped count when the command is `off`, missing, failing, timing out, or answering empty; records clear afterwards and hooks receive `DS_HELD`. Errors: zero records shows nothing.
- **R6:** A clean listener exit removes the plugin's sender keys from the shell's list, and a fresh listener start pushes them again when hold is effective. Errors: the shell being down at exit is ignored; the next start reconciles.
- **R7:** Nothing in fn-9 changes behavior when the hold is unavailable: containment, site block, lock, menu, and hooks work identically. Errors: none.
- **R8:** `python3 -m unittest discover tests` passes with the new modules, the shipped patch applies cleanly to the first-party files of the installed Omarchy version, and the upstream `test/shell.d/notifications-test.sh` passes on the patched checkout.

## Boundaries
<!-- scope: business -->

- No plugin-side notification filtering: the plugin never binds the notification service or edits its popup model.
- No edits under `/usr/share/omarchy`; the shell change reaches the machine only through Omarchy's clone mechanism or an upstream release.
- No helpful / not-helpful ledger, no self-eval window, no history screen, no per-app toggles beyond the list itself.
- No sandboxing of the summary command: no isolated home, no canary, no rlimits.
- Opening the upstream PR is a human step after this spec; the spec only keeps the patch applying.

## Decision Context
<!-- scope: both -->

### Motivation
<!-- scope: business -->

A ping on a work workspace is the distraction escaping its space, so holding is part of containment. The summary is the reason to trust the hold: the person learns nothing mattered without checking.

### Implementation Tradeoffs
<!-- scope: technical -->

Silencing in the shell instead of plugin QML because Omarchy's DND already does the exact thing for every sender, `handleNotification` had no per-sender hook, and pulling rows back out of the popup model tied 500 lines of QML to three internal service properties; the patch is 167 lines including tests and docs. Delivery through `omarchy plugin clone` because that is the mechanism Omarchy provides for changing a built-in plugin without touching `/usr/share/omarchy`: the clone replaces the built-in and keeps the `notifications` IPC target, so the plugin code is the same whether the method comes from the clone or a future release. A hash record of the cloned files is what lets `setup` tell an Omarchy update from a stale clone. Capture over the session bus because `busctl --user monitor --json=short` hands the listener each Notify as one JSON line, which makes the plugin independent of the shell's popup model for the summary text and removes the last reason for plugin notification QML. Muting the apps' own streams because the Omarchy notification server plays no sounds; every ping sound is the app's own audio, and the previous PWA-identity walk is kept in its small form because there is no other way to tell one Chromium web app's stream from another. The summary as a configurable command with the count fallback because the desired outcome is one sentence from the person's agent, and the previous sandbox defended against a threat that does not exist for a local CLI reading local notification text.
