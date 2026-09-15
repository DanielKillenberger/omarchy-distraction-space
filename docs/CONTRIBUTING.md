# Contributing

```bash
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
```

That is all a change needs: clone, run the suite, open a pull request with code, tests, and docs. Nothing in the plugin depends on any other repository.

## The offline suite

The suite runs offline. [`tests/harness.py`](../tests/harness.py) gives every test its own temporary XDG root, the tests put fake `hyprctl`, `getent`, `busctl`, `pactl`, `systemctl`, `systemd-run`, `xdg-settings`, and nft binaries at the front of `PATH`, and the cgroup reads go to a fake `/proc`, so a run never touches your session, your user manager, your config, or your firewall. Keep the suite offline in a pull request.

The `/usr/bin` prefix keeps a shim-based version manager out of the way. Under mise's `python3` shim, most of `tests/test_hypr.py` fails here, because the child process resolves the real `hyprctl` instead of the fake. Plain `python3 -m unittest discover -s tests` is enough on a machine without one.

For opt-in firewall and web-app audio checks, see [live validation](internals.md#opt-in-live-validation). These checks are separate from the offline suite and must record both results and restoration.

## CI

[`.github/workflows/tests.yml`](../.github/workflows/tests.yml) runs that suite on every push to `main` and every pull request, on Ubuntu, with Python 3.11 and the newest 3.x the runner offers. The command is `python3 -m unittest discover -s tests`. The local `PATH=/usr/bin:$PATH` prefix is omitted there because the runner has no interpreter shim, and the prefix would hide the matrix interpreter behind Ubuntu's system `/usr/bin/python3`. An apt step installs `lua5.4` first, so the Lua fragment tests in `tests/test_hypr.py` run there instead of skipping.

## Linting the bar widget

Lint the bar widget with `qmllint` from `qt6-declarative`; it is not on `PATH`. Quickshell maps `qs.*` onto the shell root, so a bare `-I "$OMARCHY_PATH/shell"` cannot resolve `qs.Commons` or `qs.Ui`. Give it an import directory whose `qs` entry links to the shell instead.

```bash
mkdir -p /tmp/qmlimports && ln -sfn "${OMARCHY_PATH:-/usr/share/omarchy}/shell" /tmp/qmlimports/qs
/usr/lib/qt6/bin/qmllint -I /tmp/qmlimports BarWidget.qml
```

Two warnings remain, both noise. `Member "iconSlot" not found on type "QObject"` at `Style.bar.iconSlot`: `Style.bar` is an inline `QtObject` whose declared properties qmllint cannot see through the bare `QObject` type. `Type QProcess::ExitStatus of parameter exitStatus in signal called exited was not found` at the state process's `onExited`: the type lives in a Qt module this import path does not carry, and Omarchy's own `plugins/bar/indicators/ScreenRecording.qml` emits it verbatim under the same command. Anything else is a finding.

## The maintainer's task tracking

The maintainer tracks work with [flow-next](https://github.com/gmickel/flow-next). Its state, the `.flow` directory of specs, tasks, receipts, and memory, and the agent instruction files `CLAUDE.md` and `AGENTS.md` live in a separate repository, [omarchy-distraction-space-flow](https://github.com/DanielKillenberger/omarchy-distraction-space-flow), because Omarchy installs this checkout as it is and the marketplace reviews it that way. This is optional and only for working the pipeline the way the maintainer does: clone that repository next to this checkout and link the three names in; all three are ignored here, so the links never enter a commit.

```bash
git clone https://github.com/DanielKillenberger/omarchy-distraction-space-flow ../omarchy-distraction-space-flow
ln -s ../omarchy-distraction-space-flow/.flow .flow
ln -s ../omarchy-distraction-space-flow/CLAUDE.md CLAUDE.md
ln -s ../omarchy-distraction-space-flow/AGENTS.md AGENTS.md
```

Run those from the repository root, where the links belong.
