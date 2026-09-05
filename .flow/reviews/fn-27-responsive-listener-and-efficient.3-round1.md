I have what I need: the sudoers grant is path-only (no argument restriction), so `check ds` needs no install change; the repo has no `unshare`-based test anywhere; and the client side (`ds/net.py`) does not yet call `check ds`, which is fn-27.2's job. Analysis follows.

## What the change does

`distractions-nft` gains a `check ds` verb that shares `replace`'s bounded address-only stdin, stats the SUDO_UID-derived slice before and after a fixed `nft -y list table inet omarchy_ds`, canonicalizes both the listing and the `render_table` output (whitespace, known priority aliases, sorted set elements, the two `reject` expansions), requires full token-for-token equality including rule order, and only then prints `{"dev","ino"}`. `list_policy` reads incrementally via `selectors` with a 1 MiB cap and a monotonic deadline, merges stderr, and SIGKILLs the session on every exit path. This matches `/tmp/fn27-2-design.md` closely.

## Verified correct (with evidence)

- **Argument/stdin confinement** — `distractions-nft:264-281`: `check` only reaches `check_policy` after `_invoking_uid`, `_read_stdin` cap, and `parse_replace_stdin`; `tests/test_nft.py:362-370` proves bad target, extra operand, `flush ruleset`, and both caps refuse without any nft call. Sudoers (`install/sudoers.omarchy-distraction-space:3`) is path-only, so no install change is needed.
- **Full-policy equality** — `canonical_policy` (`distractions-nft:227-244`) tokenizes per line so rule boundaries and order are preserved; `tests/test_nft.py:320-349` covers level, path, numeric-cgroup fallback, sport range, priority, hook, address, flags, extra chain/set, counter, comment, removed rule, replaced rule, swapped rule order, and malformed output. Set-element sorting only fires when every element parses as the right family with no duplicates, so anything unexpected falls through to a strict mismatch.
- **Identity** — `slice_identity` uses `follow_symlinks=False` + `S_ISDIR`; `check_policy:248-252` fails on before≠after; missing slice exits 1 before nft is invoked (`tests/test_nft.py:351-360`).
- **Bounded listing** — `list_policy:185-224`: read size is `min(64K, cap+1-len)`, so the cap is enforced during reading; EOF-then-hang, output flood, stderr flood, nonzero exit, invalid UTF-8, forked grandchild, and `Popen` failure all produce `SystemExit` with no stdout and a reaped child (`tests/test_nft.py:372-400`). `start_new_session` + `killpg` handles the grandchild case.

## Findings

### 1. Blocking — acceptance bullet 5 (real disposable-namespace test) is not implemented

- **Where:** `tests/test_nft.py` (diff adds only fake-`nft` tests); `Grep unshare|map-root-user` over the repo matches only the task file itself.
- **Trigger:** Task acceptance: "Real disposable namespace test applies/checks expected policy, mutates actual rule/table, detects drift, repairs and checks; host firewall untouched." The task description states root already confirmed `unshare --user --map-root-user --net` with `SUDO_UID=1000` and an existing slice works, so this is not "unavailable live verification" — it is an explicitly required, feasible test that was not written.
- **Impact:** Every rendering assumption in `check_policy:253-257` (`priority 0`/`-100`, `reject with icmp port-unreachable`, `reject with icmpv6 port-unreachable`, exact `meta nfproto … tcp sport` and `redirect to :N` spelling, quoted cgroup path) is currently proven only against a fake `nft` that echoes the wrapper's *own* expected text (`listed_policy()` at `tests/test_nft.py:304-310`). That is tautological with respect to real nft 1.1.6 output. If any spelling differs, `check` will fail closed forever, and fn-27.2 will treat the firewall as permanently unverifiable/degraded — a silent regression of the whole R3/R4 optimization. This is also the only place where "repairs and checks" and "host firewall untouched" can be demonstrated.
- **Required fix:** Add a test (skippable when `unshare`, `nft`, or the real slice directory is absent) that runs inside `unshare --user --map-root-user --net`, applies via `replace ds`, verifies `check ds` returns 0 with the real slice dev/ino, mutates the live table (e.g. `nft delete rule …` / `nft add rule …` / `nft delete table inet omarchy_ds`), asserts `check ds` exits 1 with empty stdout, re-runs `replace ds` and asserts `check ds` passes again. Assert host state is untouched by construction (all `nft` calls occur inside the child netns) and record the observed listing in the task summary.

### 2. Nonblocking — `killpg` after a successful reap has a PID-reuse hazard as root

- **Where:** `distractions-nft:217-224`.
- **Trigger:** On the success path `proc.wait(timeout=remaining)` reaps the child, then `finally` calls `os.killpg(proc.pid, SIGKILL)` on a possibly-recycled PID.
- **Impact:** Theoretically kills an unrelated process group with root privileges; practically negligible given Linux's sequential PID allocation, and `nft` does not fork. Worth a guard (`if proc.returncode is None:` or kill before wait) but not a blocker.

### 3. Nonblocking — expected-text normalization is string-coupled to `render_table`

- **Where:** `distractions-nft:253-257`. Fine today; a future change to `render_table` (e.g. adding a `with` clause) would silently stop the `.replace` from matching and produce a permanent "policy differs". The namespace test from finding 1 is the correct guard for this.

## Verdict

The wrapper half is well-built and the unit coverage of drift, bounds, and identity is thorough. One explicit acceptance criterion — the real-namespace apply/mutate/detect/repair test — is absent, and it is the only evidence that the canonicalization matches actual nft output rather than the wrapper's own rendering.

<verdict>NEEDS_WORK</verdict>