---
satisfies: [R15, R16]
---
# fn-22-the-space-is-a-process-group-one.9 Docs, manifest 3.0.0, upgrade section, and the full-suite gate

## Description
Rewrites every workspace-keyed statement in the docs, adds the upgrade note, bumps the manifest (R15), and is the final green-suite gate (R16). Docs mirror code, so this task is grok-eligible under the project's routing rule; the worker reviews the diff.

**Size:** M
**Files:** `README.md`, `docs/internals.md`, `manifest.json`
**Touches:** [README.md, docs/internals.md, manifest.json]

### Approach
- `README.md`: intro (drop "refused while you work elsewhere"); Install (slice unit, launcher entries with backup, URL handler; three new setup actions); new `## Upgrading from 2.x` whose first sentence says each web app asks for a login once in the new profile; What it does (slice framing, three layers, two banners, slice-first mute); Keys (`release` binding suggestion); Limits (delete the web-app audio limit; add Firefox web apps, the `socket cgroupv2` kernel dependency and `site_block: unavailable`, Chromium single-instance handoff, profile kept on remove); Configure (rows for `site_block.enabled`, `browser`, `open_links_in_space`, `containment.snap_back`, `containment.release_minutes`; reword `nudges.*`); Commands (`open`, `refresh`, `release`; `status` fields; `banners` line shape; `setup` scope); Contributing test count.
- `docs/internals.md`: Layout (new `ds/cgroup.py`, `ds/launch.py`); Window containment (three layers, adoption, release set); Listener loop and Network (static table, cgroup rule first, slice unit, 60 s, `refresh`, no enter/leave action); new URL handler, Launcher entries and `entries.json`, Browser profile sections; Notification capture and sound mute (slice first); State files (`links`, `browser`, `released`, `entries.json`, `expansion.desktop`, `site_block` causes); Catalog shapes (`desktop`); Tests count.
- `manifest.json`: `"version": "3.0.0"`, description reworded to the process-group framing. `docs/marketplace-submission.md` stays pinned to 2.1.0.
- Follow the docs-gap list in the spec's planning notes; every row in the README tables is one line, no prose restatement.

### Investigation targets
**Required** (read before coding):
- `README.md` — headings Install, What it does, Limits, Configure, Commands
- `docs/internals.md` — every section
- `manifest.json:4-10`

**Optional:**
- `docs/marketplace-submission.md:84-107` — what NOT to change

## Acceptance
- [ ] `grep -n 'elsewhere\|every 30 seconds\|flushes the sets\|Blocked on this workspace' README.md docs/internals.md` is empty
- [ ] README has `## Upgrading from 2.x` whose first sentence states the login-once cost
- [ ] README Configure and Commands tables list every new key and verb; Limits no longer claims web-app audio cannot be muted
- [ ] `manifest.json` reads `3.0.0`
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes offline on a clean checkout and the test count in README and internals matches


## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
