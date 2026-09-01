---
satisfies: [R5, R6]
---
# fn-8-off-space-block-feedback-page-and.3 Super+D entry confirm, README and manifest updates

## Description
Gate entering the distraction space behind a zenity confirm with the two spec'd guards (R6), and land every doc change including the R5 setup re-run instruction. Depends on .1/.2 because it touches the same `distractions` file as .2 and documents behavior .1/.2 ship.

**Size:** M
**Files:** `distractions`, `tests/test_enter_confirm.py`, `README.md`, `manifest.json`
**Touches:** [distractions, tests/test_enter_confirm.py, README.md, manifest.json]

### Approach
- `enter()` (`distractions:1985-1991`): after the `is_focus()` branch, take a non-blocking flock on a confirm lock file under `STATE_DIR` (mirror the `LISTEN_LOCK` shape at `distractions:4141-4150`); already held → return silently. Run zenity `--question --title "Distraction space" --text "Enter the distraction space?" --ok-label Enter --cancel-label Stay --timeout 30` following the subprocess shape at `prompt_list_editor` (`distractions:1841-1863`). Exit 0 → re-check `is_focus()` (→ `blocked_message()` if now on) and `on_distractions()` (→ return) before `show()`. Exit 1/5 → return. FileNotFoundError/other exits → notify once, then the same re-check + `show()` (fail-open).
- Tests: extend the fake-zenity-on-PATH convention (`tests/test_edit_list.py:20-32`) with ZENITY_MODE values for confirm/cancel/timeout(exit 5)/crash; missing-binary case via emptied PATH; focus-flip re-check via a fake zenity that flips the focus file before exiting 0; flock no-op via a held lock.
- README per spec §Approach and docs-gap findings: overview (`README.md:5`) gains the block-page/banner sentence; line 7's "Super+D is the only way in" gains the confirm clause; Install wrapper section (`README.md:39-49`) gains "after a plugin update, run `distractions setup` once again — until then the old wrapper keeps the old drop behavior"; Use table row (`README.md:74`) splits enter (confirm, 30s timeout = stay) from leave (plain keypress); post-table prose (`README.md:75-77`) documents the HTTP page, the HTTPS fast-fail + banner, and the no-MITM-by-design limitation.
- The setup re-run instruction is only true once fn-7 lands: today `setup_privileged_helper()` returns early whenever the installed wrapper's sudo grant works (`_wrapper_grant_ok()` at `distractions:3928-3947`), so a re-run does NOT replace a stale wrapper; fn-7's byte/metadata-mismatch repair is the mechanism (spec dependency fn-8 → fn-7). This task verifies against the fn-7-landed `setup`: its stale-wrapper test must show a content-mismatched installed wrapper gets replaced by a `setup` re-run — if fn-7 shipped that test, reference it; if not, add it here.
- `manifest.json:8` and `:21` descriptions: mention the block page/banner feedback.

### Investigation targets
**Required** (read before coding):
- `distractions:1985-2000` — enter()/toggle() to modify
- `distractions:1841-1863` — zenity subprocess shape to mirror
- `tests/test_edit_list.py:20-46` — fake zenity + SourceFileLoader conventions

**Optional** (reference as needed):
- `distractions:4141-4150` — flock pattern
- `README.md:39-77` — sections being edited

## Acceptance
- [ ] Confirm/cancel/timeout/crash/missing-zenity paths behave per R6 (tests for each)
- [ ] Enter after focus flipped on mid-dialog shows `blocked_message()` and does not switch (test)
- [ ] Second invocation while the lock is held returns silently with no dialog (test)
- [ ] Leaving the space and Super+Alt+D are untouched (test: `toggle()` on-space calls `hide()` with no zenity call)
- [ ] README + manifest updated per the listed anchors; no remaining text implies Super+D switches unconditionally
- [ ] A stale (content-mismatched) installed wrapper is replaced by a `setup` re-run — covered by a test here or a referenced fn-7 test; if fn-7's landed `setup` still skips on a working grant, this task fails closed and escalates rather than shipping a README claim that is false
- [ ] `python3 -m pytest tests/ -q` passes

## Done summary
Superseded, not implemented. The redirect-and-reject wrapper, the block page, the SNI banner, and the entry confirm are carried unchanged into fn-9-rewrite-one-contained-distraction-space (R2, R4, tasks .3, .4, .5). This task was written against the old single-file script, whose `enter()` and `listen()` anchors fn-9 deletes, so no code was written here.
## Evidence
- Commits:
- Tests:
- PRs: