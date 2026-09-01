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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
