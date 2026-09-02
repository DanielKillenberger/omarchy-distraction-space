---
satisfies: [R1, R2, R3, R4]
---
# fn-17-marketplace-readiness-and-submission.1 Rename the id to io.github.danielkillenberger.distraction-space, bump to 2.1.0, fix the qmllint command

## Description
Rename the plugin id from `distraction-space` to `io.github.danielkillenberger.distraction-space`: `manifest.json` `id`, `BarWidget.qml` `moduleName` (the host registry keys bar widgets on it), the install path in `hypr/autostart.lua` and `hypr/bindings.lua` (`~/.config/omarchy/plugins/<id>/distractions`), and every README path under `~/.config/omarchy/plugins/`. Do NOT rename the config file `distraction-space.json`, the state directory, the runtime sockets and locks, the wrapper path `/usr/local/libexec/omarchy-distraction-space`, or the sudoers file; they never derived from the plugin id. Add a short migration note to the README's Install section for installs of the old id: `omarchy plugin remove distraction-space`, add again, re-copy the three snippets, run `distractions setup`. Bump `manifest.json` `version` to `2.1.0`. In the README's Contributing section replace the qmllint guidance with the working form: make an import directory whose `qs` entry symlinks `$OMARCHY_PATH/shell` and run `/usr/lib/qt6/bin/qmllint -I <that dir> BarWidget.qml` (the binary ships in qt6-declarative and is not on PATH); note that the one remaining `Style.bar.iconSlot` warning is a dynamic property and is noise. Verify `omarchy plugin validate .` passes and the qmllint command produces only that warning. Do not touch docs/marketplace-submission.md (task 2 owns it).

**Touches:** manifest.json, BarWidget.qml, hypr/autostart.lua, hypr/bindings.lua, README.md, docs/internals.md

## Acceptance
- [ ] TBD

## Done summary
Renamed the plugin id to `io.github.danielkillenberger.distraction-space` in `manifest.json`, `BarWidget.qml` `moduleName`, both Hyprland snippet helper paths, and every README install path plus the `omarchy bar move` command; bumped `version` to 2.1.0; added a migration note for installs of the old id to the README Install section; replaced the Contributing lint guidance with the symlinked-import-directory qmllint command and named the one remaining `Style.bar.iconSlot` warning as noise (it is a readonly property on an inline `QtObject` in `Style.qml` that qmllint cannot see through the bare `QObject` type). Config, state, socket, wrapper, and sudoers names are unchanged. `docs/internals.md` carries no id-derived path, so it is untouched. The README test count moved from 255 to 256 to match the suite.

baseline: green (validate rc=0; qmllint working form rc=0 with the one warning; suite 256 OK)
verify: validate rc=0; qmllint rc=0 with only the iconSlot warning; suite red once on `test_feedback.FeedbackTests.test_r1_concurrent_splices_to_one_destination_take_distinct_ports` (recorded ports 33061 == 33061, an ephemeral port, not the 61000 splice range; no Python in this diff; focused 5/5 green), then 256 OK on a second full run with GREEN_RECEIPT c8481941-unittest. That flake predates the task and is worth a look outside it.

stage: impl-review - skipped(policy: parallel-wave + host-deferred - conductor owns the gate)

### Integration (conductor)

Cherry-picked onto the spec branch as ea8b4bb15409a4ac0686860ad416d625607a7e7d (workspace commit c848194) after task 2 landed. Review (cursor, gpt-5.6-sol-high): SHIP on round 1. Quiesce verification at ea8b4bb15409a4ac0686860ad416d625607a7e7d: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` 256 tests OK (receipt .flow/tmp/green-receipts/ea8b4bb1-unittest.json), `omarchy plugin validate .` rc 0, qmllint with the qs symlink import dir one known warning. The v2.1.0 tag is placed on main after the PR merges.

stage: wave-dispatch - ran [2 tasks, native worktrees, disjoint Touches, no join collision]
stage: impl-review - ran [round 1 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: ea8b4bb15409a4ac0686860ad416d625607a7e7d
- Tests: omarchy plugin validate . (rc=0, baseline and verify), mkdir -p /tmp/qmlimports && ln -sfn "${OMARCHY_PATH:-/usr/share/omarchy}/shell" /tmp/qmlimports/qs && /usr/lib/qt6/bin/qmllint -I /tmp/qmlimports BarWidget.qml (rc=0, one warning: Style.bar.iconSlot missing-property; verified with OMARCHY_PATH set and unset), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (baseline: 256 OK; verify run 1: FAILED 1, test_feedback test_r1_concurrent_splices_to_one_destination_take_distinct_ports, no Python in the diff, focused 5/5 green; verify run 2: 256 OK, GREEN_RECEIPT c8481941-unittest), quiesce at ea8b4bb: unittest 256 OK (receipt .flow/tmp/green-receipts/ea8b4bb1-unittest.json), validate rc 0, qmllint one known warning
- PRs: