---
satisfies: [R1, R2, R3, R5]
---
# fn-26-visible-health-and-accessible-v3.1 Expose observation-aware health and v3 menu controls

## Description
Implement backward-compatible status health projection, quiet bar indicator, readable status action and menu controls for temporary release, link routing, site block, and snap-back. Consume the cross-spec observed_at/ping contract; never edit listener producer. Capture focused window before menu steals focus. Reuse config.update and current setting/IPC behavior; clarify saved vs applied especially setup-required link routing.

**Files:** ds/state.py, ds/ui.py, BarWidget.qml, tests/test_status.py, tests/test_ui.py
**Touches:** ds/state.py, ds/ui.py, BarWidget.qml, tests/test_status.py, tests/test_ui.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_status tests.test_ui

## Acceptance
- Parent R1-R3/R5 covered for healthy/disabled/unknown/unavailable/displaced/stale state and bounded unresponsive-listener check.
- Do not refresh observation evidence merely by reading status; old persisted schema remains readable.
- Menu cancellation does not save, failures are visible, and configured vs effective intent is truthful.
- Add tests using isolated fake ping/state; no real desktop changes.

## Done summary
Added observation-aware health, a quiet bar indicator/status reasons, and v3 menu controls including release of the window captured before menu focus changes. Existing top-level status keys remain; updated preserves the saved timestamp, response_at timestamps this read, and health/observed_at are additive.

Baseline: green, 33 tests passed using PATH=/usr/bin:$PATH python3 -m unittest tests.test_status tests.test_ui. New status and menu tests were observed red before implementation; final focused suite passes 44 tests. git diff --check passes. QML lint passes with only the repository-documented QProcess::ExitStatus and Style.bar.iconSlot warnings; log /tmp/fn26-qmllint.log.

The consumer expects fn27's observed_at ISO dictionary and ping IPC. Ping has a 0.2-second deadline and bounded reply; observations older than 121 seconds are stale. The bar now refreshes every 30 seconds in addition to its file watch, necessary to notice a stopped listener without further writes. Disabled services are choices, and the menu exposes their last observation separately. Settings persist through config.update, which already requests reload. Saved versus last-observed state is explicit; snap-back application is not independently verified. Link routing directs the person to distractions setup without taking over the browser. Existing key-shape pins and no-Timer assertion changed because the acceptance explicitly adds status fields and detects stopped listeners.

Documentation implications for conductor task fn26.2: document new status fields and updated semantics, quiet dot/tooltip and 30-second check, Status menu, three everyday setting labels, captured-window release using configured duration, saved-versus-observed behavior and setup needed for browser routing. Document live firewall/audio validation independently; this worker made no live desktop changes and claims no live evidence.

stage: impl-review - skipped(policy: parallel-wave, host-deferred - conductor owns the gate)

Integrated commit: 7981bbe8f580268ff467a873690e35f2a7240bb1. Fable (claude-fable-5-1 via Claude CLI) returned SHIP. Conductor repeated all 44 focused tests successfully. Nonblocking findings retained in .flow/reviews; empty-host health edge and polling/status semantics require final integration attention.
## Evidence
- Commits: 7981bbe8f580268ff467a873690e35f2a7240bb1
- Tests: baseline: green (33 tests), PATH=/usr/bin:$PATH python3 -m unittest tests.test_status tests.test_ui (44 passed), /usr/lib/qt6/bin/qmllint -I /tmp/fn26-qmlimports BarWidget.qml (exit 0; two documented warnings), git diff --check
- PRs: