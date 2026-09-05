---
satisfies: [R10, R11]
---
# fn-22-the-space-is-a-process-group-one.5 Feedback: two banner kinds, one debounce table, attribution machinery removed

## Description
Collapses the banner code to the two kinds the spec names (R10) and deletes the attribution and provenance apparatus (R11). Runs before the windows task so that task can call the new banner API instead of the old one.

**Size:** M
**Files:** `ds/feedback.py`, `ds/state.py`, `tests/test_feedback.py`, `tests/test_banners.py`
**Touches:** [ds/feedback.py, ds/state.py, tests/test_feedback.py, tests/test_banners.py]

### Approach
- Delete from `ds/feedback.py`: `_inode_for_port`, `_pid_for_inode`, `_ppid_of`, `_walk_to_hypr_owner`, `_attribute`, `_provenance`, `_prov_submit`, `_prov_writer`, `_prov_flush`, `_prov_at`, `PROVENANCE_PER_MIN`, `_PPID_WALK`, and the `peer_port` plumbing in `_tls_conn`/`_http_conn`.
- One `_banner_at` dict keyed by list entry name, `BANNER_DEBOUNCE_S = 60`, one lock.
- Public API: `opened(entry_name)` and `blocked(host)`. Both check `nudges` (`app_banner` governs Opened, `block_page` governs Blocked and the block page), the debounce, and `hypr.on_space()` (never raise while on the space; unknown → log and skip).
  - Opened: title `<Product> opened in the distraction space`, body `Super+Ctrl+Shift+D enters.`; when `lock.is_locked()` the body reads `Locked until HH:MM` and the action runs `distractions enter`, which shows the lock notice; otherwise the action runs `distractions enter`.
  - Blocked: title `Blocked here`, body `<Product> opens in the distraction space. Super+Ctrl+Shift+D enters.`, action `distractions open https://<host>/`.
- Log line written synchronously through the existing `_log`: `banner: host=<h> entry=<name> decision=shown|debounced` (Opened uses the product's first host or the class as `host`).
- Keep a thin `_maybe_banner(host)` that calls `blocked(host)` so `ds/hypr.py` keeps importing until the windows task replaces the call.
- `ds/state.py` `cmd_banners`: no filter change; tolerant of v2 lines.

### Investigation targets
**Required** (read before coding):
- `ds/feedback.py:20-60` — constants and debounce tables
- `ds/feedback.py:619-906` — the deletion range
- `ds/feedback.py:909-975` — `_maybe_banner`, `_tls_conn`, `_accept_loop`
- `ds/lock.py:310-317` — `_lock_notice` and `until` formatting
- `ds/ui.py` — `notify` with actions

**Optional:**
- `ds/state.py:229-243` — `cmd_banners`
- `tests/test_banners.py` — line-shape assertions to rewrite

### Key context
- The action command must reference the plugin's own `distractions` path, not a bare name; see how existing notifications build commands in `ds/ui.py`.

## Acceptance
- [ ] `grep -n 'peer_port\|_inode_for_port\|_walk_to_hypr_owner\|_provenance\|PROVENANCE_PER_MIN' ds/feedback.py` is empty and a test asserts the symbols are gone
- [ ] `blocked(host)` fires once, is debounced within 60 s, fires again after, and never fires while on the space; log lines carry exactly host, entry, decision
- [ ] `opened(entry)` respects `nudges.app_banner`, the lock body and action, and the on-space suppression
- [ ] `distractions banners --count N` prints v3 lines and still prints v2 lines from an old log
- [ ] TLS router still routes `pass_through` and `keep_reachable` per fn-18 tests; HTTP block page still served on 80
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes


## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
