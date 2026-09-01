---
satisfies: [R1, R2, R6, R9]
---
# fn-9-rewrite-one-contained-distraction-space.7 Listener: wire containment, network, feedback, lock, and state together

## Description
Implement `ds/listener.py`, replacing the wave 1 stub: single-instance flock, config load that on a missing, unreadable, or invalid file notifies once and falls back to `expansion.json` (enforcing nothing when that is absent too), writing `expansion.json` after every successful load or reload, `hypr.apply_rules`, scan of existing clients, socket2 select loop with the reload socket (`reload\n`/`refresh\n` → `ok\n`/`error\n` after apply), one-second tick (lock expiry via `lock.expire_if_due()`, then notify and run the `unlock` hook; `state.json` write on change), generation-tagged network sync per the spec (one running job, rerun flag for coalescing, stale-generation drop, `on_space` recheck on the main loop right before `net.apply`, flush on entering the space), feedback servers per `nudges.block_page`, `enter`/`leave` hooks on every observed workspace transition (sole owner), clean shutdown that calls `net.shutdown()` so an in-flight resolution never blocks exit. `distractions listen` and `reload` become real. Integration tests drive the loop with a fake socket2 and fake binaries; `tests/harness.py` may be extended here.

**Files:** `ds/listener.py`, `tests/test_listener.py`, `tests/harness.py`.

**Touches:** [ds/listener.py, tests/test_listener.py, tests/harness.py]
## Acceptance
- A second `listen` exits silently; `reload` without a listener notifies and exits 1.
- Workspace change off-space triggers resolve+replace; entering the space triggers flush; `state.json` reflects each change.
- A resolution result whose generation is stale, or that lands after the person entered the space, is dropped and never reinstalls the block; overlapping requests coalesce into one follow-up job.
- Cold start with a corrupt config and an existing `expansion.json` enforces the cached expansion; reload with invalid config answers `error` and leaves enforcement unchanged; every successful load rewrites `expansion.json`.
- Shutdown (SIGTERM) with a hanging fake `getent` in flight exits within 3 s, leaving no child process.
- Lock expiry is observed within one tick and writes state, notifies, runs the `unlock` hook once; an observed enter and leave each run their hook exactly once.
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
