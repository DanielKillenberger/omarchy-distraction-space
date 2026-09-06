# Marketplace review: no agent instruction files, fixed root destinations

## Conversation Evidence

> user (turn 1): "check the issues that came up in the recent review from omarchy: https://github.com/omacom/omarchy-plugin-marketplace/issues/4518#issuecomment-5560990388"
> user (turn 2): "can we not have it tracked for when someone checks out the repo but packaged differently for the release?"
> user (turn 3): "but it doesn't say to move it but to remove it"

The reviewer's two findings at `bcfc76a` are quoted in the issue; the repository is what Omarchy clones and what the marketplace reviews, so the fix lands in the repository itself.

## Goal & Context
<!-- Source-tag breakdown: 40% [user] / 60% [paraphrase] -->

The marketplace reviewer blocks approval on two points. First, the installed checkout carries `AGENTS.md` and `CLAUDE.md`, which can change an agent's tool, approval, model, and repository-mutation behaviour merely because it works inside the plugin directory. Second, the privileged installer takes its root write destinations from environment variables, guards them only by rejecting a user-writable ancestor, and hands them to the sudo transaction, so a destination like `/etc/shadow` becomes an arbitrary privileged overwrite. [paraphrase] Both files are removed from the repository, and setup's destinations become fixed and are re-validated inside the root transaction. [paraphrase]

## Architecture & Data Models
<!-- Source-tag breakdown: 100% [paraphrase] -->

The two instruction files leave version control and are ignored, so they never enter a commit; development orchestration stays outside the repository Omarchy installs. The wrapper and sudoers destinations are module constants with no environment override reachable from the installed CLI. Before sudo, setup requires the destinations to equal those constants exactly; the root transaction script carries the same two canonical paths and refuses, before creating, staging, or renaming anything, any argument that is not exactly one of them. Tests that need sandbox destinations patch the module in-process and render the transaction from the patched constants, which the CLI environment cannot do. [paraphrase]

## Acceptance Criteria

- **R1:** `AGENTS.md` and `CLAUDE.md` are not tracked at any path and are listed in `.gitignore`; the README's contributing section says that agent instruction files are kept outside the repository. Errors: none beyond the ignore rule. [paraphrase]
- **R2:** No environment variable changes the wrapper or sudoers destination; `wrapper_dest()` and the sudoers destination return the canonical constants. Errors: a destination that differs from the constants, however it arose, stops setup before sudo with a refusal naming the path. [paraphrase]
- **R3:** The root transaction validates both argument paths against the canonical paths embedded in the script, before any create, stage, or rename, and exits non-zero with a refusal on mismatch; the pre-existing user-writable-ancestor check stays as defence in depth. Errors: a mismatch never touches the filesystem. [paraphrase]
- **R4:** Tests reach sandbox destinations only by patching the setup module in-process; every test that set `DS_WRAPPER_DEST` or `DS_SUDOERS_DEST` is converted, a test proves the CLI ignores those variables, and a test proves the transaction refuses a non-canonical path before writing. [inferred]

## Boundaries

- No change to what the wrapper or sudoers grant contain, or to the slice, entries, and clone steps of setup. [inferred]
- `.flow/` stays tracked; it is state and documentation, not agent instructions. [inferred]

## Decision Context

Exact-equality validation on both sides of the sudo boundary is the reviewer's own suggestion and removes the primitive rather than narrowing it. Removing the files, rather than moving them, follows the reviewer's wording and the user's reading of it. [paraphrase]

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.1 |
| R2 | fn-N.1 |
| R3 | fn-N.1 |
| R4 | fn-N.1 |
