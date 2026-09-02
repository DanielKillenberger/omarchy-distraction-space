# fn-17-marketplace-readiness-and-submission.2 Prepare docs/marketplace-submission.md with the baseline capability mapping

## Description
Write `docs/marketplace-submission.md`: a filled-in copy of the marketplace's submit-plugin issue form (SUBMISSION.md in omacom/omarchy-plugin-marketplace, headings in order: Repository URL, Category, Tags, Suggest a missing tag, Maintainer notes, Submission checklist) for repository https://github.com/DanielKillenberger/omarchy-distraction-space, category Productivity, tags hyprland, workspaces, system (lowercase form for the CLI path), plugin id `io.github.danielkillenberger.distraction-space` (task 1 renames it; assume the new id). Maintainer notes must state plainly: `omarchy plugin add` runs no sudo; privilege arrives only through the explicit `distractions setup` command, which installs the root-owned wrapper at `/usr/local/libexec/omarchy-distraction-space/distractions-nft` and a sudoers drop-in scoped to that one path for the installing user after `visudo -cf`; the wrapper takes `replace ds` or `flush ds` and reads addresses on stdin (say how it validates them, read `distractions-nft`); the notification-service clone under the user's own config; runtime dependencies (nft, sudo, busctl, pactl, python3, optional agent CLIs); Hyprland snippets copied by hand; removal via `distractions setup --remove` then `omarchy plugin remove`; the `manual-setup` label is expected. Below the form add a section "Automated Security Baseline mapping" with one line per documented pattern and capability from the marketplace's SECURITY.md (curl-pipe-shell, cargo-git-unpinned, remote-git-execution-unpinned, sudoers-dangerous-passwordless-command, privileged-process-control-from-shared-temp, installer, package-manager, privilege, remote-build, bundled-executable-binary, service-management, sudoers-modification) saying whether the repo triggers it and pointing at the file that does (install/sudoers.omarchy-distraction-space, ds/setup.py, README.md). Add a "Pinning discipline" section: validation binds to HEAD at filing; main stays frozen until `approved-and-verified`; a needed push is followed by editing the issue; later releases go through the verify form with the new 40-character SHA. Add the `gh issue create` command from SUBMISSION.md with this body. Prose follows the artifact prose contract (no em dashes). Nothing else in the repo changes.

**Touches:** docs/marketplace-submission.md

## Acceptance
- [ ] TBD

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
