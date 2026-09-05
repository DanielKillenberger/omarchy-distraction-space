I have everything needed; no further reads required.

## Re-review: fn-27-responsive-listener-and-efficient.3 (ac1b9f7 → f22fa25)

### Scope note

The range also carries `.flow/reviews/fn-27-…​.1*` and the `.1` task summary. Those are conductor bookkeeping for the sibling task, not code; I read them and they introduce nothing reviewable here. The code change is confined to `distractions-nft` and `tests/test_nft.py`, matching the task's `Files` list.

### Prior findings

1. **Real disposable-namespace test absent — fixed.** `tests/test_nft.py:431-498` adds `live_nft_scenario` and `LiveNftTests`. The child runs under `unshare --user --map-root-user --net`, refuses to proceed if `/proc/self/ns/net` equals the parent's (`:434`), applies via `replace ds`, asserts `check ds` returns 0 with JSON equal to the real slice's `st_dev`/`st_ino` (`:449-454`), records the real listing, mutates the live table both ways (`add rule … output accept` and `delete table`), asserts each drift returns exit 1 with empty stdout (`:460-466`), repairs after each, and covers empty and 4096-address sets. Every `nft` call is issued inside the child netns, so the host firewall is untouched by construction. `/tmp/fn27-3-followup-verify.log:29-64` shows the captured real nft 1.1.6 listing: `priority 0`/`-100`, `level 5` with the quoted path, `sport 61000-61999`, and both `reject with icmp[v6] port-unreachable` expansions — exactly the spellings `check_policy:255-258` substitutes. That closes the tautology concern: the canonicalization is now proven against real output, and `LIVE_NFT_PASS` was reached.
2. **`killpg` after successful reap — fixed.** `distractions-nft:219-223` now signals only when `proc.returncode is None`. Success and nonzero-exit paths go through `proc.wait(timeout=…)` first, so they never signal; timeout, output-cap, decode-failure and closed-stdout-then-hang paths still kill the group before the unconditional `proc.wait()`. `test_successful_listing_does_not_signal_reaped_pid` (`:412-416`) pins the regression.
3. **Expected-text normalization string-coupled to `render_table` — withdrawn as a finding.** Unchanged code, but the live test is now the guard I asked for; any future `render_table` drift will surface there rather than as a permanent "policy differs".

### Re-verified on the current head

- `check` reaches `check_policy` only after `_invoking_uid`, capped `_read_stdin`, and `parse_replace_stdin` (`distractions-nft:274-282`); `test_check_refuses_input_and_operands` shows bad target, extra operand, non-address stdin, and both caps refuse with no nft call. Sudoers is still path-only (`install/sudoers.omarchy-distraction-space:3`), so no install change is required.
- `canonical_policy` (`:228-245`) sorts set elements only when every element parses as the correct family with no duplicates; otherwise the text falls through to strict token comparison. `[^{}]*` spans the multi-line element lists nft emits for large sets, which the 4096-address live case exercised. The closure over `name`/`family` is used within the same loop iteration, so there is no late-binding hazard.
- `slice_identity` uses `follow_symlinks=False` + `S_ISDIR`; before/after inequality fails closed (`:249-253`); `test_check_missing_changed_slice_and_failed_listing` covers both the changed identity and the missing directory with no nft call and empty stdout.
- `list_policy` bounds the read at `MAX_OUTPUT_BYTES + 1` during consumption, uses a monotonic deadline in both the select loop and the final wait, merges stderr, and exits 1 with empty stdout on flood, stall, closed-fd hang, forked grandchild, nonzero exit, invalid UTF-8, and `Popen` failure (`test_listing_bounds_output_time_and_reaps`, `test_listing_launch_failure_is_not_proof`).
- Existing `replace`/`flush` behaviour is unchanged; `_require_slice` still guards `replace`, and `check` relies on `slice_identity` instead.

### New observations (nonblocking)

- The live test is opt-in (`DS_LIVE_NFT_TEST=1`, `tests/test_nft.py:475`) rather than auto-run-with-skip. The default suite therefore never exercises real nft; the evidence that it passes is the one recorded run in the log. Worth adding the env var to the task's Quick commands or `docs/` so it is rerun deliberately after any `render_table` or nft upgrade.
- `proc.wait()` in the `finally` (`:224`) has no timeout. After SIGKILL that is fine in practice; only an uninterruptible child could hold it.

No introduced blocking defect remains, and all five acceptance bullets now have direct test evidence.

<verdict>SHIP</verdict>