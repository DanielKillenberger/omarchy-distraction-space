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
Landed the process boundary for R7: `distractions-nft` renders `socket cgroupv2 level 5 "<slice>" accept` as the first rule of both chains, derives the slice path from `SUDO_UID` alone, and refuses to run when the slice cgroup directory is missing; `ds/cgroup.py` reads slice membership from `/proc`; `install/app-distraction.slice` is installed, started, stopped, and removed by `setup`.

### What changed (commits 53c409d, 84ca58d, 6a1f701; base c29e022)
- `distractions-nft`: `slice_path(uid)`, `_invoking_uid()` (ASCII digits only; else exit 2 `refused: no invoking uid`), `_require_slice()` (`DS_CGROUP_ROOT` or `/sys/fs/cgroup`; missing directory exits 1 `refused: slice cgroup missing`). `render_table(v4, v6, cgroup)` takes the path; the fn-21 stdin grammar, caps, and table confinement are unchanged. Both verbs carry the rule and the check.
- `ds/cgroup.py`: `SLICE`, `SLICE_LEVEL`, `slice_path`, `cgroup_of`, `in_slice`, `ancestor_in_slice(pid, hops=8)`, `systemctl_user`, `ensure_slice`. `/proc` reads follow `hold._stat_fields`; `DS_PROC_ROOT` honored.
- `ds/setup.py`: `sync_slice()` after the root transaction; `remove()` order is now sync slice, flush, `remove_slice()`, root teardown, so a manager failure leaves the wrapper and grant for a retry. A second remove skips the root half when the wrapper and its record are both gone, so it succeeds after the passwordless grant is removed.
- Tests: `tests/test_nft.py` (rule order, uid derivation and refusal, missing-slice refusal), `tests/test_cgroup.py` (new), `tests/test_setup.py` (fake `systemctl` that refuses start/stop of a unit without a file; install idempotent; remove ordering, stop failure keeps root files, missing unit restored for the flush, second remove with sudo denied). Per-test env cleanup ends the `DS_VISUDO_LOG`/`DS_VISUDO_FAIL` leak from the setup tests into the clone tests.

### Review
cursor / gpt-5.6-sol-high, three rounds: round 1 NEEDS_WORK (remove ordering P1, second-remove idempotency P2), round 2 NEEDS_WORK (second remove still called sudo), round 3 SHIP with R7 met.

### Touches deviation (declared)
`tests/test_clone.py` gained a fake `systemctl` so existing `setup.install()` tests never reach the real user manager. Test-only.

### Left open, recorded here on purpose
- Root verification on this machine (the AC's privileged apply and the slice-vs-shell reachability check) needs an interactive sudo password the run cannot supply. The conductor has asked the person to run it; the result is to be recorded in the spec's Parked unknowns before task .3 starts, per the early proof point.
- Sibling note for fn-22.2 in the run notes: the listener must `ensure_slice()` before every wrapper call, `flush` included.

### Gates
- baseline: green (293 tests, pre-edit)
- verify: green, `PATH=/usr/bin:$PATH python3 -m unittest discover -s tests` at 6a1f701, 309 tests; receipt `.flow/tmp/green-receipts/6a1f7011-unittest.json`
- classify: FULL

stage: impl-review - ran (cursor gpt-5.6-sol-high, 3 rounds, SHIP)
stage: plan-sync - skipped(config: planSync.enabled != true)
## Evidence
- Commits: 53c409d0f41dc4153ae07c8594df7b0d49a8616f, 84ca58d, 6a1f701
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests (verify: green, 309 tests at 6a1f701; receipt .flow/tmp/green-receipts/6a1f7011-unittest.json), PATH=/usr/bin:$PATH python3 -m unittest tests.test_setup tests.test_clone tests.test_nft tests.test_cgroup (56 tests, OK, in this order)
- PRs: