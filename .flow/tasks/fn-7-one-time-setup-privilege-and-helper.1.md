---
satisfies: [R1, R2]
---
# fn-7-one-time-setup-privilege-and-helper.1 One-shot setup command and README

## Description
Harden the existing `setup` / `setup_privileged_helper()` path (R1) and keep runtime apply/lift on `sudo -n` plus skip-with-notify (R2). Split from the listen/worker work so the grant can be proven before hardening the loop.

**Size:** M
**Files:** distractions, README.md, distractions-nft, tests/test_setup.py, install/sudoers.omarchy-distraction-space
**Touches:** [distractions, README.md, distractions-nft, tests/test_setup.py]

### Approach
- Keep the existing `setup` command. Replace `setup_privileged_helper()`'s current `sudo bash -c 'install -D ... && install ...'` transaction. Leave notification rescan unchanged.
- One interactive sudo: pin existing ancestors with no-follow directory descriptors (reject any symlink component, any user-writable or non-root-owned ancestor). Create any missing dest directories through the nearest pinned parent, then pin and validate each new directory before the next create or the wrapper stage. Stage a root-owned 0755 regular file next to dest through the pinned parent, verify bytes against the shipped helper, atomically replace dest, reverify on the pinned descriptors, then walk again from the filesystem root with no-follow and match each component's device, inode, and metadata to the pinned chain including the final wrapper. Then stage a root-owned sudoers grant on the same filesystem, validate with visudo, and atomically rename it into place (0440, matching the shipped template). Grant is committed only after that revalidation. Path pins stay held through grant commit.
- Concurrent setups share one root-owned lock around wrapper copy, verify, and grant commit.
- Deny, cancel, SIGINT, or non-TTY: fail closed, remove only artifacts this run created, no pkexec. Keep an older grant only when dest and ancestors are still trusted. An existing grant for a missing or untrusted path is disabled before dest write. Denied sudo cannot remove a root-owned grant; the message says so.
- Re-run: skip the prompt when wrapper bytes, pinned trusted-path checks, and this-uid grant already match. Trusted-path dest mismatch is one-sudo repair. Untrusted ancestors disable the grant and fail. No dest write into an unsafe ancestor.
- Render the sudoers principal from this process uid via the account database. Do not use `getpass.getuser()` / `LOGNAME` / `USER`. Reject empty, `ALL`, `%` group forms, and leftover `__INSTALL_USER__`.
- Runtime path stays `sudo_nft` / `wrapper_present` / `note_network_unavailable`. Do not call `focus_block.privileged()`.
- README already documents `distractions setup`. Update it only if trusted-path or fail-closed behavior changes. Uninstall stays teardown. `install` stays rescan.
- `install/sudoers.omarchy-distraction-space` is read-only input (Files, not Touches). Mode stays 0440. Setup writes the installed grant, not the shipped template.
- Extend `tests/test_setup.py`. Do not leave the old install transaction reachable.

### Investigation targets
**Required** (read before coding):
- `distractions:3916-3974` — current `setup_privileged_helper()` sudo-bash install
- `distractions:1506-1559` — `sudo_nft`, `wrapper_present`, skip-with-notify
- `tests/test_setup.py` — existing non-TTY, skip-sudo, visudo tests
- `install/sudoers.omarchy-distraction-space` — `__INSTALL_USER__` grant, mode 0440
- `README.md:44-58` — current setup and uninstall

**Optional:**
- `focus_block.py:640-667` — privilege ladder to avoid
- `tests/test_enforcement.py` — `test_missing_wrapper_skips_network_only`
## Acceptance
- [ ] Existing `setup` still requests sudo once; the current `sudo bash -c install...` transaction is gone
- [ ] Installed sudoers mode is 0440, matching the shipped template
- [ ] Grant principal is this uid from the account database; spoofed `LOGNAME`/`USER` such as `ALL` or `%wheel` is rejected
- [ ] Deny, cancel, interrupt, or non-TTY removes only this-run artifacts and prints a clear failure
- [ ] An older grant is kept only when dest and ancestors are still trusted; a grant for a missing or untrusted path is disabled before dest write
- [ ] Matching wrapper, pinned trusted path, and grant skip the prompt; trusted-path dest mismatch is one-sudo repair; untrusted ancestors disable the grant and fail
- [ ] Concurrent setups take one root-owned lock; dest and every ancestor are pinned with no-follow directory descriptors before any write; grant is committed only after stage, verify, atomic replace, pinned reverify, and a fresh root-to-dest no-follow walk that matches device/inode/metadata
- [ ] Clean install creates missing dest directories through the nearest pinned parent, then pins and validates each before the wrapper stage
- [ ] visudo-safe sudoers install stages, validates, and atomically renames; a malformed or interrupted fragment is not the active file; a previous grant stays intact if rename does not happen
- [ ] Tests refuse grant when dest or any ancestor is a symlink or user-writable; a symlink dest or ancestor is not followed; ancestor replacement after pin fails the root-to-dest revalidation and does not commit a grant; an interrupted replace leaves the previous wrapper unchanged
- [ ] Runtime apply/lift still uses `sudo -n`; missing wrapper skip-with-notify keeps placement
- [ ] README still documents setup and uninstall; docs change only if behavior changes; `install` stays rescan
- [ ] `python3 -m unittest discover -s tests` passes
## Done summary
Hardened `setup` so one interactive sudo runs an in-memory installer: pin a trusted path, atomically install the 0755 wrapper, visudo-validate a uid-only 0440 grant, and revalidate immediately before rename. Runtime apply/lift still uses `sudo -n` plus skip-with-notify.

stage: impl-review - ran (model: gpt-5.6-sol-high)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: b198dc12b301e62b220ac7ec1ac15b6293489cc7, 22bbf1db11a291f5ab1be600d82fed9bdc739b62, 68f48a567afcdddd32de5fad58c644df02b47ac6, 99d5a026ebf3be34437cb4a90d2516d8e577fc1d, 8d0a63bfe8f23463eb9034b85a7ff915a6b06689, 538cbb6b3645c444916cbd7e3436f4b6a611d0a8, 78c9cee4ef02c2665b4d1aa00d234bae839eee2d, 6c8f4c37fe5622815bdaed5527bc4e245356a08d
- Tests: python3 -m unittest tests.test_setup
- PRs: