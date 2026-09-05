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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
