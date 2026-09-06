---
satisfies: [R1, R2, R3]
---
# fn-33-orphaned-mutes-are-released-and-every.1 Implement orphaned-mute release and mute logging

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
`Mute.release` now sweeps the distraction slice: when the hold ends, and once at listener start while the hold is off, every muted stream whose process is in `app-distraction.slice` is unmuted, record or no record, through the same `cgroup.in_slice` test the scan uses (`slice_member` in ds/hold.py); streams outside the slice keep the record-only rule. A failed unmute joins `muted.json` and a failed listing keeps the sweep owed (`Mute.sweep`), both retried from `tick` every 16 seconds. Each mute, unmute, dropped record (`stream gone`, `identity changed`, `unmuted by hand`, `stream removed`), and failed `set-sink-input-mute` writes one `hold:` log line with the index, `pid:starttime`, and reason; a pactl outage still logs once per streak and a rescan that changes nothing writes nothing.

Tests (tests/test_audio.py): orphan released at hold end (R1, R3), start sweep with an outside-slice mute left alone (R1, R3), failed orphan unmute logged and retried (R1, R2), failed listing with no record retried from tick (R1), one line per mute and release (R2, R3), drop lines and a reused index swept like any other (R2), remove-event drop line (R2). README and docs/internals.md describe the sweep, the retry record, and the log lines. Implemented over the grok-4.6 bridge per the routing instruction, reviewed and corrected on this model.

baseline: green (463 tests OK before edit); verify: 469 tests OK, GREEN_RECEIPT 6be7537c-unittest

stage: impl-review - ran [round 1 fan-out x3 NEEDS_WORK (one deduped finding: a failed listing with nothing owned lost the sweep retry) .. round 2 SHIP]
## Evidence
- Commits: b8fd3416902355eddf76e3db5bbf4378b497bb20, 6be7537c5967675ec8d4b5f273704e1306558c7f
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, PATH=/usr/bin:$PATH python3 -m unittest tests.test_audio
- PRs: