## Scope reviewed

Change `1ca5c457..3c8c949c` (diff at `/tmp/fable-fn-27-responsive-listener-and-efficient.2-3c8c949c/diff.txt`): `ds/net.py` `run_command` stdin staging and two new tests in `tests/test_net.py`. This is a follow-up compatibility fix inside the task's declared files; the reconciler/listener logic reviewed previously is untouched by this range.

## Correctness walkthrough (verified against source)

**The bug and the fix.** The previous loop called `proc.communicate(input=input, timeout=0.1)` and, on `TimeoutExpired`, retried with `input=None`. On CPython 3.11 the retry only registers stdin for writing when the *argument* is truthy, so any payload larger than the pipe buffer whose reader was slower than one poll interval was truncated and the child hung until the outer deadline. The red log (`/tmp/fn27-2-compat-red.log`) shows exactly that on 3.11.16: all four 262144-byte variants raise `TimeoutExpired` from `net.py:49` (pre-fix line numbering). The fix (`ds/net.py:38-47`) writes the payload to a `tempfile.TemporaryFile`, seeks to 0, and passes it as `stdin`, then recurses with `input=None`. `Popen` receives a real fd, so `communicate` has no stdin to manage and the child reads the whole payload regardless of poll timing. `/tmp/fn27-2-compat-311.log` and `-314.log` show 24/27 tests green.

**Text-mode fidelity.** `text_mode` at line 39 mirrors subprocess's own rule (`encoding or errors or text or universal_newlines`). `TemporaryFile(mode="w+", encoding=None, errors=None)` resolves to the locale/UTF-8-mode encoding the same way subprocess's `TextIOWrapper` does; `newline=None` on both sides translates `\n`→`os.linesep`, a no-op on Linux. `seek(0)` flushes the text/buffered writer before `Popen` inherits the descriptor. The four test cases (bytes, `text=True`, explicit UTF-8, Latin-1 with `errors="replace"` → `b"\xe9?"`) pin this, asserting exact length and SHA-256.

**Lifecycle.** The `with` block closes the parent's handle on return and on `Popen` failure; `test_command_input_file_closes_when_launch_fails` asserts `closed` and `_children == {}`. The cleanup `finally` at lines 69-95 is unchanged; `proc.stdin` is now `None` for input calls, so the stream-close loop is unaffected. Cancellation is checked before the temp file is created and again in the recursive call — harmless.

**No call site conflict.** `input=` is used only by `_apply_result` (`net.py:314-318`, `stdin=DEVNULL` only on the no-input flush branch) and `_check_result` (`net.py:330-334`). `cgroup.py:80`, `launch.py:431`, `setup.py:717/1003` pass `stdin` without `input`. So the new `kwargs["stdin"] = source` never overrides a caller-supplied stdin.

**Wrapper and contract.** `distractions-nft:56-62` reads `sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)`; a regular file is indistinguishable from a pipe for that read, and the byte cap still applies. `docs/internals.md:73` says "one address per line on stdin" with no pipe assumption. `ds/summary.py:237-241` already uses the identical staging pattern, so this follows an established repository precedent for subprocess input.

## Prior findings (re-review status)

1. `net.py` invalid cached address → wrong notice text — **not-fixed**, nonblocking, outside this diff's range.
2. `listener.py` `_ask` text for refused `release` — **not-fixed**, nonblocking; the task summary records the generic message as accepted and tested.
3. Disabled/empty policy flushes each cycle — **withdrawn** as a finding; it is the documented, accepted design.
4. Listener-level fake `sudo` never changes identity — **not-fixed**, nonblocking suggestion.
5. Refresh during in-flight equal check forces a replace — **withdrawn**; design note only.

## New findings

No blocking findings. Nonblocking:

1. **`ds/net.py:45` — explicit `stdin=` combined with `input=` is silently overridden.** `subprocess.run` raises `ValueError` for that combination; here the caller's `stdin` is replaced without error. Trigger: none today (verified above). Optional fix: `if "stdin" in kwargs: raise ValueError(...)` before staging.
2. **Interpreter coverage is a property of the runner, not the test.** The new test only demonstrates the 3.11 regression when executed on 3.11; on 3.12+ the old code also passed. The red/green logs supply that evidence for this run; the conductor should keep the 3.11 gate in place so the test continues to mean what it means.

## Acceptance check (this range)

Task files only (`ds/net.py`, `tests/test_net.py`); wrapper validation and privileged surface untouched; no supported-Python change; `_children` bookkeeping asserted empty in both new tests; existing timeout-descendant, reaped-child, stale-disable and stalled-firewall tests remain in the green logs.

<verdict>SHIP</verdict>