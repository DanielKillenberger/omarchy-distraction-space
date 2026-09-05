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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
