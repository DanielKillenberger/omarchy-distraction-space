---
satisfies: [R4, R5]
---
# fn-26-visible-health-and-accessible-v3.2 Validate integrated behavior and document v3 improvements

## Description
Prepare independent documentation and review corrections now; finalize after fn25 and fn27 integration. Update README and docs/internals coherently for all three specs, run full offline suite and QML lint, and perform authorized bounded live firewall/audio checks with restoration. Record actual versions/results and any unavailable or failed checks honestly; do not satisfy R4 with mocks. Add reusable opt-in validation instructions.

Address Fable nonblocking truthfulness findings: empty-host site blocking is legitimate idle, and missing window identity must not show an unanswerable migration question. Add focused regressions and retain full public interface contracts.

**Files:** README.md, docs/internals.md, ds/state.py, ds/hypr.py, tests/test_status.py, tests/test_hypr.py
**Touches:** README.md, docs/internals.md, ds/state.py, ds/hypr.py, tests/test_status.py, tests/test_hypr.py

### Quick commands
PATH=/usr/bin:$PATH python3 -m unittest discover -s tests
## Acceptance
- Real firewall in/out-of-slice and web-app/work-browser mute/restore evidence required for parent R4.
- Update commands, config/menu descriptions, migration, health/provenance and listener/firewall lifecycle descriptions for actual implementation.
- Preserve major version 3 and existing public interfaces.
- Do not claim blocked live checks passed; report exact residual limitation.

## Done summary
Integrated all three v3 improvement tracks and updated README/internals for exact URLs, safe migration, health provenance, menu controls, serialized listener work, verified firewall reuse/repair, and browser scope/audio identity. Empty-host health is truthful idle and missing identity never creates an unanswerable migration offer. Version remains3.0.0.

Full integrated suite:445 tests passed with1 intentional live-test skip. QML lint exits0 with the same two documented Qt warnings. Real wrapper namespace suite20passed; actual reconciliation against nftables confirms one replace and3checks across3equal cycles plus rule/table drift repair and repeatedflush. Actual committed browser helper live evidence confirms Chrome152 process/audio containment and owned mute/release with independently launched work streams unaffected. Evidence .flow/evidence/fn26-live-validation.json and v3-live-reconcile.json distinguishes deployedHTTPS, branchwrapper namespace, directhelper audio and limits. No global leave/unlock transition was demonstrated, pre-muted streams remainunclaimed, and inherited cold-forward audio identity remains a documented limitation.

stage: impl-review - ran (model: claude-fable-5-1). SHIP at308e1d5; finalclarifications enumerate launcher states, record inheritedforward limitation and actualintegrated repair behavior.
stage: plan-sync - skipped(config: planSync.enabled=false).
No push, main merge, deployment, release or marketplace admission. Integration branch fn-25-27-v3-improvements remains separate from v3 basef0cc79a.
## Evidence
- Commits: 21f1410, 821ecd7, 2f79f03, ae9b3e9, 8edafdb, 075f4e2
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (445 passed,1 intentional skip), /usr/lib/qt6/bin/qmllint -I /tmp/qmlimports BarWidget.qml (exit0;2 known warnings), PATH=/usr/bin:$PATH DS_LIVE_NFT_TEST=1 python3 -m unittest tests.test_nft (20 passed), Actual browser/audio helper and real-kernel reconciliation: .flow/evidence/fn26-live-validation.json, .flow/evidence/v3-live-reconcile.json
- PRs: