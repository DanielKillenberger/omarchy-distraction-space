---
satisfies: [R1, R2, R6, R9]
---
# fn-9-rewrite-one-contained-distraction-space.7 Listener: wire containment, network, feedback, lock, and state together

## Description
Implement `ds/listener.py`: single-instance flock, config load with last-good fallback, `hypr.apply_rules`, scan of existing clients, socket2 select loop with the reload socket (`reload\n`/`refresh\n` → `ok\n`/`error\n` after apply), one-second tick (lock expiry, `state.json` write on change), network sync on workspace change and every 30 s off-space, feedback servers per `nudges.block_page`, enter/leave hooks on workspace transitions, clean shutdown. `distractions listen` and `reload` become real. Integration tests drive the loop with a fake socket2 and fake binaries.

**Files:** `ds/listener.py`, `distractions`, `tests/test_listener.py`.

## Acceptance
- A second `listen` exits silently; `reload` without a listener notifies and exits 1.
- Workspace change off-space triggers resolve+replace; entering the space triggers flush; `state.json` reflects each change.
- Invalid config on reload answers `error` and leaves enforcement unchanged.
- Lock expiry is observed within one tick and writes state, notifies, runs the hook.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
