---
satisfies: [R8, R9, R10]
---
# fn-9-rewrite-one-contained-distraction-space.1 Foundation: package skeleton, config, catalog, state, CLI dispatcher, test harness

## Description
Create `ds/` with `config.py` (schema, defaults, atomic load/save, dot-key get/set with validation, migration from `app-list.json` and `focus.json`), `catalog.py` (shipped `catalog.json` plus expansion of every list entry form into `{name, class, hosts, senders, audio}` with the automatic PWA class), `state.py` (`state.json`/`lock.json` shapes, state and runtime paths, atomic JSON), and the `distractions` argparse entry with every command wired to a stub that exits 2 'not yet'. `status --json` and `config`/`list`/`catalog` commands are real. Add `tests/` with the fake-binary-on-PATH harness and tests for config validation, migration, catalog expansion, and `status --json` shape.

**Files:** `distractions`, `ds/__init__.py`, `ds/config.py`, `ds/catalog.py`, `ds/state.py`, `catalog.json`, `tests/`.

## Acceptance
- `config get/set` validate every schema key including `hold_notifications`, `mute_sounds`, `summary` and refuse invalid values with exit 1 and an unchanged file.
- `list add/remove/expand` and `catalog` work; expansion emits the automatic PWA class.
- First run without the new file seeds `list` from old `app-list.json` + `focus.json` destinations, else the fifteen defaults.
- `status --json` prints the documented shape without a listener.
- `python3 -m unittest discover tests` passes.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
