---
satisfies: [R1, R2]
---
# fn-22-the-space-is-a-process-group-one.3 distractions open: target resolution, browser profile, slice launch, forwarding

## Description
The single way into the slice (R1) and the forwarder for everything else (R2). Split from setup because launching and registering are independent; setup only writes `Exec=distractions open ...` strings.

**Size:** M
**Files:** `ds/launch.py` (new), `distractions`, `tests/test_launch.py` (new)
**Touches:** [ds/launch.py, distractions, tests/test_launch.py]

### Approach
- New `ds/launch.py`:
  - `classify_host(host, exp) -> entry | None`: exact or subdomain match against every listed host and `pwa` host. Shared by `open` and, later, the handler check.
  - `resolve_target(arg, exp, catalog)`: URL scheme present → `WebTarget(url, entry|None)`; else list entry name → web or native target; else catalog name → target with `restricted=False` logged once; else usage (exit 2). Non-http(s) URL → exit 2.
  - `pick_browser(cfg)`: config `browser` argv wins; else `xdg-settings get default-web-browser`, the `omarchy-launch-webapp` case list on the desktop id (`google-chrome*|brave*|microsoft-edge*|opera*|vivaldi*|helium*`, else `chromium.desktop`), then the first `Exec=` token of that desktop file searched in `~/.local`, `~/.nix-profile`, `/usr` share dirs. On this machine the id is `google-chrome.desktop` and the token `google-chrome-stable`.
  - Profile flags: `--user-data-dir=$XDG_DATA_HOME/omarchy/distraction-space/browser --profile-directory=Distraction --app=<url>`.
  - `launch_in_slice(argv)`: `systemd-run --user --scope --quiet --collect --slice=app-distraction.slice -- <argv>` via `subprocess.Popen(start_new_session=True, stdin/stdout/stderr=DEVNULL)`; catch `OSError`, not only `FileNotFoundError` (memory `bug/runtime-errors/hold-subprocess-launches-let-non-enoent-2026-09-02`).
  - `focus_existing(host)`: `hyprctl clients -j`, class matching `^[a-z-]+-<host>__-Distraction$`, focus on the space without switching the person's workspace (pattern at `ds/hypr.py:199-209`; do not use `_go_to_space`).
  - Native targets: read `Exec` from `<desktop>.desktop` found across the share dirs, strip field codes, launch in the slice.
  - `forward(url)`: read `previous_handler` from `entries.json`; missing or equal to the plugin's own id → `omarchy-launch-browser <url>`; else parse that desktop file's `Exec` per the Desktop Entry spec (quoting, `%u`/`%U` substitution, drop other field codes), run it detached and NOT in the slice; unparseable → exit 1 with one notice.
- `distractions`: `open` subcommand with one positional `target`, mapped to `launch.cmd_open`.

### Investigation targets
**Required** (read before coding):
- `/usr/share/omarchy/bin/omarchy-launch-webapp` — case list and desktop-file read
- `/usr/share/omarchy/bin/omarchy-launch-browser` — fallback forwarder behavior
- `ds/hypr.py:199-209` — `focus_workspace_lua`, `move_window_lua`
- `ds/lock.py:154-160,320-330` — enter gate and `_go_to_space`, to avoid
- `tests/harness.py:16-97` — `Sandbox.fake_bin`

**Optional:**
- `ds/catalog.py:34-35` — `pwa_class`
- https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html — field codes and quoting

### Key context
- Chromium hands a second launch of the same profile to the running instance; the scope exits empty. Do not treat that as failure.
- Exit codes: 0 launched/focused/forwarded, 1 no browser or no forwarder, 2 usage or non-http(s) URL.

## Acceptance
- [ ] Listed URL → fake `systemd-run` receives `--user --scope --quiet --collect --slice=app-distraction.slice` followed by the browser argv with the three profile flags; exit 0; the person's workspace is not switched
- [ ] Subdomain of a listed host is treated as listed; unlisted host is forwarded to the recorded handler with `%u` substituted and NOT via `systemd-run --slice`; exit 0
- [ ] Missing or self-referring handler record → `omarchy-launch-browser <url>`; unparseable `Exec` → exit 1 with one notice
- [ ] Existing window of the same host in the distraction profile is focused, no second launch
- [ ] Native target launches the catalog `desktop` entry's `Exec` in the slice; catalog name not in the list launches and logs once that it is not network-restricted
- [ ] `browser: ["brave"]` overrides the pick; no Chromium-family browser found → exit 1 with one notice; `open ftp://x` and `open` with no argument → exit 2
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes


