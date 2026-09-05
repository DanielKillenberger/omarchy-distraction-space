---
satisfies: [R8, R9, R14]
---
# fn-22-the-space-is-a-process-group-one.2 Static network schedule, site_block.enabled, refresh verb, and the v3 schema

## Description
Removes every network action from the enter/leave path (R8), adds the switch (R9), the `refresh` verb, and the config, state, and catalog fields every later task reads (R14). Split as one task because listener, config, state, and catalog changes are small each and land together.

**Size:** M
**Files:** `ds/listener.py`, `ds/net.py`, `ds/config.py`, `ds/state.py`, `ds/catalog.py`, `catalog.json`, `distractions`, `tests/test_listener.py`, `tests/test_config.py`, `tests/test_status.py`, `tests/test_catalog.py`
**Touches:** [ds/listener.py, ds/net.py, ds/config.py, ds/state.py, ds/catalog.py, catalog.json, distractions, tests/test_listener.py, tests/test_config.py, tests/test_status.py, tests/test_catalog.py]

### Approach
- `ds/listener.py`: in `space()` delete the `flush()` on enter and the `request("workspace")` calls; in `enforce()`/`refresh()` delete the `self.prev is True → flush()` short-circuit so the real set is always resolved and applied; `PERIOD = 60.0`; `tick()` requests `periodic` regardless of `prev`. Add the socket verb `refresh` beside `reload` in the unix-socket protocol: it calls `request("refresh")` without `_read_cfg()`. Before any `net.apply(addrs)`, call `cgroup.ensure_slice()`. When `cfg["site_block"]["enabled"]` is false: one `net.apply([])` on start and reload, no resolution, state `site_block: "off"`. The `_APPLY` map, generation counter, and `_reply_waiters` stay so `distractions reload` keeps its reply contract.
- `ds/config.py`: `DEFAULTS` gains `site_block.enabled: True`, `browser: "auto"`, `open_links_in_space: True`, `containment: {"snap_back": True, "release_minutes": 30}`; `validate` accepts `browser` as `"auto"` or a non-empty list of non-empty strings, `release_minutes` a positive int. Follow the `_need()` pattern at `ds/config.py:143-172`; `is_schema_key`/`set_value` already walk dotted keys.
- `ds/state.py`: `status()` adds `links` (`on|off|displaced`, default `off`), `browser` (basename or `null`), `released` (dict, default `{}`); add `entries_path()`, `read_entries()`, `write_entries()` on the `read_json`/`write_json` helpers.
- `ds/catalog.py` + `catalog.json`: optional `desktop` per product (`Telegram: org.telegram.desktop`, `Signal: signal-desktop`); `expand_entry` carries `desktop` with `None` default; `_as_exp`/`read_expansion` default `desktop: None` for an on-disk v2 file.
- `distractions`: `refresh` subcommand mapped to a new `listener.cmd_refresh` mirroring `cmd_reload`.

### Investigation targets
**Required** (read before coding):
- `ds/listener.py:230-300` — `enforce`, `request`, `_launch`, `take_result`
- `ds/listener.py:344-406` — `flush`, `event`, `tick`, `space`, `reload`
- `ds/listener.py:24-52` — `cmd_listen` / `cmd_reload` socket protocol
- `ds/config.py:20-31,143-172,336-367` — DEFAULTS, validate, dotted keys
- `ds/state.py:141-155,193-211` — state readers, `status()`
- `ds/catalog.py:38-77` — `expand_entry`, `expand`

**Optional:**
- `tests/test_listener.py` — existing enter/leave pins to invert
- `tests/harness.py:150-160` — `batch_deadline_env` for constants

### Key context
- `distractions reload` waits on a generation reply; keep `take_result` and the waiter contract intact when removing the workspace branches.
- A v2 `config.json` and a v2 `expansion.json` on disk must load with every new key at its default.

