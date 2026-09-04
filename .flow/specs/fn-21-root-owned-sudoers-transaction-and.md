# Root-owned sudoers transaction and bounded reads

> HTML render lens: [.flow/artifacts/fn-21-root-owned-sudoers-transaction-and/spec.html](../artifacts/fn-21-root-owned-sudoers-transaction-and/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "can you check the omarch plugin application and check the hancore-linux comment which requires fixes"

External evidence, quoted verbatim from the marketplace listing issue `omacom/omarchy-plugin-marketplace#4518` (fetched this session, 2026-09-04). Not user turns; recorded here so every criterion below is traceable to its source.

> reviewer HANCORE-linux (2026-09-03, part 1): "Full review of exact current/validated/baseline commit `1c3fa253b438da6913231b922b19990ea7c0c417` is blocked. The sudoers fragment is written and validated as the unprivileged user, then later re-opened by pathname inside a separate `sudo install` (`ds/setup.py:372-399`, via `:60-71`). A same-UID process can modify that predictable `/tmp/ds-sudoers.*` file after `visudo` returns but before the root copy opens it, causing unvalidated sudoers content to be installed."

> reviewer HANCORE-linux (2026-09-03, part 2): "Validation and activation must be one root-owned, descriptor-pinned transaction with immediate revalidation before atomic rename; apply the same no-follow/pinned-source treatment to the wrapper copy."

> reviewer HANCORE-linux (2026-09-03, part 3): "The resulting NOPASSWD helper also performs an unbounded root `sys.stdin.read()` and builds an unbounded nft ruleset (`distractions-nft:83-126`), allowing the granted account to exhaust privileged userspace/kernel resources; impose a strict byte/address cap before allocation/commit."

> reviewer HANCORE-linux (2026-09-03, part 4): "Finally, the bar's long-lived `FileView` watches and materializes the predictable mutable state path without a regular-file/owner/no-follow/size boundary (`BarWidget.qml:12-16,42-70`), and held summaries similarly consume the entire claimed JSONL file (`ds/summary.py:92-130`); bound these reads before they reach the shell/listener. Then revalidate."

> issue state (2026-09-04): labels `submission`, `validated`, `needs-fixes`, `security-needs-fixes`, `security-review-required`; automated validation and the security baseline both passed at `1c3fa25` with no findings.

## Goal & Context

<!-- Goal & Context: 20% [user], 80% [paraphrase] -->

The plugin's marketplace listing is blocked. A maintainer reviewing the capability disposition stopped the review and named four places where the plugin's own privilege and input boundaries are weaker than the surrounding design claims. Closing them earns the listing, and it closes a real local-escalation window on the author's machine today: the sudoers drop-in that grants passwordless root to the nft wrapper is installed through a validate-then-reopen sequence another process running as the same user can win.

Three of the four findings are resource bounds rather than escalation. They matter because the account that holds the NOPASSWD grant can drive a root process into unbounded allocation, and because the Quickshell bar is a long-lived shell process that currently materializes whatever the state path holds.

## Architecture & Data Models

<!-- Architecture & Data Models: 100% [paraphrase] -->

Four surfaces change; each was read and confirmed in this session at commit `1c3fa25`.

**The setup transaction.** `distractions setup` renders the sudoers grant for the invoking user, writes it to a user-owned temporary file, validates that file with `visudo -cf`, and then hands the pathname to a `sudo` helper that re-opens it and copies it to `/etc/sudoers.d/omarchy-distraction-space`. Root resolves the name a second time, after validation returned, so the bytes root installs are not provably the bytes visudo accepted. The wrapper install has the matching weakness on its source side: root copies `distractions-nft` out of the user-writable plugin directory by pathname.

**The privileged helper.** The wrapper accepts exactly `replace ds` and `flush ds`, reads addresses from standard input, and commits one fixed nft table. Every address is validated with `ipaddress.ip_address`, so the ruleset shape is already confined. The count is not: the read, the parsed lists, the rendered script, and the committed sets all grow with whatever the caller sends.

**The bar's state watcher.** The widget resolves the state path from `XDG_STATE_HOME` and holds a watching `FileView` on it for the life of the shell, parsing whatever it loads as JSON.

**The held-summary claim.** Summary take renames `held.jsonl` to a private claim file, which is the correct claim mechanism, then reads the whole claimed file before any per-record filtering runs.

## API Contracts

<!-- API Contracts: 30% [paraphrase], 70% [inferred] -->

The privileged wrapper keeps its two argv forms and its address grammar. Two caps join the contract:

- `replace ds` reads at most a fixed byte budget from standard input and refuses beyond it, before parsing and before any allocation proportional to input size.
- `replace ds` accepts at most a fixed number of addresses and refuses beyond it, before the ruleset is rendered or committed.

A refusal exits non-zero with a one-line reason on standard error and commits nothing, matching the wrapper's existing refusal shape (`refused: <reason>`). The caps are the wrapper's own contract, so the listener needs no change to stay within them.

## Edge Cases & Constraints

<!-- Edge Cases & Constraints: 60% [paraphrase], 40% [inferred] -->

- The setup transaction must stay one interactive `sudo` prompt. A fix that prompts twice trades a security win for a usability regression the earlier privilege work deliberately avoided.
- A denied, cancelled, or non-TTY `sudo` still fails closed and leaves no half-installed grant, which is existing behavior the change preserves.
- Re-running setup when the wrapper and grant already match still skips the prompt.
- The bar renders its empty state when the state file is irregular, oversized, or unreadable, rather than blocking or crashing the shell.
- A claimed hold file over the cap is truncated at the record boundary and the summary reports on what it read, since the claim already removed the file and the records cannot be re-read.
- `main` is frozen at the validated commit `1c3fa25` until the fix lands, because marketplace validation binds to the exact HEAD at filing.

## Acceptance Criteria

- **R1:** The sudoers grant is validated and activated inside a single root-owned transaction whose destination is never re-resolved by pathname after validation. Root writes the rendered grant to a file only root can modify, validates that same file, and moves it into place atomically. A process running as the installing user cannot substitute content between validation and activation. Errors: visudo rejects the rendered grant, the transaction aborts and any prior grant stays intact; `sudo` denied, cancelled, or non-TTY, nothing is written. [paraphrase]
- **R2:** The wrapper install reads its source through a pinned descriptor that refuses a symlink or a non-regular file, so the bytes root installs to the wrapper path are the bytes that were checked. Errors: source is a symlink, a non-regular file, or unreadable, the install refuses and the run fails closed. [paraphrase]
- **R3:** Setup completes with exactly one interactive `sudo` prompt, and a re-run whose wrapper bytes and grant already match still prompts zero times. Errors: no error surface beyond R1 and R2. [paraphrase]
- **R4:** The privileged wrapper refuses standard input over a fixed byte cap and an address set over a fixed count cap, in both cases before allocating or rendering proportional to the input and before any nft commit. Errors: over either cap, exit non-zero with a `refused:` line and commit nothing; `flush` with non-whitespace input keeps its existing refusal. [paraphrase], caps chosen [inferred]
- **R5:** The bar's state watcher and the held-summary claim read both bound what they materialize. Each rejects a non-regular file and stops at a size cap. Errors: irregular, oversized, or unreadable state leaves the widget in its empty state and logs nothing to the user; an oversized claim file is read up to the cap at a record boundary and the summary reports on what it read. [paraphrase], mechanism [inferred]
- **R6:** The unit suite covers each new refusal path, and the full suite passes. Errors: no error surface beyond the criteria above. [inferred]
- **R7:** After the fix lands on `main`, the listing issue is edited to point at the new commit so validation and the security baseline re-run, and a reply maps each of the four review points to the change that answers it. Errors: revalidation reports a new finding, the reply waits until that finding is answered too. [inferred]

## Boundaries

- The blocking behavior, the site list, the banner path, and the summary content stay as they are. This spec changes how bytes are validated and how much is read, not what the plugin does. [paraphrase]
- The automated baseline's citations of `.flow/` planning files are not addressed here. They are scanner noise already answered in the issue's maintainer note, and deleting task records to quiet a scanner would cost more than it buys. [paraphrase]
- Filing or arguing the listing decision is not in scope. The spec ends at a revalidated issue and a posted reply. [inferred]
- No new dependency, no new privileged command, and no widening of the single-line sudoers policy. [paraphrase]

## Decision Context

The reviewer named the required shape for the sudoers finding rather than leaving it open, so the design question is settled before implementation starts: one root-owned, descriptor-pinned transaction with revalidation immediately before an atomic rename. Rejected alternatives are the ones the current code represents, a user-side temporary file plus a root copy by pathname, and a narrower fix that only tightens the temporary file's permissions, which leaves the same-UID window open because the file is owned by the account that would attack it.

The other three findings are ordered behind it deliberately. The sudoers path is the only one that crosses a privilege boundary; the caps close resource-exhaustion surfaces that the granted account already reaches, at lower severity and far lower design risk.

## Parked unknowns

- Whether Quickshell's `FileView` can express a size or regular-file bound directly, or whether the bar has to reach the state through a bounded reader instead. Resolved by reading the `FileView` API surface in the installed Quickshell version against what the widget needs.
- The concrete cap values for the wrapper's input and for the two bounded reads. Resolved by measuring the real sizes the listener and the hold file produce in normal use and setting each cap above that with headroom.

## Requirement coverage

| R-ID | Tasks |
|------|-------|
| R1 | fn-N.M (TBD — populate via /flow-next:plan) |
| R2 | fn-N.M (TBD — populate via /flow-next:plan) |
| R3 | fn-N.M (TBD — populate via /flow-next:plan) |
| R4 | fn-N.M (TBD — populate via /flow-next:plan) |
| R5 | fn-N.M (TBD — populate via /flow-next:plan) |
| R6 | fn-N.M (TBD — populate via /flow-next:plan) |
| R7 | fn-N.M (TBD — populate via /flow-next:plan) |
