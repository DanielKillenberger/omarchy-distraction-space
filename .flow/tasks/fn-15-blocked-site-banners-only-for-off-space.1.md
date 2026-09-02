---
satisfies: [R1, R2, R3, R5]
---
# fn-15-blocked-site-banners-only-for-off-space.1 Origin-aware banners: pid walk, entry fallback, per-entry debounce

## Description
In ds/feedback.py attribute each redirected connection to a process via /proc/net/tcp{,6} and /proc/<pid>/fd, walk PPid up to eight steps to a pid owning Hyprland clients (helpers in ds/hypr.py reading hyprctl clients -j with a one-second cache), decide on-space vs off-space, apply the host-to-entry fallback through the active expansion, and debounce per entry name. Fail toward showing the banner. Tests in tests/test_feedback.py and tests/test_hypr.py use fixture directories standing in for /proc and the existing fake hyprctl.

**Touches:** ds/feedback.py, ds/hypr.py, tests/test_feedback.py, tests/test_hypr.py

## Acceptance
R1, R2, R3 of the parent spec hold with tests; the live check in R5 is recorded by the conductor after merge.

## Done summary
Redirected TLS connections are now attributed to a process (peer port -> /proc/net/tcp{,6} inode -> /proc/<pid>/fd owner -> PPid walk of up to eight hops to a pid owning Hyprland clients) and a banner is shown only for off-space or unattributable origins; the host-to-entry fallback rescues a shared browser process whose own matching windows all sit on the distraction space, and banners are debounced per catalog entry name with the body naming the entry.

Implementer: Grok (grok-4.6) through the `grok --always-approve --no-plan` bridge, one pass, killed at the 10-minute wall after it had written all four files and while it was running tests; the host verified the edits, fixed the PPid walk to follow eight hops (Grok's `range(8)` counted the start pid, so seven), simplified the `_write_proc` fixture helper, and added the eight-hop boundary case. Design note: R2's fallback is applied only when the walked-to owner pid itself owns a window matching the entry's classes; the literal spec wording would also silence `curl https://x.com` from a terminal while the X web app is open, contradicting the R5 live check. HTTP (28080) still shows the block page with no banner, as before.

Files: ds/feedback.py (attribution, DS_PROC_ROOT, per-entry debounce, rate-limited log), ds/hypr.py (clients_cached, entry_for_host, entry_clients_on_space, _class_matches), tests/test_feedback.py (+8 tests, /proc fixture helper, fake hyprctl in setUp), tests/test_hypr.py (+3 tests). README unchanged (banner body not quoted there).

Gates: baseline green (226 tests at ba656c0); after: 237 tests, rc=0 via `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests > .flow/tmp/suite2.log 2>&1`. R5 live check is the conductor's after merge.

stage: impl-review - ran (model: claude-opus-5 via host backend, read-only subagent; SHIP, 5 non-blocking findings: two P2 performance notes recorded as follow-ups in the spec)
stage: plan-sync - skipped(config: planSync.enabled != true)
stage: wave-join - ran (fn-15.1 on the spec branch, fn-15.2 merged at c108692, no collision; integrated suite 239 tests OK)

Live check (conductor, 2026-09-02, after PR #16 installed): listener restarted with `nudges.block_page` back on; status read `notification_hold: on` straight from start (task 2's retry). `curl https://x.com` from the terminal running this session on workspace 1 was refused (rc 35) and, per the design, should raise the X banner; the X web app polling from the distraction space should raise none. User observation recorded below by the conductor when reported.

## Evidence
- Commits: 6915e28d26559812c6ed5b68fe1d00f0a09b66cb
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests > .flow/tmp/suite2.log 2>&1, PATH=/usr/bin:$PATH python3 -m unittest tests.test_feedback tests.test_hypr > .flow/tmp/focused3.log 2>&1, baseline: green (226 tests at ba656c0); after: 237 tests, rc=0, python3 -m unittest discover -s tests
- PRs: