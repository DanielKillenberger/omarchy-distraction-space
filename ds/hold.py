"""Notification hold: sender keys, the shell's silenced list, and the bus capture into held.jsonl."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from ds import catalog, config, state

FIELD_CAP = 4096
FILE_CAP = 64 * 1024
BACKOFF = (1.0, 4.0, 16.0)
IPC_TIMEOUT = 10
MATCH = "interface='org.freedesktop.Notifications',member='Notify'"
BUSCTL = ["busctl", "--user", "monitor", "--json=short", "--match", MATCH]

# catalog.pwa_class(host) is "^chrome-" + re.escape(host) + "__.*$"; the
# expansion carries the PWA host only in that class pattern.
_PWA_CLASS = re.compile(r"\^chrome-(.+)__\.\*\$")
_UNESCAPE = re.compile(r"\\(.)")
# Same rule as the shell patch: a Chromium-derived sender is told by its
# app_name or app_icon, and the site host it prepends to the body is the key.
_CHROMIUM = ("chrom", "brave", "vivaldi", "microsoft-edge", "opera")
_HOST = r"(?:https?://|www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?"
_LINKED_ORIGIN = re.compile(r"^\s*<a\b[^>]*>\s*(" + _HOST + r"(?:/[^<\s]*)?)\s*</a>", re.I)
_BARE_ORIGIN = re.compile(r"^\s*(" + _HOST + r"(?:/\S*)?)(?:\s+|$)", re.I)


def _log(msg):
    print(f"hold: {msg}", file=sys.stderr, flush=True)


def normalize(value) -> str:
    key = str(value or "").strip().lower()
    return key[4:] if key.startswith("www.") else key


def _entry_keys(entry):
    if not isinstance(entry, dict):
        return []
    raw = [s for s in entry.get("senders") or [] if isinstance(s, str)]
    for pat in entry.get("classes") or []:
        m = _PWA_CLASS.fullmatch(pat) if isinstance(pat, str) else None
        if m:
            host = _UNESCAPE.sub(r"\1", m.group(1))
            if catalog.is_hostname(host):
                raw.append(host)
    raw.extend(h for h in entry.get("hosts") or [] if isinstance(h, str))
    return raw


def key_table(expanded) -> dict:
    """Normalized sender key to the list entry's name; the first entry naming a key keeps it."""
    table = {}
    for entry in expanded or []:
        for raw in _entry_keys(entry):
            key = normalize(raw)
            if key and key not in table:
                table[key] = entry.get("name") or key
    return table


def sender_keys(expanded) -> list:
    """The keys the listener pushes: catalog senders, PWA hosts, and plain hosts, in list order."""
    return list(key_table(expanded))


def effective_hold(cfg, on_space, locked) -> bool:
    mode = (cfg or {}).get("hold_notifications", config.DEFAULTS["hold_notifications"])
    if mode == "off-space":
        return on_space is False
    return mode == "locked" and bool(locked)


def _shell(*args):
    try:
        proc = subprocess.run(
            ["omarchy-shell", "notifications", *args],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=IPC_TIMEOUT,
        )
    except FileNotFoundError:
        return None, "omarchy-shell missing"
    except subprocess.TimeoutExpired:
        return None, "omarchy-shell timed out"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return None, (proc.stderr or "").strip() or out or f"exit {proc.returncode}"
    return out, ""


def _read_silenced():
    out, err = _shell("silencedSenders")
    if out is None:
        _log(f"silencedSenders: {err}")
        return None
    try:
        items = json.loads(out)
    except json.JSONDecodeError:
        items = None
    if not isinstance(items, list):
        _log(f"silencedSenders: unexpected answer {out!r}")
        return None
    seen = []
    for item in items:
        key = normalize(item) if isinstance(item, str) else ""
        if key and key not in seen:
            seen.append(key)
    return seen


def push(keys, on, retire=()) -> str:
    """Add (on) or remove (off) the plugin's keys in the shell's silenced list.

    Keys the person added by hand stay; `retire` names keys pushed earlier
    that the list no longer produces, dropped in both directions. Returns
    `on`, `off`, or `unavailable` for `state.json.notification_hold`.
    """
    current = _read_silenced()
    if current is None:
        return "unavailable"
    keys = [normalize(k) for k in keys]
    drop = {normalize(k) for k in retire} | (set() if on else set(keys))
    if on:
        drop -= set(keys)
    want = [k for k in current if k not in drop]
    if on:
        want.extend(k for k in keys if k and k not in want)
    if want != current:
        out, err = _shell("setSilencedSenders", json.dumps(want))
        if out is None or out == "error":
            _log(f"setSilencedSenders: {err or out}")
            return "unavailable"
    return "on" if on else "off"


