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
Rewrote every workspace-keyed statement in `README.md` and `docs/internals.md` for the process-group design and bumped `manifest.json` to 3.0.0 (R15); the full suite is green on the final tree (R16). The README describes the slice, the browser profile, the login-once upgrade cost in the first sentence of `## Upgrading from 2.x`, the three containment layers, the static table with `site_block.enabled`, the URL handler, the two banners, slice-first mute, `release` and `containment.snap_back`, and every new config key and verb; the web-app audio limit is gone and the three parked unknowns sit in Limits as caveats. Internals gains The slice, Browser profile, URL handler, Launcher entries and `entries.json`, and Banners sections; Network replaces Network generations; State files carry `links`, `browser`, `released`, `entries.json`, `entries-backup/`, and the `expansion.json` additions. `docs/marketplace-submission.md` is untouched.

### What changed (commits 1c385d4, dab458b, cd03c2e; base 5f2b52f)
- `README.md`, `docs/internals.md`, `manifest.json` (the worker's commit).
- Conductor follow-up found while the docs were written from the code: `state.json.browser` was never assigned, against R14. `ds/listener.py` now resolves the basename at start and reload through `launch.pick_browser`, the internals line describes that instead of a null, the listener tests sandbox `XDG_DATA_DIRS`, and the links-off test proves the link check never asks `xdg-settings` by watching the call count across ticks. The documented test count moved to 346.
- Written on the session model rather than bridged to grok: the README voice is judgment territory under the routing rule.

### Left for later, recorded on purpose
- `feedback._maybe_banner` shim and its test remain; `distractions menu` does not expose the new keys.

### Review
cursor / gpt-5.6-sol-high, two rounds: round 1 NEEDS_WORK (documented test count one short after the browser-state fix), round 2 SHIP with R15 and R16 met.

### Gates
- baseline: green via handoff (f5bc1d46)
- verify: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at dab458b, 346 tests, OK; receipt `.flow/tmp/green-receipts/dab458b9-unittest.json`; cd03c2e is docs-only on top
- classify: FULL

stage: impl-review - ran (cursor gpt-5.6-sol-high, 2 rounds, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 1c385d4, dab458b, cd03c2e
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 346 tests at dab458b; receipt .flow/tmp/green-receipts/dab458b9-unittest.json)
- PRs: