I have everything needed: the full diff, the surrounding `ds/hypr.py`, `ds/ui.py`'s `notify`/`select` contracts, `cgroup._proc_root`, the `FakeProc` stat layout, the listener scan fixture, the CLI dispatch, the existing `--exec` action form in `feedback.py`, and the doc lines that still describe the old behavior. No further reads are required.

## Review: fn-25-reliable-links-and-deliberate-window.2 (e1a3cf0 → cc6a601)

### What the change does

`ds/hypr.py:602-628` replaces the launch-then-close adoption with: move the foreign window intact (`move_to_space`), compute a bound identity (`ds/hypr.py:586-599`: `HYPRLAND_INSTANCE_SIGNATURE`, normalized address, pid, `/proc/<pid>/stat` starttime, class, initialClass, initialTitle, product name), and emit one notification per `(identity, failed)` record keyed by address. `cmd_migrate` (`ds/hypr.py:644-670`) revalidates the address/identity before and after an explicit `ui.select` confirmation, then runs `_open(name)`; every branch leaves the original window untouched. `close_window_lua` is removed entirely, so no code path can close a window. `distractions:29,77-79` wires the subcommand.

### Verification against R3–R5 and the task acceptance

- **R3 (move, no auto-close, startup/reload/repeated events, failed moves reported):** `_adopt` dispatches only `hl.dsp.window.move`; `close_window_lua` no longer exists (`Grep` confirms zero remaining references). The `(identity, failed)` record dedups repeated `openwindow`/`movewindow`/scan/`apply_rules`+`contain` (test at `tests/test_hypr.py:301-322` asserts three moves, one offer). A refused move notifies "could not be moved" once and retries on the next event without launching (`tests/test_hypr.py:324-337`). The listener scan test (`tests/test_listener.py:1351-1354`) now asserts a move for `0xc` and no `open` log. `closewindow` still pops the address (`ds/hypr.py:710-713`) so a reused address gets a fresh offer.
- **R4 (deliberate action, explains profile/unsaved state, cancel intact, failed launch never closes, success does not authorize closure):** Offer body and `select` prompt both mention a separate profile and untransferable unsaved state. Cancel (`None` or index 1) returns 0 with no `_open`. Failure returns 1 and notifies. Success notifies "Save your work before closing it yourself." The test at `tests/test_hypr.py:339-365` asserts `_dispatches() == []` across cancel/failure/success/`Unavailable`/missing-CLI — i.e., no close ever issued.
- **Identity binding/revalidation:** `_migration_target` re-fetches the client, re-runs `classify` (must still be `adopt`), and recomputes the identity. `tests/test_hypr.py:367-388` covers vanished window, reused address with a new pid, and class changed to the profile class, both before and during the prompt. The `/proc/<pid>/stat` index (`split()[19]` after the `)` partition) is the `starttime` field; the `FakeProc` fixture writes 50 trailing fields so the index resolves.
- **Network exemption / process boundary:** nothing touches cgroup, nft, or the slice.
- **Listener/menu untouched:** `ds/listener.py` and `ds/ui.py` are not in the diff; only the adoption-specific scan expectation changed, and all scheduling tests in `tests/test_listener.py` are preserved.
- **`--exec` action form:** `[CLI, "migrate", address, identity]` matches the existing `[_CLI, "enter"]` argv convention in `ds/feedback.py:697-698`.

### Findings

No introduced blocking defect. Nonblocking items, ranked:

1. **Offer notice can pose a question with no action** — `ds/hypr.py:620-627`. Trigger: an `openwindow` event where `_client_by_address` returns `None` (`ds/hypr.py:725-726` falls back to `{"address": address}`), so there is no pid, `_migration_identity` returns `None`, and the "Open the product in a separate distraction profile?" notice is sent with `action=None`. Impact: the person sees a question they cannot answer; a later full-client event does re-offer (the record changes from `(None, False)` to `(identity, False)`), but only if such an event arrives. Suggested fix: when `identity is None`, send a plain "moved to the space" notice (or skip) rather than the question, or re-fetch the client once before deciding. Edge case dependent on hyprctl lag; nonblocking.
2. **Identity depends on `HYPRLAND_INSTANCE_SIGNATURE` being identical in the listener and the notification daemon's exec environment** — `ds/hypr.py:596`. If they differed, every migrate action would report "disappeared or changed." Existing banner actions already run `hyprctl` from the same daemon environment and the listener already needs the signature for socket2 (`ds/listener.py:602`), so this is very likely consistent, but it is not verifiable from source. Unavailable live verification, not an implementation defect.
3. **No parser test for the `migrate` subcommand** — `distractions:77-79`. Nothing exercises `build_parser().parse_args(["migrate", addr, id])` dispatching to `hypr.cmd_migrate`. Consistent with the repo (no other subcommand has a parser test), so nonblocking; a one-line assertion would close the gap.
4. **Docs still describe the old close-and-reopen adoption** — `README.md:62`, `docs/internals.md:51`, and the "by adoption" phrasing in `README.md:68`. The parent spec defers shared docs to a single post-integration pass and fn-26.2 lists the migration/commands doc update, so this is an explicitly future task, not a defect here. Noting it so it is not lost.
5. Cosmetic: the "Window could not be moved" notice omits `glyph=GLYPH` unlike the offer notice (`ds/hypr.py:619`).

### Verdict

R3–R5 and all task acceptance items are met by the diff with test coverage for startup scan, reload/repeated events, snap-back-style re-moves, failed moves, vanished/reused/changed windows, cancellation, failed launch, and success without closure. Fixtures use fake `hyprctl`, `omarchy-notification-send`, and `distractions`; no real windows are touched.

<verdict>SHIP</verdict>