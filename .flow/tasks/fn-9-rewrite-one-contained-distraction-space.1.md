---
satisfies: [R8, R9, R10]
---
# fn-9-rewrite-one-contained-distraction-space.1 Foundation: package skeleton, config, catalog, state, CLI dispatcher, test harness

## Description
Create `ds/` with `config.py` (schema without any start-locked key, defaults, atomic load/save, `update(fn)` under an exclusive flock on `$XDG_RUNTIME_DIR/distraction-space.config.lock` with a 5 s timeout that refuses with exit 1 and "config busy", dot-key get/set with validation, migration from `app-list.json` and `focus.json`), `catalog.py` (shipped `catalog.json` plus expansion of every list entry form into `{name, classes, hosts, senders, audio}` where `classes` holds the native class when present plus the automatic PWA class `^chrome-<first-host>__.*$` for every host-bearing entry), `state.py` (`state.json`/`lock.json`/`expansion.json` shapes, state and runtime paths, atomic JSON), and the `distractions` argparse entry holding the final command table mapping every command to `ds.<module>.cmd_<name>`; a target raising `NotImplementedError` exits 2 with "not yet". Create `ds/hypr.py`, `ds/net.py`, `ds/feedback.py`, `ds/lock.py`, `ds/ui.py`, `ds/setup.py`, `ds/listener.py` as stubs carrying every signature from the spec's `ds.ui` and `ds.lock` contracts (including `ui.Unavailable`) so wave 2 tasks never touch the dispatcher or each other. `status --json` and `config`/`list`/`catalog` commands are real. Add `tests/harness.py` (fake-binary-on-PATH helper, temp HOME/XDG dirs) and tests for config validation, the flock, migration, catalog expansion, and `status --json` shape.

**Files:** `distractions`, `ds/__init__.py`, `ds/config.py`, `ds/catalog.py`, `ds/state.py`, stub modules, `catalog.json`, `tests/harness.py`, `tests/test_config.py`, `tests/test_catalog.py`, `tests/test_status.py`.

**Touches:** [distractions, ds/**, catalog.json, tests/harness.py, tests/test_config.py, tests/test_catalog.py, tests/test_status.py]
## Acceptance
- `config get/set` validate every schema key including `hold_notifications`, `mute_sounds`, `summary` and refuse invalid values with exit 1 and an unchanged file; `lock.start_locked` is not in the schema and is kept as an unknown key.
- Two concurrent `config set` processes on different keys both land; a held flock past 5 s refuses with exit 1 and "config busy".
- `list add/remove/expand` and `catalog` work; Telegram expands to `classes` with the native class and the PWA class, a hostname entry to one PWA class, a `class=` entry to one class and no hosts.
- First run without the new file seeds `list` from old `app-list.json` + `focus.json` destinations, else the fifteen defaults.
- `status --json` prints the documented shape without a listener.
- Every stubbed command exits 2 with "not yet"; `python3 -m unittest discover tests` passes.
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
