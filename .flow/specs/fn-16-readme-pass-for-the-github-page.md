# README pass for the GitHub page

## Conversation Evidence

> user: "i want you to spec a readme pass using /prose to make it appealing to check the focus github"

## Goal & Context

<!-- scope: business -->

A person landing on the GitHub page decides in the first screen whether this plugin is for them. Today the README opens with a 276-line reference that starts at the architecture and lists every state file before it shows what the plugin does for a person at their desk. After this pass the first screen says what changes for the reader in one paragraph, shows the result in one image, and gives the three commands to install. The reference material stays, moved below the fold and trimmed to what a person needs to operate the plugin; internals that only a maintainer needs move to `docs/`. Every sentence follows the flow-next prose contract in `docs/prose.md` of the flow-next plugin: no portable filler, mechanisms and numbers over feelings, no negative parallelism, active voice with a named actor, no em dashes, honest about limits.

## Architecture & Data Models

<!-- scope: technical -->

**Above the fold.** Title, one-line tagline, one paragraph in the second person on what the reader gets (listed apps live on one workspace and open there, listed sites refuse to load elsewhere, held notifications and a one-line summary from their own agent when they come back, a lock with a stated purpose). One screenshot or short GIF at `preview.png` showing the bar glyph with a held count and the "While you were away" notice (the marketplace also reads `preview.png`). Then a three-step install: `omarchy plugin add ... --enable`, copy the three Hyprland snippets, run `distractions setup`. Requirements line: Omarchy 4, Hyprland, Python 3.11.

**What it does**, as short sections with the mechanism named in each: window containment (named Hyprland rules through `hyprctl eval`, plus the socket2 safety net), site block (resolved addresses dropped and redirected by nftables, block page on HTTP, banner on HTTPS only for fetches from windows outside the space), notification hold (the patched notification service clone, per-app counts, the summary), sound mute (with its stated limit: a browser's shared audio service cannot be attributed per web app), the lock (purpose, minutes, written reason to leave early), the keys table, and the moved-versus-blocked catalog table.

**Limits, stated plainly.** Address-level blocking catches other services on shared addresses (Google front ends), HTTPS cannot show the block page without a trusted certificate, Chrome web-app sounds are not muted, the notification hold needs the shell patch until it is upstream, `setup` asks for sudo once.

**Operate and configure.** Config keys with defaults, the CLI table, and where state lives, each trimmed to one line per item. `docs/internals.md` takes the listener loop, state file shapes, network generations, and the clone lifecycle detail that only a maintainer reads. Every command in the README is copied from a working invocation on this machine.

**Contributing and license** close the page. The badges, if any, are limited to license and the marketplace listing once it exists.

## Edge Cases & Constraints

<!-- scope: technical -->

- The README must not claim anything not verified live in this session or by a test; the fn-10 and fn-15 live checks are the source for the notification and banner claims.
- No em dashes anywhere in the file; the existing README carries several `→` arrows in the install list that become plain words.
- Relative links resolve on GitHub (`docs/internals.md`, `hypr/bindings.lua`).
- `preview.png` is a real capture from this machine, under 1 MB, taken with `omarchy capture screenshot` or equivalent, and committed.

## Quick commands

```bash
python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
grep -c -- "—" README.md   # expect 0
```

## Acceptance Criteria

<!-- scope: both -->

- **R1:** The first screen of `README.md` (title through the install block) tells a reader what changes for them, shows `preview.png`, and lists the install in three steps with the requirements line. Errors: none.
- **R2:** Each "what it does" section names its mechanism and every limit listed in Architecture appears under a Limits heading. Errors: none.
- **R3:** Maintainer-only detail (listener loop, state file shapes, network generations, clone lifecycle) lives in `docs/internals.md`, linked from the README, and the README is under 200 lines. Errors: none.
- **R4:** No em dashes or arrow glyphs remain in `README.md`; every command shown was run on this machine during the pass. Errors: none.
- **R5:** `manifest.json`'s `description` matches the README tagline in substance. Errors: none.

## Boundaries

<!-- scope: business -->

- No behavior changes; this spec touches `README.md`, `docs/internals.md`, `preview.png`, and `manifest.json` description only.
- The marketplace submission itself is fn-17.

## Decision Context

<!-- scope: both -->

The user asked for a page that sells the plugin to someone browsing GitHub, written under the prose contract. Rejected: a badge wall and feature adjectives, both fail the contract's portability test.
