# Publish reviewed v3 and refresh the submission

## Goal & Context
User authorizes amending existing v3 PR23 with reviewed improvements and UI fixes, merging when validation is in order, and updating existing marketplace issue4518 to the merged version.

## Architecture & Data Models
No runtime implementation changes. Refresh v2 marketplace documentation to describe current v3 privilege, systemd user slice, launchers, browser routing/profile and verified firewall reconciliation.

## API Contracts
Preserve repository identity, plugin id, issue form/checklist and existing review history. Pin submission notes to the actual merged commit. Respect documented release process if one exists; do not invent tag/release steps.

## Edge Cases & Constraints
No hosted CI exists on PR23. Use passing local full suites and recorded Fable reviews under the explicit user merge authorization; do not fabricate GitHub review or CI evidence. Refuse actual merge conflicts or unmet required repository policies. Earlier no-main restriction is explicitly lifted for this merge.

## Acceptance Criteria
- **R1:** PR23 includes all reviewed v3 work plus fn28/fn29; accurate title/body and marketplace docs, successful plugin validation and final Python3.11/3.14 full suites.
- **R2:** Merge exact verified head into main, verify server merge state, update existing issue4518 notes to the merged SHA and v3 architecture, preserve checklist/history.

## Boundaries
One publication task. No new functionality or marketplace approval claim. No new submission issue.

## Decision Context
User agreed to update the existing submission rather than wait for admission of v2; explicit publication authorization is in this conversation.
