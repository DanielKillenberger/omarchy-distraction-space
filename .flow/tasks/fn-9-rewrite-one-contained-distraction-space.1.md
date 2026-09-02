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
Foundation for the rewrite: the `ds/` package with `config.py` (schema, defaults, flocked `update()`, dot-key get/set, migration from `app-list.json` and `focus.json`), `catalog.py` (shipped `catalog.json` and expansion into `{name, classes, hosts, senders, audio}` with the automatic PWA class), `state.py` (state, lock, expansion shapes, XDG paths, live `status --json`), the thin `distractions` dispatcher holding the final command table (stubs exit 2 with "not yet"), contracted stubs for every wave-2 module, `tests/harness.py`, and 39 tests. The fifteen legacy test files were removed in this task rather than in task 8 because they load the replaced `distractions` script and would fail the suite from this commit on. Implemented by cursor-agent (cursor-grok-4.6-high) in an isolated worktree; the conductor committed and integrated.

stage: impl-review - ran [round 1 NEEDS_WORK (5 findings fixed in 7bb3046), round 2 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)

Record repair 2026-09-02: status replayed from this task's own Done summary and evidence after PR #9 merged; the fn-9 run's flow-state never reached main.
## Evidence
- Commits: 90c791f84d2eaaaa8a3a2f6d660b7153e38d76f9, 7bb304637cf7bfd1a1641142b2c7ce51cf75976f
- Tests: python3 -m unittest discover tests
- PRs: 9