## Acceptance
- [ ] A listener test pins zero wrapper calls and zero resolves across an enter and a leave, and one resolve per 60 s regardless of workspace
- [ ] `distractions refresh` triggers one resolve+apply without re-reading config; `reload` still re-reads and replies as before
- [ ] `site_block.enabled: false` yields one `flush`, no resolution, and `status --json` `site_block: "off"` while hold and mute keep working
- [ ] `config set browser '["brave"]'` validates; `config set browser '[]'` and `config set containment.release_minutes 0` are refused before the write
- [ ] `status --json` carries `links`, `browser`, `released`; a v2 config and v2 expansion load with defaults
- [ ] `catalog.json` Telegram and Signal carry `desktop`; expansion of a hosts-only product yields `desktop: null`
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes


## Done summary
Removed every network action from the enter and leave path (R8), added the `site_block.enabled` switch (R9), the `refresh` verb, and the version 3 config, state, and catalog fields (R14). Resolution now runs on start, reload, `refresh`, and every 60 s regardless of workspace, and every wrapper call starts the slice first.

### What changed (commits 1d17177, b5bd939; base babecbf; the worker's commit 1afd108 was cherry-picked onto the target as 1d17177)
- `ds/listener.py`: `space()` runs only the enter/leave hooks; `take_result` and `_follow` no longer drop or defer on the workspace; `PERIOD = 60.0`; `tick` requests `periodic` when the block is enabled; `refresh()` requests without `_read_cfg()`; `_apply()` wraps `net.apply` with `cgroup.ensure_slice()` for replace and flush alike. With `site_block.enabled: false`, `enforce` flushes once on start and reload and never resolves. `write_state` carries `links`, `browser`, `released` from `_Ctx` attributes later tasks set. The expansion carries `site_block.enabled`; `_as_exp` defaults it and `desktop: null` for a version 2 file. After review: a refused wrapper call replies `error` to whoever asked, `flush` returns whether the wrapper accepted it, `enforce` propagates that on the disabled path, and `refresh` with the block off retries a refused flush.
- `ds/config.py`: `DEFAULTS` gains `site_block.enabled`, `browser`, `open_links_in_space`, `containment.{snap_back,release_minutes}`; `validate` refuses a non-bool switch, a `browser` that is neither `"auto"` nor a non-empty argv of non-empty strings, and a `release_minutes` below 1.
- `ds/state.py`: `status()` adds `links`, `browser`, `released`; `entries_path`/`read_entries`/`write_entries`.
- `ds/catalog.py` + `catalog.json`: `desktop` per product (Telegram, Signal), `None` otherwise.
- `distractions`: `refresh` subcommand.
- Tests: listener (fake `systemctl`, enter/leave pins, periodic resolve on the space, refresh vs reload, block disabled, mid-batch enter, failed batch, v2 expansion, wrapper refusal on both paths via a file-toggled fake sudo), config, status, catalog.

### Review
cursor / gpt-5.6-sol-high, two rounds: round 1 NEEDS_WORK (apply failures replied ok), round 2 SHIP with R8, R9, R14 met.

### Side effect worth knowing
`sync_hold`'s unavailable-retry shares `PERIOD`, so it retries once per 60 s instead of 30 s. Docs still describe the version 2 schedule; task .9 owns them.

### Gates
- baseline: green via handoff (6a1f7011)
- verify: `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at b5bd939 on the integrated target (with .7), 322 tests, OK; receipt `.flow/tmp/green-receipts/b5bd9393-unittest.json`
- classify: FULL

stage: impl-review - ran (cursor gpt-5.6-sol-high, 2 rounds, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 1d17177, b5bd939
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 322 tests at b5bd939 on the integrated target; receipt .flow/tmp/green-receipts/b5bd9393-unittest.json), PATH=/usr/bin:$PATH python3 -m unittest tests.test_listener tests.test_config tests.test_status tests.test_catalog
- PRs: