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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
