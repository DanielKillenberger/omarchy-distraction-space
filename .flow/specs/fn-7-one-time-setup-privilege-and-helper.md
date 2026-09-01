# One-time setup privilege and helper resilience

> HTML render lens: [.flow/artifacts/fn-7-one-time-setup-privilege-and-helper/spec.html](../artifacts/fn-7-one-time-setup-privilege-and-helper/spec.html) — regenerable, markdown is the record. <!-- flow-next:artifact-link -->

## Conversation Evidence

> user (turn 1): "so fn-4 is done right? We capture a spec to fix these quality issues? Add to that that we should have to allow sudo one time only during setup only and not for every single thing that has to happen one by one.."
> user (turn 2): "you can merge it directly if it's ready"

## Overview

The user approves sudo once at setup. That writes the constrained site-block helper and a passwordless grant for that path only. After that, list save, reload, placement, and site-block apply/lift never ask again.

The listener and its network worker stay up when one job, window event, overlapping reload, or notify send fails.

## Goal & Context

<!-- scope: business -->

fn-4 shipped the plugin-owned distraction list, always-on off-space site block, and listener-owned reload. A quality pass then found helper-resilience gaps: a failed network job can kill the worker, a failed window query or move can kill the listener, overlapping reloads can race shared state, and a notification send that raises an OS error can stop enforcement.

Privileged setup still asks sudo once per file. The user should approve sudo once during setup.

## Architecture & Data Models

<!-- scope: technical -->

Setup is one helper command. It asks for sudo once, installs the existing constrained helper and the uid-only passwordless grant for that path, and is the only interactive privilege moment. Runtime never calls the focus-mode privilege ladder (bare / pkexec / sudo -n). That ladder can open a GUI prompt.

Runtime stays unprivileged. The listener owns list reload, placement, and site-block apply/lift through the already-installed helper with non-interactive sudo only.

The existing notification-rescan command stays notification-rescan. Setup is a separate entry.

The network worker keeps accepting jobs after one `_run` exception. Socket2 query or move failures skip that event. Reloads take one in-process lock so last-good, pending, and expand writes do not interleave. Notify failures stay absorbed.

## API Contracts

<!-- scope: technical -->

- Setup command: one entry point. Success means the privileged helper is installed and later runtime calls need no further sudo. Failure means no this-run leftover grant and no half-written sudoers file that would prompt or lock out later commands. An older grant is kept only when its dest and ancestors are still trusted. An existing grant whose dest or ancestors are missing or untrusted is disabled before repair or exit. The user can re-run setup.
- Runtime site-block apply/lift: same constrained helper invocation as today, non-interactive. Missing or broken install is a skip-with-notify. Window placement still runs. The skip body stays the current unavailable-install wording.
- Reload: the editor still only requests reload. The listener applies and replies success or failure after this generation's placement and site-block mutation, or reports that the listener is dead.

## Edge Cases & Constraints

<!-- scope: technical -->

