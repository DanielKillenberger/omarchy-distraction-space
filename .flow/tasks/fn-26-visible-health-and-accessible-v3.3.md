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
Recognized Chrome/Chromium web launches now reserve Chromium's expected portal scope inside app-distraction.slice with an exec trampoline. Browser PID and opaque arguments survive the shell and systemd-run exec chain; native launches and unknown wrappers retain the existing generic scope path.

Baseline: green, 49 focused tests. The actual-exec regression first failed because the portal --unit was absent. Initial scope-fix focused tests: 53 passed; full suite at c559bdc after host cleanup: 413 passed, rc 0. Final followup focused suite: 58 passed, rc 0; the conductor owns the final integrated full suite. Logs: /tmp/fn26-3-baseline.log, /tmp/fn26-3-red.log, /tmp/fn26-3-grok-tests.log, /tmp/fn26-3-full.log. git diff --check passed. Grok4.6 high implemented the mechanical change; host corrected the source-path citation and simplified test fixtures, inspected changes, verified and committed.

Regression coverage: test_known_browser_trampoline_keeps_portal_scope_pid_and_opaque_argv checks actual executed static trampoline, expected unit name with the browser PID, exact opaque arguments, target slice and no command-substitution side effect. test_exact_basename_map covers identities/channels, paths and near-match exclusions. test_unknown_wrapper_and_public_launch_in_slice_stay_generic preserves fallback and public native semantics. test_browser_exec_failure_after_scope_is_a_failed_launch covers early browser failure; existing missing-browser, scope-launch failure, cancellation/focus and exact URL regressions remain passing.

Source: Chromium 152.0.7977.64 components/dbus/xdg/systemd.cc requests app-<GetAppName>-<PID>.scope with replace mode, PIDs and no Slice. base/version_info/nix/version_extra_utils.cc derives Chrome/Chromium identity and beta/unstable/canary suffixes. Exact sources: https://chromium.googlesource.com/chromium/src/+/refs/tags/152.0.7977.64/components/dbus/xdg/systemd.cc and https://chromium.googlesource.com/chromium/src/+/refs/tags/152.0.7977.64/base/version_info/nix/version_extra_utils.cc . Local copies: /tmp/fn26-152-components_dbus_xdg_systemd.cc and /tmp/fn26-152-version_extra_utils.cc.

Limitations: map recognizes explicit executable basenames only, including the separately inspected current omarchy-open-chrome exec wrapper. Mapped wrappers must preserve the PID and expected channel identity; arbitrary wrappers, custom wrapper-altered identities, Brave and other browser forks remain unverified on the generic path. No version probes, global scope overrides, channel environment rewriting, portal disabling or public interface changes. Browser child Pulse properties receive only the specific audio identity described below. Chromium channel mappings have offline coverage, not live validation for each channel.

Live evidence is owned by work_health/conductor: the prior reserved-scope prototype passed actual audio mute/restore with work audio unchanged (/tmp/fn26-live-audio-reserved-result.json), but it is not evidence of this committed implementation. Actual branch validation is running separately and must be attached by the conductor before completing R4/task. This worker changed no live session state and claims no live verdict.

stage: impl-review - skipped(policy: parallel-wave, host-deferred - conductor owns the gate)

Task remains in_progress. Conductor owns shared receipts, integration, Fable review, actual branch live evidence and flowctl done.

Followup d5ba429: actual live validation exposed a separate shared audio restore identity. Muting a distraction stream caused a later work-browser stream to inherit mute even though branch process attribution correctly rejected the work stream. WirePlumber /usr/share/wireplumber/scripts/node/state-stream.lua formKey prioritizes application.id over application.name. A browser-only child environment now appends application.id=io.github.danielkillenberger.distraction-space to PULSE_PROP. Existing property text, quoted values, PULSE_SINK and other environment values remain intact; parent environment, native launches and forwarded browser launches remain unchanged. Installed libpulse parser confirmed duplicate keys are last-wins. This applies to known and unknown distraction browser executables. Direct restore-id and media.role overrides were refuted prototypes and do not ship.

The same followup derives inherited channel suffixes for raw chrome/chromium from the verified Chromium GetAppName source: beta, unstable and canary are exact supported suffixes; stable, extended, unknown and absent yield no suffix. Packaged channel wrappers keep their static identities because they override the channel. The inspected /opt/google/chrome/google-chrome sets CHROME_VERSION_EXTRA=stable; /usr/bin/google-chrome-stable and current Omarchy --app wrapper exec that path. No supplied environment text becomes part of a unit identifier unless it matches one of the fixed suffix constants.

New tests were observed red before production edits (/tmp/fn26-3-followup-red.log); final focused suite passes 58 tests (/tmp/fn26-3-followup-focused.log). Tests cover channels/hostile values, static wrappers, known and unknown browser child env merge, parent env preservation, native/forward behavior, plus actual executed trampoline child properties. Live property prototype /tmp/fn26-live-audio-application-id-result.json passed the newly-created work-stream scenario; work_health is rerunning the final committed helper without prototype overrides, and conductor must attach that result before completing the task.

Live followup caveat: the first final-helper run confirmed the separate application.id and an unmuted newly-created work stream, but release was inconclusive because the test distraction stream began pre-muted from persisted stream restore without a branch-owned record. work_health is establishing a known test baseline by unmuting only that isolated stream before requiring a listener-owned mute/release cycle. This must not be represented as proof of automatic recovery from persisted pre-mute after an unclean session.

Conductor integration: 433 tests passed (one intentional live-test skip). Fable implementation review SHIP (claude-fable-5-1). stage: impl-review - ran (model: claude-fable-5-1).
Final committed helper live validation passed: exact source hash, browser/audio slice containment, owned mute/release, new work stream unaffected. Durable evidence: .flow/evidence/fn26-live-validation.json. Pre-muted streams remain intentionally unclaimed.
## Evidence
- Commits: 41fc9064bacb767b65ae7e7b94fd5a55120f6d7e, 396ba9bc1fe30aa43d01bc8da9366da086d5fd15
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (433 passed, 1 skipped), Final live branch browser/audio validation: .flow/evidence/fn26-live-validation.json
- PRs: