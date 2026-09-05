# Room for the early-leave reason

## Goal & Context
The user reports that the native early-leave reason screen is too narrow to read a useful reason and requests a quick new spec on top of the v3 release work. Keep the native Omarchy input experience.

## Architecture & Data Models
Use the native input command's existing width option for the reason prompt only. Request 900 logical units; Omarchy scales and clamps the card to available screen width. Ordinary short inputs retain their defaults. No persisted data changes.

## API Contracts
Extend the internal input helper with an optional keyword-only width. Omit the CLI option unless requested. Preserve UTF-8 reason text, trailing newline handling, cancellation, timeout and unavailable-command behavior. The lock engine remains responsible for minimum-length validation and unlocking.

## Edge Cases & Constraints
Native input is single-line and elides very long text. This bounded fix provides more room for ordinary reasons; multiline editing and dynamic typing-driven growth require native Omarchy support and are outside scope. Do not edit packaged Omarchy files or clone its menu. Keep the existing minimum-length requirement and refusal behavior.

## Acceptance Criteria
- **R1:** Early-leave reason entry uses native input with width 900; Omarchy retains screen-edge clamping. Other input prompts omit width and remain unchanged. No error surface beyond existing native command failures.
- **R2:** Long UTF-8 reasons return intact; cancellation, timeout and unavailable input retain existing behavior, and insufficient reasons do not unlock. No automatic lock changes during visual validation.
- **R3:** Focused regression tests pass, a native prompt smoke check records actual behavior/limitations, and the change is reviewed on top of the completed v3 improvements. No push, main merge, release or marketplace update.

## Boundaries
One small UI change, tests and concise documentation. No custom input screen, Omarchy source edits, new dependencies, or version bump.

## Decision Context
The installed native command accepts --width, and its menu clamps scaled width to panel width minus outer gaps. A wider native input is the smallest supported correction. The existing v3 installation remains the base; local installation of the reviewed fix follows the user's already authorized local workflow.