- Setup cancelled, denied, or interrupted after this run created a wrapper and before the grant: remove only artifacts this run created. Keep an older grant only after dest and ancestors are still trusted. If an existing grant targets a missing or untrusted path, the one sudo disables that grant before any dest write. Repairable case: trusted ancestors, dest missing or byte/metadata mismatch. Unsafe-ancestor case: disable the grant and fail with no active grant. Denied sudo cannot remove a root-owned grant; the message says the unsafe grant remains until a later successful setup.
- Setup pins dest and every ancestor with no-follow directory descriptors before any wrapper write. Missing dest directories (the usual clean-install case, including `/usr/local/libexec/omarchy-distraction-space`) are created through the nearest existing pinned parent. Each new directory is pinned and checked root-owned and non-user-writable before the next create or the wrapper stage. Each existing component must be a root-owned, non-user-writable directory (dest is a regular file after replace). Reject any symlink, non-directory ancestor, or user-writable/non-root-owned ancestor. Then stage a root-owned regular file next to dest through the pinned parent, verify bytes, atomically replace dest, reverify on the pinned descriptors, and revalidate from the filesystem root. Grant is committed only after that final verify. A grant for a missing, mismatched, or untrusted path is never committed.
- Interrupted replace leaves the previous dest wrapper unchanged. A symlink dest or ancestor is rejected without following it, so the symlink target is not overwritten. Immediately before grant commit, walk again from the filesystem root with no-follow and compare each component's device, inode, and metadata with the pinned chain, including the final wrapper. Any mismatch fails closed without a grant.
- Setup install of sudoers is visudo-safe. Stage a root-owned grant on the same filesystem, validate with visudo, then atomically rename into place. An interrupt before that rename leaves the previous grant file unchanged. A broken or truncated sudoers.d fragment must not become the active file or lock out all sudo.
- Setup re-run: skip the sudo prompt when the installed wrapper bytes, pinned trusted-path checks, and this-uid grant already match. A trusted-path dest mismatch is one-sudo repair (pin, replace, revalidate, refresh grant). An untrusted ancestor is disable-then-fail, not dest repair.
- The grant principal is this process uid's account name from the account database, not `LOGNAME` or `USER`. Reject empty, `ALL`, `%` group forms, and leftover `__INSTALL_USER__`.
- Non-TTY setup fails closed with a message. It does not open a GUI privilege prompt.
- Two setup runs at once share one root-owned lock so wrapper and grant stay one transaction. The loser waits or fails closed without writing a grant for the other run's wrapper.
- A network job that throws: the worker records failure for that generation, stays started, and accepts later jobs.
- A single window event that throws: that event is skipped or notified. The listen loop and reload socket stay up.
- Two reload requests at once: the second waits for the first's full transaction. Shared rule, generation, network wait, and last-good writes do not interleave. A failed reload leaves a consistent last-good.
- Notification sender missing, nonzero, or any OS error: absorbed. Enforcement continues.

## Approach

- Harden the existing `setup` / `setup_privileged_helper()` path. Replace the current `sudo bash -c install...` transaction. Do not add a second setup entry. Do not fold nft install into notification rescan.
- Reuse the shipped wrapper binary and the shipped sudoers template. Do not invent a second grant path. Create any missing dest directories through the nearest pinned parent, then pin dest and every ancestor with no-follow directory descriptors before wrapper write. Stage, verify, atomically replace, reverify, revalidate from the filesystem root, then commit the grant by same-filesystem visudo-validated atomic rename.
- Keep `sudo -n` plus skip-with-notify for runtime apply/lift.
- Wrap worker `_run` so the thread stays in its loop and `started` remains a live acceptor.
- Serialize the full `handle_reload_conn` transaction with an in-process lock: load state, bump generation, apply rules, network enqueue and wait, determine the result. Do not lock only `apply_enforcement`. Do not reuse the listen singleton lock.
- Wrap socket2 query and move so one `CalledProcessError`, `JSONDecodeError`, or `OSError` (including `FileNotFoundError` and `PermissionError`) cannot exit `listen()`.
- Lock R6 with an OSError notify test. `notify()` already absorbs that class.

## Quick commands

```bash
python3 -m unittest discover -s tests
```

## Acceptance Criteria

<!-- scope: both -->

