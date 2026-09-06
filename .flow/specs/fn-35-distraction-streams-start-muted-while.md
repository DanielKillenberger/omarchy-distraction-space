# Distraction streams start muted while the hold is on

## Conversation Evidence

> user (turn 1): "ok so why is notification sound on now from dspace?"
> user (turn 2): "ok /capture then review the spec with astra and implement with grok and do impl-review with astra and /make-pr."

The diagnosis is the assistant's, accepted in turn 2. The distraction Chrome no longer keeps one long-lived audio stream: each notification sound creates a stream, plays, and tears it down. The plugin mutes reactively, after a subscribe event and two pactl calls, so the first part of every short sound leaks. Two live facts shape the fix: WirePlumber keys its saved per-stream state on `application.id` first, then `application.name`, and the distraction browser's stream carried no `application.id` (WirePlumber keyed its saved state on the shared name "Google Chrome") even though the launcher puts one in the browser's environment. The fix is the assistant's proposal, so its substance carries `[inferred]`.

## Goal & Context
<!-- Source-tag breakdown: 30% [user] / 70% [inferred] -->

While the hold is on, no sound from the distraction browser should be audible, including a short notification ding. [paraphrase] Muting a stream after it appears cannot meet that for sounds shorter than the reaction time, so the mute has to be in place when the stream is created. [inferred] The browser's audio identity is the lever: with its own `application.id`, its streams get their own saved state in WirePlumber, separate from the work browser that shares the name "Google Chrome", and a mute pinned to that identity applies to every new stream at creation. [inferred]

## Architecture & Data Models
<!-- Source-tag breakdown: 100% [inferred] -->

The launcher already stamps the distraction browser with `application.id` on the PipeWire property line, but the browser's streams do not carry it, so the first step is finding where the identity is lost between the launch environment and the audio process, fixing that, and verifying it on a live stream. [inferred] The hold then owns that identity: on hold start the plugin puts the identity into the muted state, on hold end it takes it out, and the audio server applies the state to each stream as it is created, so no stream is ever audible before the plugin reacts. The exact mechanism, WirePlumber's per-identity saved state or a PipeWire stream rule, is chosen during planning and must be one that takes effect without restarting the browser or the audio server. [inferred] The reactive scan stays as the path for native listed apps and as the fallback for a stream that carries no identity. [inferred] The slice sweep from fn-33 is unchanged. [inferred]

## Edge Cases & Constraints
<!-- Source-tag breakdown: 100% [inferred] -->

- A browser started before this change carries no identity until it is relaunched; the reactive path covers it and the docs say so. [inferred]
- The work browser, which shares the application name, must never be affected; the identity is the only key the pinned mute uses. [inferred]
- A listener that dies while the hold is on leaves the identity muted; the fn-33 start sweep plus the hold-off path on the next start release it. [inferred]
- Whether a web app's stream carries the browser's identity on this PipeWire is verified live, not assumed, and the result is recorded in the docs. [inferred]

## Acceptance Criteria

- **R1:** Every audio stream the distraction browser creates carries the plugin's `application.id`, verified on a live stream from a freshly launched browser. Errors: a browser launched through a path that cannot carry the identity is named in the docs and falls back to the reactive scan. [inferred]
- **R2:** While the hold is on, a new stream carrying that identity is muted at creation, before any audio is rendered; when the hold ends, new streams of that identity play, and any existing one is unmuted. Errors: the mechanism failing to apply is logged once per streak and the reactive scan still mutes; nothing is written for the work browser's identity. [inferred]
- **R3:** The change takes effect without restarting the browser or the audio server, and a live check records that a short sound started while the hold is on produced a stream that was already muted at its first event. [inferred]
- **R4:** Tests cover the identity reaching the launch environment, the pinned mute set on hold start and cleared on hold end through the fake, and the reactive fallback for a stream without identity. [inferred]

## Boundaries

- No change to what counts as a listed app, to the hold policy, or to the fn-33 slice sweep. [inferred]
- No muting keyed on the shared application name. [inferred]

## Decision Context

Pinning the mute to an identity the audio server applies at creation removes the race entirely rather than shrinking it; a faster reactive loop would still lose the first milliseconds of every short sound. [inferred] The identity already exists in the launcher, so the change is making it stick and using it. [inferred]

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.M (TBD — populate via /flow-next:plan) |
| R2 | fn-N.M (TBD — populate via /flow-next:plan) |
| R3 | fn-N.M (TBD — populate via /flow-next:plan) |
| R4 | fn-N.M (TBD — populate via /flow-next:plan) |
