# Distraction streams start muted while the hold is on

## Conversation Evidence

> user (turn 1): "ok so why is notification sound on now from dspace?"
> user (turn 2): "ok /capture then review the spec with astra and implement with grok and do impl-review with astra and /make-pr."

The diagnosis is the assistant's, accepted in turn 2. The distraction Chrome no longer keeps one long-lived audio stream: each notification sound creates a stream, plays, and tears it down. The plugin mutes reactively, after a subscribe event and two pactl calls, so the first part of every short sound leaks. Two live facts shape the fix: WirePlumber keys its saved per-stream state on `application.id` first, then `application.name`, and the distraction browser's stream carried no `application.id` (WirePlumber keyed its saved state on the shared name "Google Chrome") even though the launcher puts one in the browser's environment. The fix is the assistant's proposal, so its substance carries `[inferred]`.

## Goal & Context
<!-- Source-tag breakdown: 30% [user] / 70% [inferred] -->

While the hold is on, no sound from the distraction browser should be audible, including a short notification ding. [paraphrase] Muting a stream after it appears cannot meet that for sounds shorter than the reaction time, so the mute has to be decided by the audio server at the moment the stream is created. [inferred] The browser's audio identity is the lever: its own `application.id` lets a WirePlumber hook recognise its streams before they play, separately from the work browser that shares the name "Google Chrome". [inferred]

## Architecture & Data Models
<!-- Source-tag breakdown: 100% [inferred] -->

**Identity.** The launcher already puts `application.id=io.github.danielkillenberger.distraction-space` on the browser's PipeWire property line, but the browser's streams do not carry it. The first step is finding where the identity is lost between the launch environment and the audio process, fixing it, and verifying it on a live stream. The identity is confined to launches into the slice: on both forwarding paths to the work browser the plugin's `application.id` is removed from the inherited property line, other properties preserved, so a cold work browser started through a forward never carries it. [inferred]

**Creation-time mute.** A WirePlumber Lua script, installed by `distractions setup` under the user's WirePlumber scripts directory with a config fragment that loads it, registers a hook on stream nodes being added whose `application.id` is the plugin's. For each such node it reads the plugin's hold flag, a file in the plugin's state directory that the listener creates when the hold starts and removes when it ends, and sets the node's mute property to match before the node is linked. Because the decision is made per stream from the flag, it works with zero existing streams, needs no WirePlumber restart to toggle, and overrides WirePlumber's saved per-identity state in both directions, so a stale saved mute never leaks onto the space. The one restart is WirePlumber's at setup, when the script is first installed; setup says so. [inferred]

**Listener side.** On hold start the listener writes the flag, then runs today's reactive scan for streams already playing; on hold end it removes the flag and releases as today, including the fn-33 slice sweep. On listener start while the hold is off, a stale flag is removed. The flag write and removal are logged with the fn-33 log lines. If the script is not installed, or WirePlumber does not report it loaded, the listener logs that once per streak and the reactive scan remains the only mute. Native listed apps keep the reactive path. [inferred]

## Edge Cases & Constraints
<!-- Source-tag breakdown: 100% [inferred] -->

- A browser started before this change carries no identity until it is relaunched; the reactive path covers it and the docs say so. [inferred]
- The work browser, which shares the application name, is never matched: the hook keys only on the plugin's `application.id`, and forwards strip it. [inferred]
- A listener that dies while the hold is on leaves the flag in place; the next listener start while the hold is off removes it, and the fn-33 start sweep unmutes any stream muted meanwhile. [inferred]
- Setup installs the script and fragment idempotently and removes them on `remove`; a WirePlumber that lacks user script loading is reported at setup and the feature degrades to the reactive path. [inferred]
- Whether a web app's stream carries the browser's identity on this PipeWire, and that the hook fires before the stream is audible, are verified live and recorded in the docs. [inferred]

## Acceptance Criteria

- **R1:** Every audio stream the distraction browser creates carries the plugin's `application.id`, verified on a live stream from a freshly launched browser. Errors: a browser launched through a path that cannot carry the identity is named in the docs and falls back to the reactive scan. [inferred]
- **R2:** While the hold flag is present, a new stream carrying that identity is muted by the WirePlumber hook before it is linked; while the flag is absent, the hook leaves it unmuted regardless of WirePlumber's saved state. Errors: a hook that cannot read the flag treats it as absent and logs nothing; the reactive scan still mutes. [inferred]
- **R3:** The listener writes the flag on hold start, removes it on hold end and on start while the hold is off, and logs each change; a missing or unloaded script is logged once per streak. Errors: a flag write failure is logged and the reactive scan still mutes. [inferred]
- **R4:** Toggling the hold needs no WirePlumber or browser restart; a live check records that a short sound started while the hold is on produced a stream whose first event already showed it muted. [inferred]
- **R5:** A forward to the work browser, on either forwarding path, never passes the plugin's `application.id`, with the rest of the inherited property line intact, verified by a test that launches a cold forwarded browser with the identity in its inherited environment. [inferred]
- **R6:** Tests cover the identity in the slice launch environment and its absence on forwards, the flag written and removed at the transitions through the fakes, the stale-flag removal at start, the once-per-streak log for a missing script, and the reactive fallback. The hook script itself is exercised by a Lua test where an interpreter exists, as the Hyprland fragments are. [inferred]

## Boundaries

- No change to what counts as a listed app, to the hold policy, or to the fn-33 slice sweep. [inferred]
- No muting keyed on the shared application name, and no WirePlumber rule that touches other applications. [inferred]

## Decision Context

A hook that decides mute at node creation removes the race entirely rather than shrinking it; a faster reactive loop would still lose the first milliseconds of every short sound. [inferred] Rejected: relying on WirePlumber's saved per-identity state alone, because it cannot be set while no stream exists and it would carry a stale mute onto the space; a PipeWire pulse rule, because it cannot read the hold state at creation. [inferred] The flag file keeps the hook stateless and the listener the single owner of the hold. [inferred]

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.M (TBD — populate via /flow-next:plan) |
| R2 | fn-N.M (TBD — populate via /flow-next:plan) |
| R3 | fn-N.M (TBD — populate via /flow-next:plan) |
| R4 | fn-N.M (TBD — populate via /flow-next:plan) |
| R5 | fn-N.M (TBD — populate via /flow-next:plan) |
| R6 | fn-N.M (TBD — populate via /flow-next:plan) |
