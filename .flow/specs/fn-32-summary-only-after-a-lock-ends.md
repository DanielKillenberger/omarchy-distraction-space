# Summary only after a lock ends

## Conversation Evidence

> user (turn 1): "can you pls configure my dspace to only summarize notifications after focus unlock not always"

## Goal & Context
<!-- Source-tag breakdown: 60% [user] / 40% [inferred] -->

The "While you were away" notice fires at two boundaries today, when a lock ends and when the person enters the space, and there is no setting to pick one. [paraphrase] The person wants the notice only when a focus lock ends. [user] Entering the space still marks the boundary for the held count and the enter hook; only the notice is suppressed, because the person is about to see the apps themselves. [inferred]

## Architecture & Data Models
<!-- Source-tag breakdown: 100% [inferred] -->

One new config key under `summary`: `after`, either `"any"` (the default, today's behaviour) or `"unlock"`. The listener's enter boundary keeps claiming the held records and passing their counts to the enter hook, and starts the notice only when `after` is `any`. Both unlock paths, the listener's expiry and the manual `distractions unlock` command, are unchanged. Config validation rejects any other value. The settings menu is unchanged. [inferred]

## Acceptance Criteria

- **R1:** `summary.after` accepts `"any"` and `"unlock"`, defaults to `"any"` when absent, and any other value fails validation with the key named, like the other summary keys. [inferred]
- **R2:** With `after: "unlock"`, entering the space claims the held records, resets the held count, runs the enter hook with `DS_HELD` as today, and shows no notice. With `after: "any"`, behaviour is unchanged. Errors: no error surface beyond R1. [inferred]
- **R3:** With either value, a lock ending by expiry or by `distractions unlock` still claims and notifies as today. [inferred]
- **R4:** Tests cover R1 and R2, and the README config table documents the key. [inferred]

## Boundaries

- No change to the hold policy, the held-count display, or the unlock paths. [inferred]
- No new menu entry. [inferred]

## Decision Context

Suppressing only the notice on enter, rather than deferring the records to the next unlock, keeps the count and hooks consistent with today and avoids a summary that would later cover pings from before the lock began. [inferred]

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.M (TBD) |
| R2 | fn-N.M (TBD) |
| R3 | fn-N.M (TBD) |
| R4 | fn-N.M (TBD) |
