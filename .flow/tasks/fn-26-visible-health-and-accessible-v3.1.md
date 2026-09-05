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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
