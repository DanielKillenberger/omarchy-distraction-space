---
satisfies: [R4, R5]
---
# fn-26-visible-health-and-accessible-v3.2 Validate integrated behavior and document v3 improvements

## Description
After fn25 and fn27 integration, update README and docs/internals coherently for all three specs, run full offline suite and QML lint, and perform authorized bounded live firewall/audio checks with restoration. Record actual versions/results and any unavailable or failed checks honestly; do not satisfy R4 with mocks. Add reusable opt-in validation instructions.

**Files:** README.md, docs/internals.md
**Touches:** README.md, docs/internals.md

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests

## Acceptance
- Real firewall in/out-of-slice and web-app/work-browser mute/restore evidence required for parent R4.
- Update commands, config/menu descriptions, migration, health/provenance and listener/firewall lifecycle descriptions for actual implementation.
- Preserve major version 3 and existing public interfaces.
- Do not claim blocked live checks passed; report exact residual limitation.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