- **R1:** Privileged install is one setup action that requests sudo once. Errors: user denies, cancels, or interrupts → setup fails closed with a clear message and removes only artifacts this run created; an older grant is kept only when dest and ancestors are still trusted; an existing grant for a missing or untrusted path is disabled before dest write, then repaired or left with no active grant; denied sudo cannot remove a root-owned grant and the message says so; sudoers is never committed for a missing, mismatched, or untrusted wrapper; dest or any ancestor that is a symlink or user-writable is rejected before any dest write; path components stay pinned on no-follow directory descriptors through grant commit; a fresh no-follow walk from the filesystem root must match the pinned device/inode/metadata chain immediately before grant commit or the grant is not written; missing dest directories are created through the nearest pinned parent and pinned before the wrapper stage; an interrupted wrapper replace leaves the previous wrapper in place; sudoers is staged, visudo-validated, and atomically renamed, so an interrupt leaves the previous grant file; a broken sudoers fragment does not become active or lock out sudo; the grant principal is this uid from the account database, not environment user vars; empty, ALL, %group, and leftover template tokens fail closed; already-installed matching wrapper, trusted path, and this-uid grant skip the prompt; trusted-path dest mismatch is one-sudo repair; untrusted ancestors disable the grant and fail; non-TTY fails closed without a GUI privilege prompt; concurrent setups take one root-owned lock so wrapper and grant stay one transaction.
- **R2:** After a successful setup, list save, reload, placement, and site-block apply/lift never present a sudo password prompt. Errors: missing or broken install → notify with the current unavailable-install wording and skip network apply/lift only; window placement still runs.
- **R3:** A failed or exception-raising network job does not stop the network worker. The worker stays accepting jobs and a later apply or lift can succeed. Errors: the failed generation is reported as failure to a waiting reload; no silent permanent stop.
- **R4:** A failed window query or move on one event does not stop the listener. Later events and reload requests still run. Errors: the bad event is skipped; the user may be notified; the process stays listening.
- **R5:** Overlapping reload requests do not interleave rule, registry, generation, network wait, or last-good writes. The second waits for the first's full transaction (load, generation bump, apply, network sync, result). Errors: a failed reload still leaves a consistent last-good; the next reload can retry.
- **R6:** Notification failure never leaves the listen loop. Missing sender, nonzero exit, and OS errors from the sender are absorbed. Errors: no error surface beyond a swallowed notify.

## Early proof point

Task fn-7-one-time-setup-privilege-and-helper.1 proves one sudo writes a matching trusted-path wrapper and uid-only grant, and a denied or interrupted run removes only this-run artifacts. If that fails, stop before hardening listen and reload. Runtime never-prompt (R2) is meaningless without a working grant.

## Boundaries

<!-- scope: business -->

- fn-4 product behavior stays: owned list, exclusive listed windows, always-on off-space site block, intercept banner, focus lock unchanged.
- This spec does not re-open fn-4 list membership, banner copy, or expand-map work.
- Splitting the helper into multiple modules and extracting shared test fixtures are not required to close this spec.
- Tests that reach internal worker state may stay; tightening them is optional.
- Uninstall remains a documented teardown of the privileged helper and grant, not a second interactive product flow.
- The notification-rescan command stays notification-rescan.
- Focus-mode hosts and `omarchy_focus` apply/lift stay on the existing focus privilege path. Healing a leftover focus hosts sinkhole is out of scope.
- A one-line "run setup" toast hint is out of scope. The skip body stays the current unavailable-install wording.

## Decision Context

<!-- scope: both -->

Quality findings stay in the existing helper rather than a rewrite. One setup sudo is the only privilege UX. Runtime keeps the already-chosen constrained helper and `sudo -n`.

Rejected: prompting sudo on every apply or install file.
Rejected: folding nft setup into the notification-rescan command (that command already means `rescanPlugins`).
Rejected: using the focus-mode privilege ladder for ds setup or apply (pkexec can prompt).
Rejected: a "run setup" hint in the skip toast (current wording already says install is missing).
Rejected: a leftover focus hosts / `omarchy_focus` lift in this spec (focus lock is unchanged).

## Requirement coverage

| Req | Description | Task(s) | Gap justification |
|-----|-------------|---------|-------------------|
| R1 | One setup sudo, fail closed, idempotent | fn-7-one-time-setup-privilege-and-helper.1 | — |
| R2 | Runtime never prompts; skip-with-notify | fn-7-one-time-setup-privilege-and-helper.1 | — |
| R3 | Worker survives a failed job | fn-7-one-time-setup-privilege-and-helper.2 | — |
| R4 | Listener survives one failed query or move | fn-7-one-time-setup-privilege-and-helper.3 | — |
| R5 | Reloads serialize last-good writes | fn-7-one-time-setup-privilege-and-helper.2 | — |
| R6 | Notify failure stays swallowed | fn-7-one-time-setup-privilege-and-helper.3 | — |
