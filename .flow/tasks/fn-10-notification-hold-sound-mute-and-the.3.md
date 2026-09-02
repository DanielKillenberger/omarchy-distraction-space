---
satisfies: [R4]
---
# fn-10-notification-hold-sound-mute-and-the.3 Sound mute of listed apps' streams while hold is on

## Description
Implement the audio half of `ds/hold.py`: `pactl -f json list sink-inputs` parse, `pactl subscribe` stream for new sink-inputs, attribution by catalog `audio.name`/`audio.binary` or `--app-id=<pwa host>` in the stream process's cmdline or up to eight ancestors (never a bare browser identity), `mute(index)` with `muted.json` recording `pid:starttime`, `unmute_owned()` verifying identity before unmuting, `pactl` missing disables with one log line. Wire into the listener on hold transitions.

**Files:** `ds/hold.py`, `ds/listener.py`, `tests/test_audio.py`.

## Acceptance
- Native and PWA streams from fixtures are attributed; a bare Chromium stream is not.
- Streams muted by the plugin are unmuted on hold end; a reused index with a different `pid:starttime` is left alone.
- Missing `pactl` disables the feature without affecting the hold.

## Done summary
Implemented the audio half of `ds/hold.py` and wired it onto the listener's hold transitions. `audio_table` maps catalog `audio.name` / `audio.binary` and PWA hosts to entry names; `attribute_stream` matches native streams by name or binary and Chromium streams only through a web-app flag in the stream process's cmdline or up to eight ancestors, so a bare browser stream is never a member. `Mute` mutes attributable audible streams on hold-on, records index to `pid:starttime` in `muted.json`, unmutes only recorded indexes whose identity still matches on hold-off and on listener exit, keeps and retries (every 16 s from the listener tick) any record whose listing or unmute failed, and reloads its records after a crash. `pactl subscribe` runs only while hold is on and `pactl list` succeeds, as a `_Tail` (the busctl lifecycle extracted from `Capture`: 1/4/16 s backoff, clean stop, and now EOF reaping so an exited child no longer spins the select loop). A missing `pactl` disables the feature with one log line; a failing one logs once. Listener tests gained quiet `omarchy-shell` / `busctl` / `pactl` stubs (conductor-authorized) so they never reach the real shell IPC, bus monitor, or PulseAudio.

Spec deviation, deliberate: the spec names `--app-id=<pwa host>`, but Omarchy's `omarchy-launch-webapp` launches web apps with `--app=<url>` (verified on this machine; Chromium uses `--app-id=` only for installed PWAs, with a hash id). Both spellings are accepted and `--app=` resolves to its host. Known limit, inherent to the design the spec accepted: when a web app is opened while the browser already runs, the app window lives in the existing browser process whose cmdline carries no web-app flag, so its stream cannot be attributed and stays audible.

Tests: `tests/test_audio.py` covers attribution (native, PWA via `--app=` ancestor and `--app-id=`, bare Chromium even when a custom entry names Chromium as audio, the eight-ancestor cap), scan/record/release with identity, a reused index with a different identity, a user-muted stream left alone, pump events (new rescans, remove forgets), EOF reaping, subscribe gated on list health, missing `pactl` once, failing `pactl` with release retry, a stuck unmute retried, and one listener-level pass through hold on/off/on/exit. Follow-up noted, not built: README documentation of `muted.json` belongs to task 4.

stage: impl-review - ran [round 1 NEEDS_WORK (P1: failed release not recoverable) .. round 2 SHIP]

stage: plan-sync - skipped(config: planSync.enabled != true)

## Evidence
- Commits: 5deb73c41730cf904f45dd7293b67c35147615ef, 0eb9a1fd96cb77904390a2c1e8fcd4f9f73aed4c, 206e13eb9efa798f4d2410c2be96cb4d944e10d0
- Tests: baseline: green via handoff (verified at 9788bdcc by fn-10-notification-hold-sound-mute-and-the.2; 204 tests), PATH=/usr/bin:$PATH python3 -m unittest tests.test_audio tests.test_hold, PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (214 tests, OK, gate receipt unittest at 206e13e)
- PRs: