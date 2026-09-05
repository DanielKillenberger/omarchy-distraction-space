I have everything I need: spec, both tasks, both prior reviews, the fn-25 hunks of the diff, the current `ds/hypr.py`/`ds/launch.py`/`distractions` source, the `ui`/`cgroup`/FakeProc contracts they depend on, and the listener scan test. No further reads required.

## Review: fn-25 spec completion (f0cc79a → 286953d9)

### Scope note

The diff covers the whole fn-25/26/27 integration branch. I reviewed the fn-25-owned surfaces (`ds/launch.py` target resolution and `_open_web`, `ds/hypr.py` adoption/migration, `distractions` wiring, `tests/test_hypr.py`, `tests/test_launch.py`, the adoption scan expectation in `tests/test_listener.py`, and the README/internals wording that describes them). The browser portal-scope trampoline (`_BROWSER_APP_IDS`, `_launch_browser_in_slice`) in the same `ds/launch.py` hunk is owned by fn-26.3 per `.flow/tasks/fn-26-visible-health-and-accessible-v3.3.md:9`; I only checked that it does not disturb the R1 path (it doesn't: `_open_web` still passes `profile_flags(target.url)` verbatim, `ds/launch.py:612`).

### Requirement map

| R-ID | Implementation | Tests | Live evidence |
|---|---|---|---|
| R1 | `Target.explicit_url` (`ds/launch.py:69`), set for scheme-bearing args (`:209`), reuse skipped at `:605`; raw URL to `profile_flags` at `:612` | `test_explicit_same_host_urls_are_delivered_intact` (two same-host URLs with query/fragment/percent-encoding, with and without a matching window); `test_launch_reports_a_browser_that_did_not_start` now has a matching `youtu.be` window and still exits 1 for missing binary and failed start | None; spec/task define success as accepted invocation, not navigation |
| R2 | `_entry_target` leaves `explicit_url=False` (`:184-191`) so name opens reach `focus_existing` (`:579-600`); `forward()`, `_url_host`, `pick_browser is None` untouched; `open_target` has no lock gate before or after (`:699-723`) | `test_existing_profile_window_is_focused_instead_of_relaunched` (now `open YouTube`); existing forward/malformed/absent-launcher tests unchanged; new test asserts no workspace focus dispatch for explicit URLs | None required; lock semantics untouched |
| R3 | `_adopt` (`ds/hypr.py:602-628`) only dispatches `hl.dsp.window.move`; `close_window_lua` deleted, zero references repo-wide; released/snap-back checks precede `classify` (`:547-552`); failed move → "Window could not be moved" once, retried on next event (`:618-619`) | `test_foreign_discovery_moves_and_offers_once_without_opening_or_closing` (openwindow, movewindow, reload rescan → 3 moves, 1 offer, 0 opens); `test_foreign_failed_move_reports_and_retries_without_launch`; `test_released_window_skips_every_layer…` includes `FOREIGN_WA`; `ScanTests.test_scan_applies_all_three_layers_to_existing_clients` asserts move of `0xc` and "discovery never launches a replacement" | None; fake hyprctl only |
| R4 | Offer body names separate profile and untransferable unsaved state (`:621-627`); `cmd_migrate` (`:644-670`) revalidates identity before and after `ui.select`, cancel → 0 with no `_open`, failure → 1, success notice tells the person to save before closing it themselves; no dispatch on any branch | `test_migration_cancel_failure_and_success_preserve_original` (cancel/fail/success/`Unavailable`/missing CLI, `_dispatches() == []` throughout, prompt contains "separate" and "unsaved"); `test_migration_refuses_vanished_reused_or_changed_window_before_and_after_prompt`; `test_adopt_skips_migration_offer_when_identity_is_unavailable` | Not verifiable offline (see nonblocking 2) |
| R5 | — | All of the above; fixtures are fake `hyprctl`, fake `omarchy-notification-send`, fake `distractions` CLI, fake `/proc` (`DS_PROC_ROOT`) | Conductor: 89 focused / 409 combined green; no live desktop changes |

Boundaries hold: nothing in the adoption/migration path touches `cgroup`, `nft`, or the slice; moving a foreign window changes neither process membership nor network policy. Cross-spec contract holds: migration is a notification action (`ui.notify(action=[CLI, "migrate", address, identity])`, same argv convention as `ds/feedback.py:698`), no main-menu edit by fn-25, no listener scheduling change in `ds/hypr.py`. Documentation deferred by both task reviews is now done in this range: README "Upgrading from 2.x", "Windows stay on one workspace", "Links open in the space", the `open` and new `migrate` command rows, and `docs/internals.md:19,51`.

### Correctness checks that passed

- `/proc/<pid>/stat` starttime: `rpartition(")")[2].split()[19]` is field 22 (`starttime`) after the three fields consumed by pid/comm handling; comm with parentheses is safe via `rpartition`. FakeProc writes 54 post-comm fields so the index resolves in tests and in real `/proc` (52 fields).
- Dedup record `(identity, failed)`: fail→fail is silent, fail→success emits the offer, snap-back re-move after a manual drag does not re-offer, `closewindow` pops the key so a reused address gets a fresh offer (`:710-712`). `_reset_for_tests` clears `_adopted`.
- `ui.notify` serializes a list action as separate argv items after `--exec` (`ds/ui.py:86-87`), which is what the tests index as `action[2]`/`action[3]`.
- `ui.select` returns index or `None` and raises `ui.Unavailable` on a non-1 exit (`ds/ui.py:51,65-70`); `cmd_migrate` handles all three.

### Findings

**Blocking:** none.

**Nonblocking, ranked**

1. **Offer may never arrive when `openwindow` precedes the client listing** — `ds/hypr.py:719-727` → `_adopt:611,620`. Trigger: `_client_by_address` returns `None` on `openwindow`, client falls back to `{"address": address}`, no pid → identity `None` → window moved, record `(None, False)` stored, no offer (correct per fn-26.2's "no unanswerable question"). If no later `movewindow`/rescan arrives, the person has a moved window with no migration path except closing it themselves. Fix: one bounded re-fetch of the client after a successful move before deciding on the offer. Edge case dependent on hyprctl lag; not a spec violation.
2. **`HYPRLAND_INSTANCE_SIGNATURE` in the identity** — `ds/hypr.py:596`. If the listener's and the notification-exec environment's values differed, every `migrate` would report "disappeared or changed". Failure mode is safe (nothing launched, nothing closed), and the existing `enter` action already relies on the same exec environment, but this is live-only. Recommend one manual smoke of the notification action when the integrated branch is next exercised on the desktop. Unavailable live verification, not an implementation defect.
3. **Two notifications on first discovery** — a moved foreign window raises both the Opened banner (`contain:568-569`) and the "Keep your … window" offer. Acceptable under the spec; could be merged into one notice later.
4. **No parser test for `migrate`** — `distractions:77-79`. Consistent with the repo's other subcommands; a one-line `build_parser().parse_args(["migrate", a, i])` check would close it.
5. Cosmetic: the "Window could not be moved" notice omits `glyph=GLYPH` (`ds/hypr.py:619`) unlike the offer.

### Prior findings (re-review status)

- fn-25.1 #1 docs out of date → **fixed** (README `open` row, "Links open in the space"; `docs/internals.md:19`).
- fn-25.1 #2 assert non-interaction with existing window → **not-fixed**, optional as stated; nonblocking.
- fn-25.2 #1 question with no action when identity is `None` → **fixed** (`elif identity:` at `:620`, covered by `test_adopt_skips_migration_offer_when_identity_is_unavailable`); residual "no offer at all" edge recorded above as #1.
- fn-25.2 #2 signature consistency → **not-fixed**, live-only; carried as #2.
- fn-25.2 #3 parser test → **not-fixed**, nonblocking; carried as #4.
- fn-25.2 #4 docs describe old adoption → **fixed** (`README.md:62,44`, `docs/internals.md:51`).
- fn-25.2 #5 glyph → **not-fixed**, cosmetic.

### Verdict

R1–R5 are implemented and covered by offline regressions using fakes only; no code path can close a window; boundaries and the cross-spec contract hold; deferred docs are landed. Remaining items are edge-case hardening and one live-only check with a safe failure mode.

<verdict>SHIP</verdict>