## Done summary
`distractions open <target>` lands as `ds/launch.py` plus the CLI verb: a URL, list entry name, or catalog name resolves to a web launch (distraction browser, `--user-data-dir=$XDG_DATA_HOME/omarchy/distraction-space/browser --profile-directory=Distraction --app=<url>`) or a native launch (catalog `desktop` id's `Exec`), each run detached as a transient scope through `systemd-run --user --scope --quiet --collect --slice=app-distraction.slice`; an unlisted URL is forwarded outside the slice through the recorded previous handler's parsed `Exec` line, falling back to `omarchy-launch-browser` when the record is missing or self-referring (R1, R2).

### What changed (commits 80f3536, c2bdeba, 9f7090f, 3556e38, 100b1e5; base 5b87284)
- `ds/launch.py` (new): `classify_host` (listed or subdomain; the list names its own `www.` aliases), `_url_host` (control characters refused whole, RFC 3986 authority with percent triplets, port 1–65535, label grammar), `resolve_target` (URL scheme → http(s) only; else list entry; else catalog name logged once as not network-restricted; else usage), `pick_browser` (config argv wins; else the `omarchy-launch-webapp` case list on `xdg-settings get default-web-browser`, else `chromium.desktop`), `launch_in_slice` (detached `Popen`, `OSError` caught), `focus_existing`, `forward` (Desktop Entry `Exec` grammar with key-file escapes, double and single quotes, outside-quote backslash escapes, field-code substitution; `Exec` read from `[Desktop Entry]` only), `desktop_files` nearest first and `exec_argv(skip_own=True)` so a native launch passes over the plugin's own launcher entry that setup puts in front of the system entry.
- `distractions`: `open` subcommand → `launch.cmd_open`. Exit 0 launched/focused/forwarded, 1 no browser or no forwarder, 2 usage or malformed URL.
- `tests/test_launch.py` (new): one case per acceptance line through fakes on PATH, table-driven `parse_exec`, `expand_fields`, `classify_host`, `read_exec` group selection, malformed-authority usage cases, and the setup-then-open native regression.

### Review
cursor / gpt-5.6-sol-high, three rounds, each NEEDS_WORK on a narrowing URL-validation finding (unclosed IPv6 bracket, backslash before `@`, bare `%` and control characters), all fixed; flowctl's stall guard stopped a fourth cursor round on the same lineage. The person chose codex / gpt-6-astra at medium: round 1 NEEDS_WORK on a new P1 (native launch recursing into the plugin's own launcher after setup), round 2 SHIP with R1 and R2 met.

### Live checks left open, handed to the person
- Second `open` of the same host while on the space should focus the existing `chrome-<host>__-Distraction` window; the `hl.dsp.focus({ window = ... })` form is inferred from the Lua stubs.
- On this machine `~/.local/share/applications/google-chrome.desktop` runs `~/.local/bin/omarchy-open-chrome`, a personal wrapper that reroutes YouTube URLs to the Omarchy web app; the profile flags precede `--app=` so it passes them through today, and the wrapper is redundant once the URL handler routes listed links.

### Gates
- baseline: green via handoff (b5bd9393)
- verify: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at 100b1e5 on the integrated target, 336 tests, OK; receipt `.flow/tmp/green-receipts/100b1e5f-unittest.json`
- classify: FULL

stage: impl-review - ran (cursor gpt-5.6-sol-high 3 rounds, stalled; codex gpt-6-astra medium 2 rounds, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 80f3536, c2bdeba, 9f7090f, 3556e38, 100b1e5
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 336 tests at 100b1e5 on the integrated target; receipt .flow/tmp/green-receipts/100b1e5f-unittest.json), PATH=/usr/bin:$PATH python3 -m unittest tests.test_launch
- PRs: