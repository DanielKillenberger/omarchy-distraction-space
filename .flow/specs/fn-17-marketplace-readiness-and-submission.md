# Marketplace readiness and submission

## Conversation Evidence

> user: "And then we can make it ready for the plugin marketplace i think? the summary was actually nice. Works well."

## Goal & Context

<!-- scope: business -->

The plugin becomes installable from the official Omarchy Plugin Marketplace at plugins.omarchy.org. Listing is by GitHub issue on `omacom/omarchy-plugin-marketplace` (template `submit-plugin.yml`), reviewed against a compatibility validation and an Automated Security Baseline, and published at an exact commit. This spec gets the repository to a state that passes those checks and prepares the submission; the human files the issue.

## Architecture & Data Models

<!-- scope: technical -->

Verified 2026-09-02 from the marketplace repository and plugins.omarchy.org:

- **Manifest.** `schemaVersion: 1`, `id`, `name`, `version` (up to 64 chars), `author`, `description`, `kinds`, `entryPoints` are required; `omarchy plugin validate <dir>` passes today. The develop guide shows third-party ids in namespaced form (`io.github.yourname.custom-clock`) and forbids the `omarchy.*` prefix; the publish page shows `yourname.plugin`. Our id is `distraction-space`, unnamespaced. Decision needed: keep it (the validator accepts it; the install path stays `~/.config/omarchy/plugins/distraction-space`) or rename to `killenberger.distraction-space`, which changes the install path, the bar id, the clone step's owner naming, and every README path, and requires a migration note for existing installs.
- **Files.** Public repo (yes), `README.md` with installation and removal (present; fn-16 improves it), `LICENSE` (MIT, present), `preview.png` (missing; fn-16 adds it; the marketplace auto-optimizes it).
- **Security baseline** (`SECURITY.md#automated-security-baseline` in the marketplace repo, to be read in task 1): the plugin runs unsandboxed; our surface includes a sudoers grant for the nft wrapper, an `/etc/sudoers.d` write, a cloned and patched notification service, a busctl monitor, PulseAudio mutes, and an optional agent CLI call with notification text. Each must be documented in the README's privilege section and in the submission's "Maintainer notes".
- **Submission checklist** (from the issue template): public repo with install and removal instructions; license and external dependencies documented (nft, sudo, zenity or omarchy-menu, busctl, pactl, optional claude or grok); permission to submit preview assets; the plugin does not overwrite user configuration without consent (setup writes `/etc/sudoers.d/omarchy-distraction-space` and clones the notification service after an explicit command; the Hyprland snippets are copied by hand); approval is listing, not security review.
- **Category and tags.** Category Productivity; tags from the fixed list, pick up to three: Hyprland, Workspaces, and one of System or Bar.
- **Release pinning.** Listings record an exact commit; a `v2.1.0` tag on that commit and `version` bumped in `manifest.json` to match. Later updates go through the `verify-plugin.yml` form with the new SHA.
- **qmllint.** The develop guide asks for `qmllint -I "$OMARCHY_PATH/shell" BarWidget.qml`; run it and fix warnings.

## Quick commands

```bash
omarchy plugin validate .
qmllint -I "$OMARCHY_PATH/shell" BarWidget.qml
python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
```

## Acceptance Criteria

<!-- scope: both -->

- **R1:** `omarchy plugin validate` and `qmllint` pass on the repository root at the tagged commit. `qmllint` runs with an import directory whose `qs` entry is a symlink to `$OMARCHY_PATH/shell`, because Quickshell maps `qs.*` to the shell root and a bare `-I $OMARCHY_PATH/shell` cannot resolve `qs.Commons` or `qs.Ui`; the README's Contributing section carries that command. The one remaining warning, `Style.bar.iconSlot` missing on a QObject, is a dynamic property and is documented as noise. Errors: none.
- **R2:** The README documents every external dependency, privilege boundary (sudoers grant, wrapper path, notification-service clone), service, and the removal path (`setup --remove`, `omarchy plugin remove`). Errors: none.
- **R3:** The id is `io.github.danielkillenberger.distraction-space` in `manifest.json`, `BarWidget.qml`'s `moduleName`, the two Hyprland snippet paths, and every README install path; the README carries a migration note for installs of the old id (`omarchy plugin remove distraction-space`, add again, re-copy the snippets, `distractions setup`). Config, state, socket, wrapper, and sudoers names stay `distraction-space` / `omarchy-distraction-space`; they never derived from the plugin id. Errors: none.
- **R4:** `manifest.json` `version` is `2.1.0` and the conductor tags the merged submission commit `v2.1.0` on main after the PR lands (a tag cannot ride a PR); the version and a filled-in copy of the submission form (repository URL, category, tags, maintainer notes, checklist) is saved as `docs/marketplace-submission.md` for the human to paste. Errors: none.
- **R5:** The Automated Security Baseline document has been read and each of its checks is mapped to a line in `docs/marketplace-submission.md` saying how the plugin satisfies it or why it needs a maintainer note. Errors: none.

## Boundaries

<!-- scope: business -->

- Filing the GitHub issue is the user's action; this spec stops at the prepared form.
- No functional changes beyond the id rename if chosen and qmllint fixes.
- Depends on fn-16 for `preview.png` and the README.

## Decision Context

<!-- scope: both -->

The user chose on 2026-09-02 to rename to `io.github.danielkillenberger.distraction-space` before the first listing, since ids are permanent marketplace identifiers and the only install so far is the author's. Rejected: keeping `distraction-space`, allowed by the validator but a bare id the marketplace guide steers away from, and unrenameable after listing.

From the marketplace's own history (issues #3293 Self Control, #3756 Deeplok, #3590 GNO Recall, read 2026-09-02): the Automated Security Baseline will report the capabilities `privilege`, `sudoers-modification`, and `installer` and no findings, which is `review-required`, the same disposition two nft and hosts blockers with a sudoers or polkit grant were approved under the same day. The `manual-setup` label is expected because `omarchy plugin add` alone yields no working plugin. Validation binds to the exact HEAD at filing; GNO Recall's review was refused after a three-line merge moved HEAD, so main stays frozen from filing until `approved-and-verified`, and any needed push is followed by editing the issue to revalidate.
