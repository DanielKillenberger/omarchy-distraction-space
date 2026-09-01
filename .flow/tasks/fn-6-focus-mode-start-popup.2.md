---
satisfies: [R2]
---
# fn-6-focus-mode-start-popup.2 Session timer auto-disable

## Description
Arm and fire the session timer from the Hyprland listener so elapsed minutes turn focus off without the 50-character reason, and purpose reaches the disable log (R2).

**Size:** M
**Files:** distractions, tests/test_focus_timer.py
**Touches:** [distractions, tests/test_focus_timer.py]

### Approach
- On the listener select loop (`listen()` already ticks ~1s), compare persisted wall-clock deadline to wall time. Do not use `now()` (monotonic) as the deadline clock.
- When the deadline is due and focus is on, start a detached helper command for timer-off. Do not run zenity or `_disable_focus_locked` on the listen thread.
- Timer-off calls the disable apply path without `MIN_REASON`. Every disable log line (timer and hand-off) includes the active purpose. Timer lines also include a timer marker. Hand-off still goes through `prompt_reason` then `disable_focus()`.
- If leave-reason is open when the deadline fires, timer disable wins. A later confirm of an already-off session is a no-op.
- Listener restart (already-on branch) resumes the persisted **active** deadline. After successful disable, disarm the deadline on active. Do not delete recap_pending. A missing, corrupt, or truncated active record does not timer-disable.
- Bar icon stays the eye. Do not drive the timer from `BarWidget.qml`'s 2s poll.

### Investigation targets
**Required** (read before coding):
- `distractions:4033-4102`  - `listen()` select loop and already-on re-apply
- `distractions:1186-1187`  - monotonic `now()` (not the deadline clock)
- `distractions:3936-3993`  - `disable_focus` / `_disable_focus_locked` / `MIN_REASON`
- `distractions:37` / `distractions:109`  - `STATE_DIR` runtime files
- `distractions:2233-2246`  - `write_private_atomic` for clear/replace
- `distractions:4111-4132`  - argv including `focus-off`

**Optional:**
- `tests/test_notification_count.py:212-218`  - disable still emits the off toast
- `BarWidget.qml:66-86`  - eye icon and status poll

### Key context
A zenity call on the listen thread stalls socket2 and DNS ticks. Detach the timer-off helper the way the bar launches `focus`.
## Acceptance
- [ ] Elapsed deadline turns focus off without a 50-character reason (R2)
- [ ] Disable log line includes the session purpose and a timer marker (R2)
- [ ] Hand-off `disable_focus` with a 50-character reason also appends the active purpose to the log (R2)
- [ ] Hand-off still requires `prompt_reason` / `MIN_REASON`
- [ ] Listener restart with a future persisted deadline does not disable immediately; a past deadline does
- [ ] Missing, corrupt, or truncated session record does not timer-disable
- [ ] After timer disable, recap_pending is still present (task 3 consumes it)
- [ ] Timer-off does not run on the listen thread (detached helper or equivalent)
- [ ] Already-off timer confirm is a no-op
- [ ] Eye icon unchanged
- [ ] `python3 -m unittest tests.test_focus_timer tests.test_focus_start tests.test_summary_session` is green
- [ ] `python3 -m py_compile distractions` is green
## Done summary
The Hyprland listener compares the persisted wall-clock deadline on each select tick and detaches focus-timer-off when it is due. Timer-off skips the 50-character reason, logs purpose plus a timer marker, disarms the active deadline, and leaves recap_pending. Hand-off still requires MIN_REASON, binds to the activation nonce that opened leave-reason, and appends the active purpose. An already-off confirm is a no-op.

stage: impl-review - ran host gpt-5.6-sol-high SHIP (4 rounds; receipt /tmp/impl-review-receipt-fn-6-focus-mode-start-popup.2.json)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 1d336eb78cd2881ae0926632f06cb365dd837d84, 3b65c3cf2642af3010f99a37ec7e98dd358ffb8f, 7d836347e29e8584c5a73e5d56643d08d775b010, 4bc72070ca321df9b5b0b2a1320ceabeac3bd738
- Tests: python3 -m py_compile distractions, python3 -m unittest tests.test_focus_timer tests.test_focus_start tests.test_summary_session, review: /tmp/impl-review-receipt-fn-6-focus-mode-start-popup.2.json host gpt-5.6-sol-high SHIP
- PRs: