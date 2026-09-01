---
satisfies: [R3, R5]
---
# fn-7-one-time-setup-privilege-and-helper.2 Worker stay-up and serialized reload

## Description
Keep the network worker accepting after one `_run` exception (R3) and apply reloads one at a time so last-good writes do not interleave (R5).

**Size:** M
**Files:** distractions, tests/test_enforcement.py
**Touches:** [distractions, tests/test_enforcement.py]

### Approach
- In `NetworkWorker._loop`, catch `_run` exceptions after `_finish`, record generation failure, leave `started` as a live acceptor. Do not start a second worker.
- `on_distractions()` inside `_run` is a known raise site (`hyprctl_json`). That failure is a job failure, not thread death.
- Serialize the full `handle_reload_conn` transaction behind one in-process lock: load state, bump generation, apply rules, network enqueue and wait, determine the result. Do not lock only `apply_enforcement`. Do not reuse `LISTEN_LOCK` (that one excludes a second `listen()`).
- A failed reload leaves a consistent last-good. The next reload can retry.
- Add tests for a raising `_run` that still accepts a later job, and for two overlapping reload connections where the second cannot bump generation or apply until the first's full transaction finishes, and both receive the correct result.

### Investigation targets
**Required** (read before coding):
- `distractions:1562-1697` — `NetworkWorker` `_loop` / `_run` / `_finish`
- `distractions:1726-1774` — `apply_enforcement`, `handle_reload_conn` (one thread per accept)
- `distractions:938` — `_atomic_write` shared tmp name
- `tests/test_enforcement.py:522-652` — overlapping periodic skip and reload generation

**Optional:**
- `distractions:1853` — `reset_runtime_state` for tests
## Acceptance
- [ ] A raising network job reports failure for that generation and the worker accepts a later apply or lift
- [ ] Two overlapping reload connections wait on one lock that covers load, generation bump, apply, network wait, and result; the second cannot bump or apply until the first finishes
- [ ] Both reloads receive the correct result; a failed reload leaves a consistent last-good; the next reload can retry
- [ ] `python3 -m unittest discover -s tests` passes
## Done summary
NetworkWorker now records a failed `_run` and stays accepting on the same thread; overlapping reloads take one in-process lock across load, generation bump, apply, network wait, and result so last-good writes stay consistent.

stage: impl-review - ran (model: gpt-5.6-sol-high)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: faedd2b71604cda9174b06ac6e030f0e8a175dba
- Tests: python3 -m unittest tests.test_enforcement
- PRs: