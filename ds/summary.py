"""The "While you were away" notice: one line from the person's agent over the held records, or the grouped count."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading

from ds import config, hold, ui

TITLE = "While you were away"
CLIP = 800
AUTO = (["claude", "-p", "--output-format", "text"], ["grok", "-p"])
PROMPT = (
    "The desktop notifications below were held while the person was focused. Each line is one JSON object "
    "with the app, the title, and the body. In one or two plain sentences, in the second person, tell them "
    "whether anything needs their attention. No preamble, no list, no markdown.\n\n"
)


def _log(msg):
    print(f"summary: {msg}", file=sys.stderr, flush=True)


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
    """The held records, removed from held.jsonl in the same step.

    Consuming them here, on the listener's thread, is what keeps a second
    boundary during a slow agent call (a lock ending seconds after the space
    was entered) from summarizing the same pings twice, and lets pings held
    while the command runs wait for the next summary.
    """
    path = hold.held_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("app"), str) and rec["app"]:
            records.append(rec)
    try:
        path.unlink()
    except OSError as e:
        _log(f"cannot clear {path}: {e}")
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


def ask(argv, text, timeout):
    """The command's reply as one line, or None when it failed, timed out, or answered nothing."""
    try:
        proc = subprocess.run(argv, input=text, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        _log(f"{argv[0]} timed out after {timeout:g}s")
        return None
    except OSError as e:
        _log(f"{argv[0]}: {e}")
        return None
    if proc.returncode != 0:
        _log((proc.stderr or "").strip() or f"{argv[0]} exited {proc.returncode}")
        return None
    reply = " ".join((proc.stdout or "").split())
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
    """`notice` off the caller's thread: the command may take the whole `timeout_seconds`."""
    if not records:
        return None
    thread = threading.Thread(target=notice, args=(records, cfg), daemon=True)
    thread.start()
    return thread
