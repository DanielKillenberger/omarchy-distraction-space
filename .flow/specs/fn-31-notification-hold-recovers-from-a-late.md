# Notification hold recovers from a late shell

> HTML render lens: [.flow/artifacts/fn-31-notification-hold-recovers-from-a-late/spec.html](../artifacts/fn-31-notification-hold-recovers-from-a-late/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "why is distraction space degraded?"
> user (turn 2): "what you mean a newer branch than this rep?"
> user (turn 3): "main is on v3 now no?"
> user (turn 4): "/flow-next:capture a fix for this?"
> user (turn 5): "i though we shipped fn-26 yesterday"
> user (edit cycle 1): "do we need the spec to be this long? cut the fat make it elegantly concise"

"This" is the assistant's diagnosis, accepted in turn 4: at login on 2026-09-06 the listener pushed its sender keys one second after omarchy-shell launched, the log recorded `hold: silencedSenders: omarchy-shell is not running`, the hold was marked unavailable, health read degraded, and the next attempt 60 seconds later succeeded. The fix is the assistant's proposal, so its substance carries `[inferred]`.

## Goal & Context
<!-- Source-tag breakdown: 30% [user] / 70% [inferred] -->

Every login shows the degraded dot for about a minute with nothing wrong. [paraphrase] The listener pushes its sender keys before the shell answers, records the hold as unavailable, and waits a full 60-second period to retry, so a one-second race costs a minute of false degraded state. [inferred] The one-time notice for that failure blames a missing shell feature and tells the person to run setup, which is wrong for a shell that is merely late. [inferred] The fix shortens the minute to seconds and reserves the notice for the shell that really lacks the feature. [inferred]

## Architecture & Data Models
<!-- Source-tag breakdown: 100% [inferred] -->

The hold module today collapses every push failure into one unavailable result. It gains one distinction, kept internal: a transport failure (the shell could not be reached, timed out, or the call failed) versus an answered failure (the shell replied with an error, a missing command, or an unparseable payload). Transport failures get a short bounded retry; answered failures keep the per-period retry and the notice. [inferred] An outage is one episode: the window opens at its first transport failure, is not extended by later ones, and closes on the first success or when it runs out. The existing per-period push stays the steady-state retry. [inferred] The state file's values, the status output, and the bar's file watch are unchanged; the existing state write already publishes a new hold observation or observation time. [inferred]

## Edge Cases & Constraints
<!-- Source-tag breakdown: 100% [inferred] -->

- A mid-session shell restart is a new episode with its own window. [inferred]
- A short retry re-runs only the shell push, never the sound-mute sync, which scans the audio server. [inferred]
- Each shell call blocks the listener for up to the IPC timeout, longer than the status ping allows; a hanging shell can make the listener look unresponsive for that long. Accepted and documented, not fixed here. [inferred]
- An "error" or empty answer during startup counts as answered; a wrong guess costs the per-period retry, which is today's behaviour. [inferred]

## Acceptance Criteria
<!-- scope: both -->

- **R1:** After a transport failure the listener retries the push every 2 seconds for a 10-second window measured from the episode's first failure, then returns to the per-period retry. Errors: an answered failure gets no window; later failures do not extend it; the per-period push does not reopen an exhausted one. [inferred]
- **R2:** A retry that succeeds records the hold at the value the current policy calls for, with a fresh observation time, and status reports the service healthy before the next period. Errors: overall health still depends on the listener ping and the other services, unchanged. [inferred]
- **R3:** The "Notification hold unavailable" notice fires once per listener lifetime and only for an answered failure. A transport failure writes one log line per attempt and no notice, even past the window. No error surface beyond that. [inferred]
- **R4:** The tests' fake shell gains modes for absent-then-answering, never-answering, and answering "error". Tests cover recovery inside the window with no notice and a published state change, exhaustion with no notice, the missing-feature notice firing exactly once, the "error" path with its notice, and a retired key whose removal failed being retried on the next push rather than forgotten. [inferred]

## Boundaries
<!-- scope: business -->

- fn-26's health model, state-file fields, status output, and bar widget stay as shipped; unavailable still means degraded. [inferred]
- The 60-second period for the other services, and the blocking shell call, are not touched. [inferred]

## Decision Context
<!-- scope: both -->

A bounded retry keeps the per-period push as the steady state, so a shell that is truly gone costs nothing beyond the window. [inferred] Rejected: waiting for the shell before the first push (the listener cannot know when, and a shell restart repeats the race) and reporting the transient as unknown (a new state for a condition that lasts seconds). [inferred] Two seconds fits the one-second tick with half the subprocess churn; ten seconds gives five attempts before the 60-second schedule resumes. [inferred] Reviewed before write by the configured codex gpt-6-astra backend, whose findings corrected the classification claim, R1 to R4, the mute coupling, the timeout bound, and the retry values.

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.M (TBD — populate via /flow-next:plan) |
| R2 | fn-N.M (TBD — populate via /flow-next:plan) |
| R3 | fn-N.M (TBD — populate via /flow-next:plan) |
| R4 | fn-N.M (TBD — populate via /flow-next:plan) |
