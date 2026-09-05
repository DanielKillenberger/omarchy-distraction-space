---
satisfies: [R7]
---
# fn-22-the-space-is-a-process-group-one.1 Slice unit, cgroup helper, and the wrapper's cgroup accept rule

## Description
Lands the process boundary itself (R7) and proves the parked unknown about `socket cgroupv2 level 5` under root. Split first because every other task reads the slice through the helper this one creates.

**Size:** M
**Files:** `distractions-nft`, `ds/cgroup.py` (new), `install/app-distraction.slice` (new), `ds/setup.py`, `tests/test_nft.py`, `tests/test_cgroup.py` (new)
**Touches:** [distractions-nft, ds/cgroup.py, install/app-distraction.slice, ds/setup.py, tests/test_nft.py, tests/test_cgroup.py]

### Approach
- `distractions-nft`: `render_table` emits `socket cgroupv2 level 5 "<path>" accept` as the first rule of `output` and of `output_nat`, before the splice source-port accepts (memory `bug/security/source-port-exemption-must-sit-above-2026-09-02` pins that ordering discipline). Path is `user.slice/user-<uid>.slice/user@<uid>.service/app.slice/app-distraction.slice` with uid taken from `SUDO_UID` only; missing or non-numeric is `_fail("refused: no invoking uid")`. Before `commit`, check `<cgroup-root>/<path>` is a directory (root from env `DS_CGROUP_ROOT`, default `/sys/fs/cgroup`) and `_fail("refused: slice cgroup missing", 1)` otherwise. Stdin grammar, `MAX_STDIN_BYTES`, `MAX_ADDRESSES`, and table confinement stay byte-for-byte (fn-21).
- New `ds/cgroup.py`: `SLICE = "app-distraction.slice"`, `slice_path(uid)`, `cgroup_of(pid, proc=None)` reading the `0::` line, `in_slice(pid)`, `ancestor_in_slice(pid, hops=8)` walking `/proc/<pid>/stat` ppid parsed from the last `)` (the comm can contain spaces), `ensure_slice()` running `systemctl --user start app-distraction.slice`. Every read follows the `_stat_fields` pattern at `ds/hold.py:426-433` and returns None/False on `OSError`. Honor the `DS_PROC_ROOT` override the way `ds/feedback.py:64-65` does.
- `install/app-distraction.slice`: `[Unit]` with a description, empty `[Slice]`. `ds/setup.py` gains `sync_slice()` (copy to `$XDG_CONFIG_HOME/systemd/user/`, `systemctl --user daemon-reload`, `start`) called from `install()` after `_root_transaction`, and `remove_slice()` (`stop`, delete) called from `remove()` before the root teardown. No root, no second sudo prompt.
- Manual proof on this machine, recorded in the task summary: `printf '1.2.3.4\n' | sudo -n /usr/local/libexec/omarchy-distraction-space/distractions-nft replace ds` after `systemctl --user start app-distraction.slice`, then `sudo nft list table inet omarchy_ds` shows the cgroup rule first, and `curl` to a listed host succeeds from `systemd-run --user --scope --slice=app-distraction.slice curl ...` and is refused from a plain shell.

### Investigation targets
**Required** (read before coding):
- `distractions-nft:65-146` — `render_table`, `parse_replace_stdin`, `commit`, `main`
- `ds/hold.py:426-433` — `_stat_fields` proc-read pattern
- `ds/setup.py:613-666` — `install()` / `remove()` ordering
- `tests/test_nft.py:1-40` — `SourceFileLoader` load and `FAKE_NFT`

**Optional:**
- `tests/harness.py:16-97` — `Sandbox`, `fake_bin`

### Key context
- nftables resolves the cgroup path to a kernel id at load time; a missing directory fails the load, a recreated cgroup silently stops matching. That is why the slice is a persistent unit and why the wrapper checks the directory first.
- `systemctl --user` must run as the person, never through sudo.

## Acceptance
- [ ] `render_table` output starts each chain with the cgroup accept rule; a test pins the order against the splice and reject rules
- [ ] Missing or non-numeric `SUDO_UID` is refused before any `nft` call; missing slice cgroup directory exits 1 with `refused: slice cgroup missing`
- [ ] fn-21 tests in `tests/test_nft.py` and `tests/test_setup.py` pass unchanged
- [ ] `ds/cgroup.py` covered by `tests/test_cgroup.py`: in-slice pid, ancestor within 8 hops, ancestor beyond 8 hops, unreadable cgroup file, comm with spaces in `/proc/<pid>/stat`
- [ ] `setup` installs and starts the slice unit; `setup --remove` stops and deletes it; both idempotent on a second run
- [ ] Root apply verified on this machine and the observed `nft list` output pasted into the done summary
- [ ] `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` passes


## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
