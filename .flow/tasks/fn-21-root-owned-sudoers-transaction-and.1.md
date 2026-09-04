---
satisfies: [R1, R2, R3, R4, R5, R6, R7]
---
# fn-21-root-owned-sudoers-transaction-and.1 Implement Root-owned sudoers transaction and bounded reads

## Description
TBD

## Acceptance
Every R-ID in the parent spec's ## Acceptance Criteria is satisfied; judge this task against the spec's criteria directly.

## Done summary
R1 through R6 of fn-21 are implemented in one commit: the sudoers grant is now validated and activated inside a single root-owned, descriptor-pinned transaction, and every read a granted account can grow is bounded. R7 (the marketplace issue edit and reply) is deliberately not done here — the conductor and the human own the push, the issue edit, and the reply.

**R1, the escalation window.** `distractions setup` no longer writes a user-owned temp file for root to re-open. All privileged work is one `sudo python3 -c` invocation that receives the wrapper bytes and the rendered grant on stdin behind a small framed header. Inside root the grant is staged with `mkstemp` in `/etc/sudoers.d` itself — root-only in a real install, and under a dotted name sudo's `#includedir` skips while it waits — held open by descriptor, fsynced, set to 0440, and checked with `visudo -cf` on that same path. Root then revalidates through the held descriptor immediately before activating: inode identity against `lstat`, link count 1, ownership, mode, and a byte-for-byte re-read of what visudo accepted. Only then does it `os.rename` into place. The grant is staged and validated first, so a rejected grant aborts before anything has moved and any prior grant stays live; the wrapper lands before the grant that names it.

**R2, the wrapper source.** The unprivileged half opens the shipped `distractions-nft` once with `O_NOFOLLOW | O_NONBLOCK`, refuses a symlink, a fifo, or anything not a regular file, and sends those exact bytes. Root installs content, not a pathname, so the user-writable plugin directory is never re-resolved.

**R3, one prompt.** The two `sudo` invocations collapsed into one, so setup asks for a password once and cannot regress into prompting twice. A re-run whose bytes already match renames nothing and revalidates nothing: root compares in place and returns. Pinned by `test_install_idempotent_and_rescan_last`, which asserts exactly one sudo invocation for a fresh install and unchanged destination inodes on the re-run.

**R4, the privileged helper.** `sys.stdin.read()` is gone. Both argv forms read at most `MAX_STDIN_BYTES + 1` (256 KiB) and refuse over the cap before decoding; `parse_replace_stdin` refuses past `MAX_ADDRESSES` (4096) while parsing, so neither the lists, the rendered ruleset, nor any nft commit grows with what the caller sent. The two argv forms and the address grammar are unchanged.

**R5, the bounded reads.** `state.read_bounded` opens non-blocking, rejects a non-regular target with `fstat` before a byte is read, and stops at 1 MiB; `read_json` and therefore every state read comes through it. `summary.take()` reads the claimed hold file through an `O_NOFOLLOW | O_NONBLOCK` descriptor, rejects a non-regular claim, and truncates at the last newline inside a 4 MiB cap so every surviving record is whole. The bar's parked unknown resolved against the installed Quickshell API: `FileView` exposes no size or regular-file bound, so the widget now watches the state path and never materializes it — the read goes through `distractions status --json`, which is bounded in Python, with a pending-refresh flag so a change landing mid-read is not lost.

**R6, the suite.** 290 tests pass (276 at baseline, 14 added). New coverage: the file visudo validated is the same inode with the same bytes that gets renamed into place; a rejected grant moves nothing and leaves a prior grant intact; the pinned source refuses a symlink, a fifo, and a missing file; install refuses a non-regular source before any sudo; the caps refuse a byte over and accept exactly at; an oversized claim returns only whole records; a fifo state path neither blocks nor is read. The fake `sudo` now executes the real root-side transaction against real destinations rather than emulating an `install` protocol, so the transaction itself is under test.

`docs/marketplace-submission.md` described the replaced `sudo sh -c 'cmp || install'` mechanism verbatim, including line-number citations. It is rewritten to the transaction that now exists — that doc is what the reviewer reads, so leaving it would have been the drift the fix is meant to end.

Follow-ups, not built: the sudoers destination could carry a root-written fingerprint so a re-run could skip the transaction entirely rather than prompting once; and `distractions status --json` spawns `hyprctl` per bar refresh, which is fine at state-change frequency but is the obvious thing to trim if the bar ever gets chattier.

stage: impl-review - skipped(policy: host-deferred - conductor owns the gate)

### Review (conductor-run, cursor / gpt-5.6-sol-high)

Round 1 returned NEEDS_WORK on two introduced P2 findings, both valid:

- **R3 was not met.** The transaction made reaching sudo cheap, not unnecessary: an unchanged re-run still invoked it, so an expired sudo timestamp still prompted. Root now writes `.installed.sha256` (0444) beside the wrapper holding the digests of the wrapper and the grant it installed, and the unprivileged half compares that record plus the installed wrapper's own bytes before invoking sudo at all. The grant is never read unprivileged; it is 0440 in a directory the account cannot traverse, which is the reason the record exists. Documented gap: a grant edited behind `/etc/sudoers.d` is invisible to the pre-check, and the repair is `setup --remove` then `setup`.
- **`read_bounded` did not hold its boundary.** It followed symlinks and returned exactly `cap` bytes of a larger file, so JSON followed by padding parsed as a whole state file. It now opens with `O_NOFOLLOW` and refuses one byte over the cap instead of truncating.

Tests added for both: symlink refusal, exactly-cap versus one-over, valid-JSON-plus-padding refusal, a zero-sudo matching re-run, and a drifted-record re-install. `test_rejected_grant_leaves_the_prior_grant_intact` now drops the record before its re-run, because an out-of-band grant edit is invisible to the pre-check by construction and that test is about the transaction.

`README.md` and `docs/marketplace-submission.md` gained the record file, and the submission doc's stale `install -D` / `ds/setup.py:60 to 71` citation is now the transaction it actually describes.

Round 2 returned SHIP with no surviving findings. Full suite green at 293 tests.

### Stage outcomes

stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: f116af0f7d69fe3da803d29a6bdac82cf60ff96c, 9eecae5
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (baseline green, 276 tests), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify green, 290 tests), PATH=/usr/bin:$PATH python3 -m unittest tests.test_setup (13 tests, OK), PATH=/usr/bin:$PATH python3 -m unittest tests.test_nft (9 tests, OK), PATH=/usr/bin:$PATH python3 -m unittest tests.test_summary (11 tests, OK), PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (post-review-fix green, 293 tests), PATH=/usr/bin:$PATH python3 -m unittest tests.test_setup tests.test_status (33 tests, OK)
- PRs: