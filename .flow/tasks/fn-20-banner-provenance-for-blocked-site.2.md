---
satisfies: [R3]
---
# fn-20-banner-provenance-for-blocked-site.2 distractions banners: print the latest provenance lines

## Description
Add a `banners` subcommand to the `distractions` CLI (the argparse builder and COMMANDS table in the `distractions` script) that prints the most recent banner provenance lines from the state log, newest first, 20 by default, with `--count N` (positive integer; argparse rejects the rest). Lines are those whose text after the timestamp starts with `banner: `; the format task 1 writes is `<iso> banner: host=<host> entry=<entry|-> port=<n> pid=<n|-> exe=<basename|-> class=<class|-> ws=<workspace|-> decision=<reason>[ dropped=<n>]` written through the existing state-log helper (hypr._log, which prefixes the ISO timestamp). Field values never contain whitespace: replace any whitespace run in a value with `_`; an absent value is `-`. `decision` is one of `shown`, `debounced`, `on-space`, `entry-on-space`, `unattributed`. Print each matching line verbatim (timestamp included). An absent or empty log prints nothing and exits 0. Implement `cmd_banners` in ds/state.py next to cmd_status, reading `state.state_path("log")` with the same tolerance as the rest of the module (missing file, unreadable file -> nothing, exit 0; decode with errors="replace"). Add a row to the README Commands table. Tests in a new tests/test_banners.py using tests/harness.py's Sandbox: a log with mixed lines yields only banner lines newest first and honours --count; empty and missing logs exit 0 with no output; invalid --count exits 2. Do not touch ds/feedback.py (task 1 owns the writer).

**Touches:** distractions, ds/state.py, tests/test_banners.py, README.md

## Acceptance
Every R-ID this task declares in `satisfies` is met per the parent spec's Acceptance Criteria; judge against the spec directly.

## Done summary
Added `distractions banners [--count N]` (R3): `cmd_banners` in ds/state.py reads the state log with the module's tolerance (missing or unreadable file prints nothing, exit 0; decode errors="replace"), keeps lines whose text after the timestamp starts with `banner: `, and prints them verbatim newest first, 20 by default. `--count` uses a `positive_int` argparse type in `distractions` so 0, negatives, and non-integers exit 2. README Commands table gained one row. tests/test_banners.py (7 tests) covers mixed-log ordering, --count, the default of 20, empty, missing, and unreadable logs, and invalid --count. ds/feedback.py untouched.

baseline: green (PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, 256 tests, rc 0, no prior receipt)
verify: full suite 263 tests rc 0; green receipt .flow/tmp/green-receipts/4e639bed-unittest.json
red-first: 6/7 new tests failed at base with `invalid choice: 'banners'`; the invalid --count case exits 2 at base too (unknown subcommand), which is the same exit code the AC names

Bridge: grok (grok-4.6, high reasoning) implemented all four files in one run. Changes made after review of its diff: removed a blank line it inserted after the new README row that split the Commands table in two; collapsed a duplicated ArgumentTypeError branch in positive_int; removed extra blank lines before build_parser and main; dropped the unused ROOT import from tests/test_banners.py. cmd_banners and the tests were kept as written.

stage: impl-review - skipped(policy: host-deferred - conductor owns the gate; parallel-wave worker)

### Integration (conductor)

Fast-forwarded onto the spec branch unchanged (4e639bed90c61f1e8939d9b50aac2ae440463e4e). Review (cursor, gpt-5.6-sol-high): SHIP on round 1. Quiesce verification at f7cc5c0b5118af80dbd4af53dce4f9017422f221 as in task 1 (274 tests OK).

stage: wave-dispatch - ran [2 tasks, native worktrees, disjoint Touches, no join collision] (implementer: grok-4.6 via the CLI bridge, reviewed and committed by the worker)
stage: impl-review - ran [round 1 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 4e639bed90c61f1e8939d9b50aac2ae440463e4e
- Tests: PATH=/usr/bin:$PATH python3 -m unittest tests.test_banners tests.test_status, PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, quiesce at f7cc5c0: unittest 274 OK
- PRs: