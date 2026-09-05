---
satisfies: [R4, R5]
---
# fn-26-visible-health-and-accessible-v3.3 Preserve browser process and audio isolation

## Description
Live R4 validation found Chrome 152 portal startup reparenting its browser into app-com.google.Chrome-PID.scope outside the distraction slice. Implement a narrow launch correction so the browser and descendants remain in app-distraction.slice without disabling portal/crypto features or affecting the work browser. A temporary prototype pre-created the browser-expected scope inside the slice using an exec trampoline and passed actual audio mute/restore. Derive supported application identity from verified Chromium source, preserve opaque argv and existing launch semantics, and verify actual branch launch with isolated live profiles.

**Files:** ds/launch.py, tests/test_launch.py (a small internal launch trampoline file only if required)
**Touches:** ds/launch.py, tests/test_launch.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest tests.test_launch tests.test_cgroup tests.test_status

Additional live finding: Pulse stream restore gives distraction and work Chrome streams the same identity, so a work stream created during distraction mute inherits mute. Isolate the distraction browser audio restore identity per launch if validated, preserving existing user audio properties and native/work forwarding. Validate both pre-existing and later-created work streams.
## Acceptance
- Chrome portal startup cannot move the distraction browser out of the slice in the exercised live environment. Record source and real process/audio evidence.
- Work-browser scope and audio remain unaffected; no global overrides, fake sandbox environment, portal disabling or weaker process-boundary attribution.
- Browser argv/flags and URLs retain exact values; cancellation, missing executable and launcher failures retain existing behavior.
- Existing interfaces and major version3 preserved; unit naming/escaping deterministic and command inputs not shell-interpreted.
- Focused offline regressions and actual branch live check; do not claim untested browser families passed.


- Later-created unrelated work-browser streams remain unmuted while distraction audio is held and after release; actual live evidence required. Preserve any unrelated existing PULSE_PROP properties and keep changes local to distraction-browser launch.
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
