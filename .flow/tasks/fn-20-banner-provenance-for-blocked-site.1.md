---
satisfies: [R1, R2, R4, R5]
---
# fn-20-banner-provenance-for-blocked-site.1 Provenance line for every HTTPS banner decision, per-host rate limit, hostname-only

## Description
In ds/feedback.py, make every banner decision on the TLS path append one provenance line to the state log, whether the banner fired or not. Format: `<iso> banner: host=<host> entry=<entry|-> port=<n> pid=<n|-> exe=<basename|-> class=<class|-> ws=<workspace|-> decision=<reason>[ dropped=<n>]` written through the existing state-log helper (hypr._log, which prefixes the ISO timestamp). Field values never contain whitespace: replace any whitespace run in a value with `_`; an absent value is `-`. `decision` is one of `shown`, `debounced`, `on-space`, `entry-on-space`, `unattributed`. `entry` is the matched catalog entry name from `_entry_for_host` (`-` when none), `pid` and `exe` come from the existing peer-port to inode to pid attribution (`exe` is the basename of /proc/<pid>/exe read through the same DS_PROC_ROOT the tests fake, `-` when unknown), `class` and `ws` are the attributed Hyprland client's class and workspace name (`-` when unattributed). Decision reasons: `shown` (banner sent), `debounced` (inside the 30 s per-entry window; no attribution attempted, pid/exe/class/ws are `-`), `on-space` (owner's windows all on the space), `entry-on-space` (entry fallback matched windows on the space), `unattributed` (no socket, process, or client match; banner still shown as today, decision stays `unattributed` so the line says why). A partial attribution (socket found, process gone) records what was recovered and `unattributed`. Per-host rate limit: at most 20 lines per host per minute (a module constant); further decisions in that minute increment a dropped counter, and the next line for that host carries ` dropped=<n>` and resets it. The line never carries a URL path, query, request body, or notification text; only the SNI hostname. The log write never blocks or alters the banner path and an unwritable log drops the line silently (hypr._log already swallows OSError). The banner text, the debounce, and the on-space suppression are unchanged and the existing banner tests pass unmodified. Tests in tests/test_feedback.py: one line per decision with the exact field order for shown, debounced, on-space, entry-on-space, unattributed (reuse the fake /proc and hyprctl fixtures the R1/R2 tests already build); the rate limit with a monotonic clock patch (21 hellos in a minute yield 20 lines, the next minute's first line carries dropped=1); hostname-only for an SNI whose request carries a path and query (the HTTP path has no banner, so drive the TLS path and assert the line has no `/` or `?`). Run the focused module then the full suite.

**Touches:** ds/feedback.py, tests/test_feedback.py

## Acceptance
Every R-ID this task declares in `satisfies` is met per the parent spec's Acceptance Criteria; judge against the spec directly.

## Done summary
Every banner decision on the TLS path now appends one `banner: host= entry= port= pid= exe= class= ws= decision=` line to the state log through hypr._log, with the decision from the closed set shown / debounced / on-space / entry-on-space / unattributed, values whitespace-free and absent ones `-`, a per-host cap of `PROVENANCE_PER_MIN` (20) lines a minute whose overflow rides the host's next line as ` dropped=<n>`, and the SNI hostname as the only request-derived value. Attribution (`_attribute` in ds/feedback.py, replacing `_origin_on_space`) returns what it recovered instead of a bool; banner text, debounce, and on-space suppression are unchanged and the pre-existing banner tests are untouched.

Implementation bridge: grok (grok-4.6, high reasoning) wrote the first pass of both files from a self-contained brief; the bridge call outran the 10-minute foreground budget while grok was running the full suite, so its process was stopped and the diff reviewed line by line. Changed after grok: removed the blanket `try/except Exception: pass` around `_provenance` (hypr._log already swallows OSError; nothing else in the writer can raise), dropped the unused `host` parameter from `_attribute`/`_attribute_inner`, replaced the literal 60 with `_PROVENANCE_WINDOW_S`, and renamed `l` loop variables in the tests. Red check: 7 of 8 new tests fail on the pre-change module with zero provenance lines; `test_r1_provenance_unwritable_log_keeps_banner` is a no-regression guard for R1's error case and passes on both.

Tests added in tests/test_feedback.py (R1: shown, debounced, on-space, entry-on-space, unattributed x3 subtests, unwritable log; R2: 21 hellos yield 20 lines, next minute carries dropped=1; R5: hello followed by a path and query logs no `/` or `?`). `_write_proc` gained an optional `exe={pid: path}` map for the /proc/<pid>/exe symlink.

baseline: green (PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, 256 tests, pre-edit)
verify: focused module 41 tests OK; full suite 264 tests OK; GREEN_RECEIPT .flow/tmp/green-receipts/ca3c8430-unittest.json

stage: impl-review - skipped(policy: host-deferred - conductor owns the gate; parallel-wave worker)

### Integration (conductor)

Cherry-picked onto the spec branch as 24817c8792e59c8491c29cf20aece53bad7d342f (workspace commit ca3c843) after task 2. Review (cursor, gpt-5.6-sol-high) round 1 NEEDS_WORK on three P2s: attribution gave up on pid and exe when Hyprland was unavailable, entry-on-space logged the first owner client instead of the one that justified it, and the rate-limit key was case-sensitive. Fixed in f7cc5c0b5118af80dbd4af53dce4f9017422f221 with a test each; round 2 SHIP. Quiesce verification at f7cc5c0b5118af80dbd4af53dce4f9017422f221: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` 274 tests OK (receipt .flow/tmp/green-receipts/f7cc5c0b-unittest.json).

stage: wave-dispatch - ran [2 tasks, native worktrees, disjoint Touches, no join collision] (implementer: grok-4.6 via the CLI bridge, reviewed and committed by the worker)
stage: impl-review - ran [round 1 NEEDS_WORK, round 2 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 24817c8792e59c8491c29cf20aece53bad7d342f, f7cc5c0b5118af80dbd4af53dce4f9017422f221
- Tests: PATH=/usr/bin:$PATH python3 -m unittest tests.test_feedback, PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, quiesce at f7cc5c0: unittest 274 OK
- PRs: