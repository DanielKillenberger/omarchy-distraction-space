# The plugin owns launching while it is the default browser, and says so during setup

## Goal & Context
<!-- scope: business -->

Version 3 registers the plugin's link handler as the system's default browser so that a clicked link to a listed site opens inside the space. Two things follow that the person only discovers afterwards. First, Omarchy's own launchers resolve the default browser with `xdg-settings` and now get the plugin: the browser keybinds (`omarchy-launch-browser`, Super+Shift+Return and Super+Shift+B, and the private variant) run the handler's Exec with no arguments and nothing opens, and `omarchy-launch-webapp` matches the id against a Chromium-family list, misses, and falls back to Chromium, so every Omarchy web app the plugin did not take over now opens in the wrong browser. Second, nothing in setup explains that the default browser changes, why, or how to undo it, so Chrome's "make Chrome the default?" prompt reads as the plugin fighting the browser, and one click on it displaces the handler.

This spec makes the plugin own launching for everything while it is the default, so Omarchy behaves exactly as before for unlisted sites, and makes the default-browser change an explicit, explained choice during setup. Verified on this machine on 2026-09-05 against Omarchy's `omarchy-launch-browser`, `omarchy-launch-webapp`, and `default/hypr/bindings/applications.lua`.

## Architecture & Data Models
<!-- scope: technical -->

**`open` forwards what it does not own.** `distractions open` accepts no target, a target, and browser flags in any order. With no URL and no listed target, or with only flags, it forwards to the previous browser exactly as `omarchy-launch-browser` would have: the previous handler's Exec with the URL field code removed and the flags appended, detached, never slice-wrapped. A new `--app` flag means "if this is forwarded, forward as an app window": the previous browser's Exec with `--app=<url>` appended, which is what `omarchy-launch-webapp` does. A listed target with `--app` behaves as today, since the space always opens app windows. The flags Omarchy's launcher may hand over (`--incognito`, `--private-window`, `--inprivate`) and any other `-`-prefixed token pass through unchanged; `open` never interprets them. The forward is still the previous handler's Exec, so a Firefox previous browser receives `--private-window` and Chrome receives `--incognito`, whichever Omarchy chose. `open` with no arguments at all and no previous handler recorded, or a handler whose Exec cannot be parsed, falls back to `omarchy-launch-browser` with `BROWSER` dropped from the environment, and exits 1 with one line when that is missing too.

**Setup routes every Omarchy web-app entry.** Today `sync_entries` writes one launcher per listed product and backs up Omarchy's same-name file. It now also rewrites every entry in `~/.local/share/applications/` whose Exec starts with `omarchy-launch-webapp`: the file is backed up under `entries-backup/` and recorded in `entries.json` the same way, and the written entry keeps every key of the original except Exec, which becomes `distractions open --app <url> <extra args>` with the URL and any extra arguments carried over. Unlisted web apps therefore open in the previous browser as app windows, listed ones in the space, and Omarchy's menus never see the difference. `refresh` and the periodic tick re-run the entry sync, so an entry Omarchy regenerates (a new web app installed, a reinstall) is rewritten within a minute; `remove` restores every backup. An entry the plugin cannot parse is left alone and named once in the log.

**Setup asks once, in plain words.** Before the root prompt, an interactive setup whose config has no explicit `open_links_in_space` prints the explanation below and asks `Route links through the distraction space? [Y/n]`. The answer is written to `open_links_in_space` in the config file, so setup never asks twice; a rerun prints the current choice and the config key that changes it. A non-interactive setup (stdin is not a terminal, or `--yes`) takes the config value, defaulting to true, and prints the same paragraph as a notice. The text names the previous browser by its desktop Name.

```
Links from other apps

To open listed sites inside the space, the plugin has to become the
system's default browser. It is a router, not a browser: it sends
listed links to the distraction profile and forwards everything else
to <Browser> unchanged. Omarchy's browser keybinds and web apps keep
working. <Browser> may ask to become the default again; answer
"Don't ask again". "distractions remove" restores <Browser>.

Without it, a clicked link to a listed site opens in <Browser>, hits
the block page, and you reopen it from the launcher.
```

**The distraction profile never asks.** Chrome shows its default-browser prompt per profile, governed by the `browser.check_default_browser` preference. `open` creates the profile directory with a `Preferences` file holding that key set to false when the directory does not exist yet, before the first launch, and `profile import` sets the same key in the copied `Preferences` after the copy. The main profile is never touched.

**State.** `entries.json` gains nothing structural: the rewritten Omarchy entries are ordinary owned entries with a backup. The config file gains an explicit `open_links_in_space` value once setup has asked. `status` is unchanged.

## API Contracts
<!-- scope: technical -->

- `distractions open [--app] [target] [browser flags...]` - exit 0 when something was launched or forwarded, 1 when nothing could be launched (no previous handler and no `omarchy-launch-browser`), 2 on a malformed target. Flags after the target and before it are equivalent. The handler desktop entry keeps `Exec=distractions open %u`.
- `distractions setup [--yes]` - `--yes` answers the link question with the config value or true and suppresses every prompt; a terminal setup without it asks once. Exit codes unchanged.
- `distractions refresh` re-runs the entry sync in addition to what it does today; `distractions remove` restores every backed-up entry, Omarchy web apps included.
- Rewritten Omarchy entries: `Exec=<absolute distractions> open --app <url> [extra args]`, every other key verbatim.
- No new config keys; `open_links_in_space` becomes explicit in the file after setup.

## Edge Cases & Constraints
<!-- scope: technical -->

- `omarchy-launch-browser` runs the handler's Exec first token with no arguments, and with `--incognito` for the private keybind. Both shapes must open the previous browser.
- `omarchy-launch-webapp` passes `--app=<url>` plus extra arguments; the rewritten entry carries the extra arguments after the URL, and `open` passes them through.
- An Omarchy web app whose URL host is listed opens in the space, so the rewritten entry behaves exactly like the listed launcher setup already writes; the two paths must not produce two files for one product. Listed products keep today's entry; the rewrite applies to the remaining `omarchy-launch-webapp` entries only.
- The previous handler is the plugin itself (a rerun of setup after a displaced default that was fixed by hand): forwarding must skip the plugin's own entry, as `_is_own_launcher` already does, and fall back to `omarchy-launch-browser`.
- A setup rerun after the person answered no: no prompt, one line stating links are off and the config key that turns them on, the handler not registered, entries still rewritten (unlisted apps still forward, listed ones still open in the space from the launcher).
- Chrome rewrites `Preferences` on exit; setting `check_default_browser` while the browser runs is lost. `open` writes it only before creating the directory, and `profile import` already requires both browsers closed.
- Omarchy regenerates a web-app entry while the plugin runs: the periodic tick rewrites it; until then the entry opens in whichever browser Omarchy's launcher picked.
- `--yes` and a terminal: still no prompt.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** `distractions open` with no target, and with only browser flags, launches the previous browser's Exec with the flags appended and the URL field code removed, detached and outside the slice. Errors: no previous handler and no `omarchy-launch-browser` exits 1 with one line; a previous handler that resolves to the plugin's own entry is skipped.
- **R2:** `distractions open --app <unlisted url> [extra]` forwards to the previous browser with `--app=<url>` and the extra arguments; `--app` with a listed target opens in the space as today. Errors: a malformed URL exits 2.
- **R3:** Setup rewrites every `omarchy-launch-webapp` entry in the applications directory that is not a listed product into `distractions open --app <url> [extra]` with every other key verbatim, backs the original up in `entries-backup/`, records it in `entries.json`, and `remove` restores it; `refresh` and the periodic tick rewrite a regenerated entry. Errors: an entry whose Exec cannot be parsed is left untouched and logged once.
- **R4:** An interactive setup with no explicit `open_links_in_space` prints the explanation naming the previous browser and asks once; the answer is persisted to the config file and a rerun prints the current choice instead of asking. Errors: a non-interactive setup or `--yes` never prompts and prints the paragraph as a notice; an answer of no leaves the handler unregistered with `links: off`.
- **R5:** `open` creates the distraction profile directory with `Preferences` carrying `browser.check_default_browser: false` before the first launch, and `profile import` sets the key in the copied `Preferences`. Errors: an existing profile directory is never modified by `open`.
- **R6:** README's Install section explains, near the top, that setup registers a link handler as the default browser, why, what happens with no, and that remove restores the previous browser; `docs/internals.md` describes the forwarding and the entry rewrite; `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes offline. Errors: none.

## Boundaries
<!-- scope: business -->

- No change to Omarchy's scripts; the plugin adapts to them.
- No browser extension.
- No per-host handler registration; the desktop only offers per-scheme handlers.
- No change to the network, containment, or mute halves of version 3.
- The main browser profile's preferences are never modified.

## Decision Context
<!-- scope: both -->

- Forward through the previous handler's Exec over calling `omarchy-launch-browser`: the Omarchy script resolves the default browser again and would recurse into the plugin; it stays the fallback when no previous handler is recorded.
- Rewrite every Omarchy web-app entry over teaching `omarchy-launch-webapp` about the plugin: the script's case list is Omarchy's, and a plugin that needs a patch upstream to work is not installable from the marketplace.
- Ask once and persist over asking on every setup: a rerun is a repair, and repeating the question would teach people to skip it.
- The default answer is yes: the routing is the feature; the prompt exists so the change is understood, not to discourage it.
- Write the Chrome preference only into the distraction profile: the main profile belongs to the person.

## Quick commands

```bash
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
./distractions open --help
./distractions setup --help
```

## Early proof point

Task .1: `open` with no target and with `--incognito` opens the previous browser on this machine through Omarchy's own keybind script, proving the forwarding shape before setup depends on it.

## Requirement coverage

| Req | Description | Task(s) | Gap justification |
|-----|-------------|---------|-------------------|
| R1 | `open` forwards no-target and flags | .1 | — |
| R2 | `open --app` forwards app windows | .1 | — |
| R3 | Setup rewrites Omarchy web-app entries | .2 | — |
| R4 | Explicit link question, persisted | .3 | — |
| R5 | Distraction profile never asks | .1 | — |
| R6 | Docs and full suite | .3 | — |
