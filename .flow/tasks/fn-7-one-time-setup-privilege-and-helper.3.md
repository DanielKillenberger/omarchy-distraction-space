---
satisfies: [R4, R6]
---
# fn-7-one-time-setup-privilege-and-helper.3 Listen event isolation and notify OSError lock

## Description
One failed window query or move must not exit `listen()` (R4). Lock notify OSError absorb so listen stays up (R6).

**Size:** S
**Files:** distractions, tests/test_enforcement.py
**Touches:** [distractions, tests/test_enforcement.py]

### Approach
- Wrap `process_socket2_line` (or `handle_openwindow` / `handle_movewindow` / `silent_move`) so `CalledProcessError`, `JSONDecodeError`, and `OSError` (including `FileNotFoundError` and `PermissionError`) skip that event. The select loop and reload socket stay bound.
- `notify()` already absorbs TimeoutExpired, CalledProcessError, FileNotFoundError, and OSError at `distractions:245-259`. Add the missing OSError test next to `test_notify_absorbs_missing_and_nonzero`.
- Do not change banner copy or expand-map.

### Investigation targets
**Required** (read before coding):
- `distractions:1397-1468` — `client_by_address`, `silent_move`, `handle_openwindow`, `handle_movewindow`, `process_socket2_line`
- `distractions:245-259` — `notify()` absorb set
- `distractions:4033-4102` — `listen()` loop calling unwrapped `process_socket2_line`
- `tests/test_enforcement.py:439` — notify missing/nonzero

**Optional:**
- `distractions:1293-1348` — `apply_named_rules` already catches hyprctl fail for rules
## Acceptance
- [ ] One raising query or move (`CalledProcessError`, `JSONDecodeError`, or `OSError`) skips that event; later socket2 lines and reload accepts still run
- [ ] `notify()` OSError is absorbed and covered by a test
- [ ] `python3 -m unittest discover -s tests` passes
## Done summary
`process_socket2_line` now skips a window query or move that raises `CalledProcessError`, `JSONDecodeError`, or `OSError`, so later socket2 lines and reload accepts still run. `notify()` OSError absorb is covered next to the existing missing/nonzero test (R4, R6).

stage: impl-review - ran (model: gpt-5.6-sol-high)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: b972ba551db56faa2f013e8e2f4dcec59056556a
- Tests: python3 -m unittest tests.test_enforcement, python3 -m unittest discover -s tests
- PRs: