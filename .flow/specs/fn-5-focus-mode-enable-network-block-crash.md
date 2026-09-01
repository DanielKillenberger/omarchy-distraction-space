# Focus-mode enable network-block crash

> HTML render lens: [.flow/artifacts/fn-5-focus-mode-enable-network-block-crash/spec.html](../artifacts/fn-5-focus-mode-enable-network-block-crash/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "there was an error when enabling focus mode"
> user (turn 2): "/capture a fix in the repo and /work it directly and push"
> user (turn 3): "fn-1 is already done? why would we extend it? new spec."

## Goal & Context

<!-- Source-tag breakdown: 60% [paraphrase] / 40% [inferred] -->

Turning focus mode on failed with an error toast, and focus stayed off. The user asked to capture that fix as its own spec in the repo (not as an extension of the already-done network-block spec), then implement it directly and push.

## Architecture & Data Models

<!-- Source-tag breakdown: 100% [inferred] -->

Focus enable still applies the existing network block before it turns focus on. A failed apply must leave focus off and report a readable reason. The privilege helper that runs the block commands must treat command output as text whether the process emitted text or raw bytes, so a normal permission failure can continue to the next privilege attempt instead of aborting as a type error.

## API Contracts

<!-- Source-tag breakdown: 100% [inferred] -->

Privilege-run of a command: on failure, stderr/stdout is decoded as text. A missing nftables table is classified as missing-table. Other failures retry with the next privilege method, then surface a BlockError whose message includes the decoded detail. No new public commands.

## Edge Cases & Constraints

<!-- Source-tag breakdown: 100% [inferred] -->

- Unprivileged nft listing that returns bytes on stderr must not raise a type error. Errors: permission denied → retry pkexec then passwordless sudo; missing table → missing-table, not a crash; empty stderr → still a BlockError, not a type error.
- A genuine apply failure still leaves focus off and shows a user-visible reason. Errors: no error surface beyond the existing apply-failure path once decoding succeeds.

## Acceptance Criteria

- **R1:** Enabling focus mode must not fail with a type error caused by treating command output as the wrong string/bytes kind. [paraphrase]
- **R2:** A missing nftables table is still reported as a missing table, not as a type error. [inferred]
- **R3:** After decoding failure output as text, an unprivileged permission failure still retries the remaining privilege methods, then reports a readable BlockError. [inferred]
- **R4:** Automated tests cover failure output arriving as bytes (permission denied and missing table) and fail if those paths raise a type error. [inferred]

## Boundaries

- This spec does not re-specify the network-block feature itself (hosts, nftables, DNS sinkhole, destination list). That remains the already-done network-block spec. [paraphrase]
- Notification mute, grouped leave-notice, and plugin-owned app list are out of scope. [inferred]
- This spec does not change how the live desktop plugin is installed; the repo fix is the deliverable. [inferred]

## Decision Context

The original network-block spec is already done; the user rejected extending it and asked for a new spec. [paraphrase]

A type error while decoding privilege-command output is a helper bug, not a new product surface. Keep the spec to that crash and the tests that lock it. [inferred]

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.M (TBD — populate via /flow-next:plan) |
| R2 | fn-N.M (TBD — populate via /flow-next:plan) |
| R3 | fn-N.M (TBD — populate via /flow-next:plan) |
| R4 | fn-N.M (TBD — populate via /flow-next:plan) |
