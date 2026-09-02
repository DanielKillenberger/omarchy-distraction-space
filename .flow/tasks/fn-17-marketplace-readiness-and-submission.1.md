# fn-17-marketplace-readiness-and-submission.1 Rename the id to io.github.danielkillenberger.distraction-space, bump to 2.1.0, fix the qmllint command

## Description
Rename the plugin id from `distraction-space` to `io.github.danielkillenberger.distraction-space`: `manifest.json` `id`, `BarWidget.qml` `moduleName` (the host registry keys bar widgets on it), the install path in `hypr/autostart.lua` and `hypr/bindings.lua` (`~/.config/omarchy/plugins/<id>/distractions`), and every README path under `~/.config/omarchy/plugins/`. Do NOT rename the config file `distraction-space.json`, the state directory, the runtime sockets and locks, the wrapper path `/usr/local/libexec/omarchy-distraction-space`, or the sudoers file; they never derived from the plugin id. Add a short migration note to the README's Install section for installs of the old id: `omarchy plugin remove distraction-space`, add again, re-copy the three snippets, run `distractions setup`. Bump `manifest.json` `version` to `2.1.0`. In the README's Contributing section replace the qmllint guidance with the working form: make an import directory whose `qs` entry symlinks `$OMARCHY_PATH/shell` and run `/usr/lib/qt6/bin/qmllint -I <that dir> BarWidget.qml` (the binary ships in qt6-declarative and is not on PATH); note that the one remaining `Style.bar.iconSlot` warning is a dynamic property and is noise. Verify `omarchy plugin validate .` passes and the qmllint command produces only that warning. Do not touch docs/marketplace-submission.md (task 2 owns it).

**Touches:** manifest.json, BarWidget.qml, hypr/autostart.lua, hypr/bindings.lua, README.md, docs/internals.md

## Acceptance
- [ ] TBD

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
