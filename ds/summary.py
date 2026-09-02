"""The "While you were away" notice: one line from the person's agent over the held records, or the grouped count."""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import tempfile
import threading
import time

from ds import config, hold, state, ui

TITLE = "While you were away"
CLIP = 800
# What is read from the command at most: stdout past this is not a one-liner, stderr past this is not a reason.
READ_CAP, ERR_CAP = 64 * 1024, 4 * 1024
AUTO = (["claude", "-p", "--output-format", "text"], ["grok", "-p"])
PROMPT = (
    "The desktop notifications below were held while the person was focused. Each line is one JSON object "
    "with the app, the title, and the body. In one or two plain sentences, in the second person, tell them "
    "whether anything needs their attention. No preamble, no list, no markdown.\n\n"
)


def _log(msg):
    path = state.state_path("log")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{state.now_iso()} summary: {msg}\n")
    except OSError:
        pass


def settings(cfg) -> dict:
    """The `summary` block with the defaults filled in."""
    raw = (cfg or {}).get("summary")
    return {**config.DEFAULTS["summary"], **(raw if isinstance(raw, dict) else {})}


def resolve_command(cfg):
    """The argv to ask, or None for the grouped count.

    `auto` takes claude, then grok, whichever PATH has first; `off` never
    asks; a custom argv is used as given.
    """
    cmd = settings(cfg).get("command")
    if isinstance(cmd, list):
        return list(cmd)
    if cmd != "auto":
        return None
    for argv in AUTO:
        if shutil.which(argv[0]):
            return list(argv)
    return None


def take() -> list:
    """Claim the held records: held.jsonl is renamed away first, then read.

    The rename is the claim, so whoever marks a boundary (the listener on a
    lock expiry or space entry, `distractions unlock` on a manual unlock) gets
    every record exactly once: the hook's counts and the notice come from the
    same records, a second boundary during a slow agent call has nothing to
    repeat, and pings held meanwhile wait for the next summary. A claim that
    fails leaves the file untouched and returns nothing, so nothing is shown
    twice.
    """
    path = hold.held_path()
    claim = path.with_name(f".{path.name}.{os.getpid()}.taken")
    try:
        os.replace(path, claim)
    except FileNotFoundError:
        return []
    except OSError as e:
        _log(f"cannot claim {path}: {e}")
        return []
    try:
        lines = claim.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        _log(f"cannot read {claim}: {e}")
        lines = []
    finally:
        try:
            claim.unlink()
        except OSError:
            pass
    records = []
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("app"), str) and rec["app"]:
            records.append(rec)
    return records


def counts(records) -> dict:
    held = {}
    for rec in records:
        held[rec["app"]] = held.get(rec["app"], 0) + 1
    return held


def grouped(held) -> str:
    """`Telegram 3 · Discord 1`: most held first, ties in the order they were first held."""
    return " · ".join(f"{app} {n}" for app, n in sorted(held.items(), key=lambda kv: -kv[1]))


def prompt(records) -> str:
    return PROMPT + "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in records)


def _clip(text) -> str:
    raw = text.encode("utf-8")
    return raw[:CLIP].decode("utf-8", "ignore") if len(raw) > CLIP else text


def _drain(proc, deadline):
    """stdout up to READ_CAP and stderr up to ERR_CAP, or None past the deadline (the child is killed).

    A pipe is closed once its cap is reached, so a flooding child writes into
    a closed pipe instead of into this process's memory.
    """
    caps = {proc.stdout: READ_CAP, proc.stderr: ERR_CAP}
    bufs = {f: b"" for f in caps}
    pending = set(caps)
    late = False
    while pending and not late:
        wait = deadline - time.monotonic()
        ready = select.select(list(pending), [], [], wait)[0] if wait > 0 else []
        if not ready:
            late = True
            break
        for f in ready:
            try:
                chunk = os.read(f.fileno(), 65536)
            except OSError:
                chunk = b""
            bufs[f] += chunk
            if not chunk or len(bufs[f]) >= caps[f]:
                pending.discard(f)
                f.close()
    for f in pending:
        f.close()
    try:
        proc.wait(timeout=max(0.0, deadline - time.monotonic()) if not late else 0)
    except subprocess.TimeoutExpired:
        late = True
    if late:
        proc.kill()
        proc.wait()
        return None
    return {f: bufs[f][:caps[f]] for f in caps}


def ask(argv, text, timeout):
    """The command's reply as one line, or None when it failed, timed out, or answered nothing."""
    deadline = time.monotonic() + timeout
    try:
        with tempfile.TemporaryFile() as stdin:
            stdin.write(text.encode("utf-8"))
            stdin.flush()
            stdin.seek(0)
            proc = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        _log(f"{argv[0]}: {e}")
        return None
    got = _drain(proc, deadline)
    if got is None:
        _log(f"{argv[0]} timed out after {timeout:g}s")
        return None
    if proc.returncode != 0:
        err = got[proc.stderr].decode("utf-8", "replace").strip()
        _log(err or f"{argv[0]} exited {proc.returncode}")
        return None
    reply = " ".join(got[proc.stdout].decode("utf-8", "replace").split())
    return _clip(reply) if reply else None


def body(records, cfg) -> str:
    argv = resolve_command(cfg)
    reply = ask(argv, prompt(records), settings(cfg).get("timeout_seconds")) if argv else None
    return reply or grouped(counts(records))


def notice(records, cfg) -> bool:
    """Show the one notification for these records; zero records show nothing."""
    if not records:
        return False
    ui.notify(TITLE, body(records, cfg))
    return True


def start(records, cfg):
    """`notice` off the listener's loop: the command may take the whole `timeout_seconds`."""
    if not records:
        return None
    thread = threading.Thread(target=notice, args=(records, cfg), daemon=True)
    thread.start()
    return thread