def sender_origin(app, icon, body) -> str:
    source = f"{app or ''}\n{icon or ''}".lower()
    if not any(mark in source for mark in _CHROMIUM):
        return ""
    text = str(body or "")
    m = _LINKED_ORIGIN.match(text) or _BARE_ORIGIN.match(text)
    if not m:
        return ""
    host = re.sub(r"^https?://", "", m.group(1), flags=re.I)
    return host.split("/")[0].split(":")[0].lower()


def attribute(data, table):
    """The list entry name a Notify's `payload.data` belongs to, or None."""
    if not isinstance(data, list) or len(data) < 5:
        return None
    app, icon, body = data[0], data[2], data[4]
    name = table.get(normalize(app))
    if name is None:
        origin = normalize(sender_origin(app, icon, body))
        name = table.get(origin) if origin else None
    return name


def held_path():
    return state.state_path("held.jsonl")


def _clip(value) -> str:
    raw = str(value if value is not None else "").encode("utf-8")
    return raw[:FIELD_CAP].decode("utf-8", "ignore") if len(raw) > FIELD_CAP else raw.decode("utf-8")


def _trim(path):
    data = path.read_bytes()
    if len(data) <= FILE_CAP:
        return
    while len(data) > FILE_CAP and b"\n" in data:
        data = data.split(b"\n", 1)[1]
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def append_held(app, title, body) -> bool:
    """One record per held Notify; fields clipped at FIELD_CAP, the newest kept under FILE_CAP."""
    record = {"at": state.now_iso(), "app": _clip(app), "title": _clip(title), "body": _clip(body)}
    try:
        path = held_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        _trim(path)
    except OSError:
        return False
    return True


def held_counts() -> dict:
    counts = {}
    try:
        lines = held_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return counts
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        app = rec.get("app") if isinstance(rec, dict) else None
        if isinstance(app, str) and app:
            counts[app] = counts.get(app, 0) + 1
    return counts


class Capture:
    """`busctl --user monitor` for the listener's life, restarted with backoff when it exits."""

    def __init__(self):
        self.proc, self.buf, self.exits = None, b"", 0
        self.next_start, self.missing, self.drop_noted = 0.0, False, False

    def fileno(self):
        return self.proc.stdout.fileno() if self.proc is not None else None

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        if self.proc is not None and self.proc.poll() is not None:
            rc = self.proc.returncode
            self.proc.stdout.close()
            self.proc, self.buf = None, b""
            delay = BACKOFF[min(self.exits, len(BACKOFF) - 1)]
            self.exits += 1
            self.next_start = now + delay
            _log(f"busctl exited with {rc}; restarting in {delay:g}s")
        if self.proc is None and not self.missing and now >= self.next_start:
            self._start()

    def _start(self):
        try:
            self.proc = subprocess.Popen(
                BUSCTL, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self.missing = True
            _log("busctl missing; notification capture is off")
            return
        os.set_blocking(self.proc.stdout.fileno(), False)

    def pump(self, active, table) -> int:
        """Read what busctl has; while `active`, record every Notify the table attributes."""
        if self.proc is None:
            return 0
        fd = self.proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                chunk = b""
            if not chunk:
                break
            self.buf += chunk
        added = 0
        while b"\n" in self.buf:
            raw, self.buf = self.buf.split(b"\n", 1)
            self.exits = 0
            if active and self._record(raw, table):
                added += 1
        return added

    def _record(self, raw, table) -> bool:
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return False
        if not isinstance(obj, dict) or obj.get("member") != "Notify":
            return False
        payload = obj.get("payload")
        data = payload.get("data") if isinstance(payload, dict) else None
        name = attribute(data, table)
        if name is None:
            return False
        if append_held(name, data[3], data[4]):
            return True
        if not self.drop_noted:
            self.drop_noted = True
            _log(f"cannot write {held_path()}; held records are dropped")
        return False

    def stop(self):
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        except OSError:
            pass
        proc.stdout.close()


def cmd_senders(args):
    try:
        cfg = config.load()
    except (config.Invalid, config.Busy) as e:
        print(str(e), file=sys.stderr)
        return 1
    for key in sender_keys(catalog.expand(cfg)):
        print(key)
    return 0
