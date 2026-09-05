# Type focus minutes directly

## Goal & Context
Replace the searchable duration preset list with native minutes entry, stacked on the v3 improvements and fn28 reason fix.

## Architecture & Data Models
Change only ds.ui.prompt_lock duration interaction. Use omarchy-menu-input immediately. No persistence or lock-engine changes.

## API Contracts
Enter positive whole minutes directly; allow whitespace. Zero explicitly means until manual unlock and maps to None at the UI boundary. Show a concise prompt with the configured default as an example and the zero meaning. Invalid configured defaults retain fallback 25. Do not change CLI numeric duration semantics. Purpose and return tuple remain as before.

## Edge Cases & Constraints
Empty/cancelled input aborts without asking purpose or changing lock state. Reject negative, fractional and nonnumeric input with existing invalid-duration notification, without proceeding. Preserve unavailable/timeout propagation and purpose opt-out/cancellation behavior. Omarchy has no supported prefilled-text API, so default is a visible example, not a fake prefill.

## Acceptance Criteria
- **R1:** Opening focus duration immediately accepts typed minutes with no preset/search list; positive minutes and zero-until-unlock work, with a clear native prompt.
- **R2:** Invalid/empty/cancelled duration cannot start a lock; purpose behavior and direct CLI semantics remain unchanged. Regressions cover arbitrary duration, zero, invalid values and native argv.
- **R3:** Focused and full suites pass, native helper smoke does not change lock state, Fable reviews the final implementation, and reviewed source is installed locally.

## Boundaries
One task for UI, tests and concise README wording. No custom native UI, new dependencies, version bump, push, main merge, release or marketplace edit.

## Decision Context
User wants direct entry instead of list search. Native input is supported already. Keep work on a separate branch atop fn28 and follow existing Fable Claude CLI review and local-install authorization.
