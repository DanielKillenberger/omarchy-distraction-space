---
satisfies: [R1, R2, R3, R4, R6]
---
# fn-3-focus-mode-agent-notification-summary.2 Background parse and focus-off summary

## Description
Wire the one-shot from .1 into focus-on / focus-off (R1, R2, R3, R4, R6). Consume mute ping records. Do not implement mute, banners, or the grouped-count builder.

**Size:** M
**Files:** `distractions`
**Touches:** [distractions]

### Approach
- Hook `enable_focus()` after mute is applying. First blocked-ping record starts one closed-table one-shot (prompt = records + ledger file if present). Flock the result file like `listen()`.
- No CLI or notify reads that file while `is_focus()` is true (R2). Do not add a dump/status command for it.
- After a successful `disable_focus()`, wait once for the child (timeout then kill). Non-empty stdout → one `omarchy-notification-send` with a longer timeout than 4000 ms, and suppress the mute grouped-count notice for this session. Any fail, off, empty buffer, or missing agent → leave the mute grouped count as-is (R4, R6).
- `focus-off` argv/stdin runs the same chain. Focus-on again cancels the child and discards unread stdout.
- If the buffer grows after the child exits and focus is still on, a replacement parse may run.

### Investigation targets
**Required** (read before coding):
- `distractions:180-198` — `enable_focus()` / `disable_focus()` hooks
- `distractions:237-260` — flock singleton pattern
- `distractions:280-284` — `focus-off` argv/stdin path
- Parent spec §API Contracts ping-record shape (mute writes it)

**Optional** (reference as needed):
- `BarWidget.qml:26-31` — bar already skips a second Process
- `.flow/specs/fn-2-focus-mode-distraction-notification.md` — grouped-count ownership. Do not take over that spec.

### Key context
- fn-2 is in flight on another branch. This task consumes a record list. If the list is absent, treat it as empty (R4). Do not invent a second mute buffer and do not land network-block code.
- Ledger prompt text can be empty until .3 lands. .3 appends lines this task already passes through.

### Acceptance
- [ ] First ping while summaries are on starts one background one-shot. Failure notifies at focus-off (R1).
- [ ] No user-facing read of the running parse or result while focus is on (R2).
- [ ] Focus-off shows one summary on success, not each ping (R3).
- [ ] Off / no agent / empty buffer leaves grouped-count behavior unchanged (R4).
- [ ] Invoke, timeout, or display failure still lets the mute grouped count apply (R6).
- [ ] `python3 -m py_compile distractions` passes.

## Acceptance
- [ ] First ping while summaries are on starts one background one-shot. Failure notifies at focus-off (R1).
- [ ] No user-facing read of the running parse or result while focus is on (R2).
- [ ] Focus-off shows one summary on success, not each ping (R3).
- [ ] Off / no agent / empty buffer leaves grouped-count behavior unchanged (R4).
- [ ] Invoke, timeout, or display failure still lets the mute grouped count apply (R6).
- [ ] `python3 -m py_compile distractions` passes.

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
