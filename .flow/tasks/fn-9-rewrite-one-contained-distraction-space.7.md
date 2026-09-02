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
`ds/listener.py` is the one long-running process: single-instance flock, config load with the `expansion.json` fallback (rewritten after every successful load or reload, invalid-config notice once per run), `hypr.apply_rules` and a scan of existing clients, one select loop over Hyprland socket2, the reload socket, resolver results, and a one-second tick. Workspace transitions are driven from parsed socket2 events in order with tick reconciliation (`None` from hyprctl is unknown), and the listener alone runs the `enter`/`leave` hooks and the expiry `unlock` hook. Network sync is generation-tagged: one running job, a rerun flag that coalesces overlapping requests, stale-generation drop, an `on_space` recheck on the main loop right before `net.apply`, flush on entering the space, failed batches keeping current enforcement, and reload clients held non-blockingly (buffer cap, deadline budgeted for an active batch plus one coalesced follow-up) until their generation is applied so `ok` means applied. Feedback servers follow `nudges.block_page`; SIGTERM shuts down through `net.shutdown()` so a hanging resolver never blocks exit. `listen` and `reload` are real. Implemented by cursor-agent (cursor-grok-4.6-high) in an isolated worktree; the conductor committed and integrated.

stage: impl-review - ran [round 1 NEEDS_WORK (7 findings fixed in 440d92c), round 2 NEEDS_WORK (2 fixed in b19463f), round 3 NEEDS_WORK (1 fixed in e3a6df3), round 4 SHIP] (model: gpt-5.6-sol-high via cursor)
stage: plan-sync - skipped(config: planSync.enabled != true)

Record repair 2026-09-02: status replayed from this task's own Done summary and evidence after PR #9 merged; the fn-9 run's flow-state never reached main.
## Evidence
- Commits: 5fa1547de752f7373369e583120f40e25646f4e8, 440d92cc57a8357ed496d1b6805a3e57e61c0269, b19463fd5acaa670aaea4a97c15e08095fdec76e, e3a6df3d5d0c21c6d7332191dd1ae1faf90120b4
- Tests: python3 -m unittest discover tests
- PRs: 9