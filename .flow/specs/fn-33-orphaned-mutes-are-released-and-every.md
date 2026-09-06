# Orphaned mutes are released and every mute is logged

> HTML render lens: [.flow/artifacts/fn-33-orphaned-mutes-are-released-and-every/spec.html](../artifacts/fn-33-orphaned-mutes-are-released-and-every/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "is sound muted on dspaces?"
> user (turn 2): "but it's muted on x while i'm on dspace?"
> user (turn 3): "yes /capture that"

The diagnosis is the assistant's, accepted in turn 3. On 2026-09-06 the distraction Chrome's audio stream stayed muted while the person was on the space. The plugin's mute record file was absent, WirePlumber's saved state said Chrome was unmuted, and the listener running at the time had started after the mute was applied. The listener never claims a stream it did not mute itself, so nothing ever released it. The plugin logs no mute or unmute action, so the exact step that lost the record could not be reconstructed. The fix is the assistant's proposal, so its substance carries `[inferred]`.

## Goal & Context
<!-- Source-tag breakdown: 30% [user] / 70% [inferred] -->

Sound from a listed app must not stay muted while the person is on the space. [paraphrase] Today a mute that outlives its record, for instance across a listener stop and start, is never released because the plugin only unmutes what its record names, a rule that exists to protect the person's own mutes. [inferred] A muted stream whose process is inside the distraction slice, seen while the hold is off, is far more likely an orphan than a choice, and the plugin has enough information to tell the two apart. [inferred] Without a log of mute actions, an orphan cannot be traced after the fact. [inferred]

## Architecture & Data Models
<!-- Source-tag breakdown: 100% [inferred] -->

The mute module keeps its record of owned streams and its identity check as today. It gains two behaviours. First, every mute, unmute, dropped record, and failed pactl call writes one line to the plugin log naming the stream index, the process identity, and the reason. Second, when the hold ends, and on the listener's start while the hold is off, the release pass also unmutes any muted stream whose process sits inside the distraction slice, whether or not the record names it; streams outside the slice keep today's record-only rule, so a mute the person set on a work app is never touched. [inferred]

## Edge Cases & Constraints
<!-- Source-tag breakdown: 100% [inferred] -->

- A person who deliberately muted a distraction stream on the space loses that mute at the next hold end; accepted, because that stream is by construction the plugin's to mute and the alternative is the reported bug. [inferred]
- The slice check reuses the cgroup test the plugin already applies when it decides what to mute, so the two sides agree on membership. [inferred]
- A listener that stops while the hold is on still releases on exit as today; the slice sweep covers the case where that release did not happen. [inferred]
- Log lines are bounded to one per action; a rescan that changes nothing writes nothing. [inferred]

## Acceptance Criteria

- **R1:** When the hold ends, and once at listener start while the hold is off, every muted audio stream whose process is inside the distraction slice is unmuted, record or no record. Errors: a pactl failure leaves the stream for the next retry and writes one log line; streams outside the slice follow today's record-only rule unchanged. [inferred]
- **R2:** Each mute, unmute, dropped record, and failed pactl call writes one log line with the stream index, the process identity, and the reason. Errors: a rescan that changes nothing writes nothing; log write failures are ignored as today. [inferred]
- **R3:** Tests cover an orphaned slice mute released at hold end and at listener start, a muted stream outside the slice left alone, and the log lines for a mute and its release. No error surface beyond the paths named. [inferred]

## Boundaries

- No change to what gets muted, when the hold applies, or the identity check for recorded streams. [inferred]
- No adoption of orphaned mutes outside the slice. [inferred]

## Decision Context

Sweeping the slice at release time fixes the orphan without weakening the promise that the plugin never touches a mute outside its own boundary; the slice is that boundary. [inferred] Rejected: claiming every pre-muted slice stream into the record at start (same effect with more state), and logging alone (diagnosable but still stuck). [inferred] Prior art in memory: the earlier release bug where a failed unmute was forgotten rather than retried. [inferred]

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.M (TBD — populate via /flow-next:plan) |
| R2 | fn-N.M (TBD — populate via /flow-next:plan) |
| R3 | fn-N.M (TBD — populate via /flow-next:plan) |
