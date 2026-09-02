---
satisfies: [R3]
---
# fn-20-banner-provenance-for-blocked-site.2 distractions banners: print the latest provenance lines

## Description
Add a `banners` subcommand to the `distractions` CLI (the argparse builder and COMMANDS table in the `distractions` script) that prints the most recent banner provenance lines from the state log, newest first, 20 by default, with `--count N` (positive integer; argparse rejects the rest). Lines are those whose text after the timestamp starts with `banner: `; the format task 1 writes is `<iso> banner: host=<host> entry=<entry|-> port=<n> pid=<n|-> exe=<basename|-> class=<class|-> ws=<workspace|-> decision=<reason>[ dropped=<n>]` written through the existing state-log helper (hypr._log, which prefixes the ISO timestamp). Field values never contain whitespace: replace any whitespace run in a value with `_`; an absent value is `-`. `decision` is one of `shown`, `debounced`, `on-space`, `entry-on-space`, `unattributed`. Print each matching line verbatim (timestamp included). An absent or empty log prints nothing and exits 0. Implement `cmd_banners` in ds/state.py next to cmd_status, reading `state.state_path("log")` with the same tolerance as the rest of the module (missing file, unreadable file -> nothing, exit 0; decode with errors="replace"). Add a row to the README Commands table. Tests in a new tests/test_banners.py using tests/harness.py's Sandbox: a log with mixed lines yields only banner lines newest first and honours --count; empty and missing logs exit 0 with no output; invalid --count exits 2. Do not touch ds/feedback.py (task 1 owns the writer).

**Touches:** distractions, ds/state.py, tests/test_banners.py, README.md
