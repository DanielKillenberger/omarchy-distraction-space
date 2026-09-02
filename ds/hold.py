"""Notification hold: sender keys, the shell's silenced list, the bus capture into held.jsonl, and the sound mute."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from ds import catalog, config, state

FIELD_CAP = 4096
FILE_CAP = 64 * 1024
BACKOFF = (1.0, 4.0, 16.0)
IPC_TIMEOUT = 10
MATCH = "interface='org.freedesktop.Notifications',member='Notify'"
BUSCTL = ["busctl", "--user", "monitor", "--json=short", "--match", MATCH]
PACTL_LIST = ["pactl", "-f", "json", "list", "sink-inputs"]
PACTL_SUBSCRIBE = ["pactl", "subscribe"]
ANCESTORS = 8
RELEASE_RETRY = 16.0
PROC = Path("/proc")
_SINK_INPUT = re.compile(r"^Event '(new|change|remove)' on sink-input #(\d+)")

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


def _entry_hosts(entry, products):
    """The PWA host; a plain or custom hostname entry adds its hosts."""
    raw = []
    for pat in entry.get("classes") or []:
        m = _PWA_CLASS.fullmatch(pat) if isinstance(pat, str) else None
        if m:
            host = _UNESCAPE.sub(r"\1", m.group(1))
            if catalog.is_hostname(host):
                raw.append(host)
    if entry.get("name") not in products:
        raw.extend(h for h in entry.get("hosts") or [] if isinstance(h, str))
    return raw


def _entry_keys(entry, products):
    """Catalog senders plus the entry's hosts."""
    if not isinstance(entry, dict):
        return []
    return [s for s in entry.get("senders") or [] if isinstance(s, str)] + _entry_hosts(entry, products)


def key_table(expanded) -> dict:
    """Normalized sender key to the list entry's name; the first entry naming a key keeps it."""
    table, products = {}, catalog.load_catalog()
    for entry in expanded or []:
        for raw in _entry_keys(entry, products):
            key = normalize(raw)
            if key and key not in table:
                table[key] = entry.get("name") or key
    return table


def sender_keys(expanded) -> list:
    """The keys the listener pushes: catalog senders and PWA hosts, plain entries' hosts, in list order."""
    return list(key_table(expanded))


def effective_hold(cfg, on_space, locked) -> bool:
    mode = (cfg or {}).get("hold_notifications", config.DEFAULTS["hold_notifications"])
    if mode == "off-space":
        return on_space is False
    return mode == "locked" and bool(locked)


def mute_on(cfg) -> bool:
    return (cfg or {}).get("mute_sounds", config.DEFAULTS["mute_sounds"]) is True


def _shell(*args):
    try:
        proc = subprocess.run(
            ["omarchy-shell", "notifications", *args],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=IPC_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, "omarchy-shell timed out"
    except OSError as e:
        return None, f"omarchy-shell: {e}"
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


def owned_path():
    return state.state_path("silenced-owned.json")


def _read_owned() -> list:
    data = state.read_json(owned_path(), [])
    return [k for k in data if isinstance(k, str) and k] if isinstance(data, list) else []


def _write_owned(keys) -> None:
    try:
        if keys:
            state.write_json(owned_path(), list(keys))
        else:
            owned_path().unlink(missing_ok=True)
    except OSError as e:
        _log(f"silenced-owned.json: {e}")


def push(keys, on, retire=()) -> str:
    """Add (on) or remove (off) the plugin's sender keys in the shell's silenced list.

    Only keys this plugin put there are ever removed: a key the person had
    silenced by hand before a hold began is never touched in either direction.
    The owned set persists in `silenced-owned.json` so a listener restart or a
    retired key (`retire`: pushed earlier, no longer on the list) still knows
    what to give back. Returns `on`, `off`, or `unavailable` for
    `state.json.notification_hold`.
    """
    current = _read_silenced()
    if current is None:
        return "unavailable"
    keys = [normalize(k) for k in keys if normalize(k)]
    owned = [k for k in _read_owned() if k in current]
    remove = [k for k in owned if k in (set(normalize(r) for r in retire) | (set() if on else set(keys)))]
    add = [k for k in keys if k not in current] if on else []
    # One IPC call per key: `qs ipc call` parses a `[...]` argument as its own
    # list syntax, so a JSON array can never reach setSilencedSenders intact.
    for key in remove:
        out, err = _shell("unsilence", key)
        if out is None or out == "error":
            _log(f"unsilence {key}: {err or out}")
            _write_owned(owned)
            return "unavailable"
        owned.remove(key)
    for key in add:
        out, err = _shell("silence", key)
        if out is None or out == "error":
            _log(f"silence {key}: {err or out}")
            _write_owned(owned)
            return "unavailable"
        owned.append(key)
    _write_owned(owned)
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


class _Tail:
    """A long-running child read line by line for the listener's life, restarted with backoff when it exits."""

    CMD, MISSING = (), ""

    def __init__(self):
        self.proc, self.buf, self.exits = None, b"", 0
        self.next_start, self.missing = 0.0, False

    def fileno(self):
        return self.proc.stdout.fileno() if self.proc is not None else None

    def wanted(self) -> bool:
        return True

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        if self.proc is not None and self.proc.poll() is not None:
            self._exited(now)
        if self.proc is None and not self.missing and self.wanted() and now >= self.next_start:
            self._start(now)

    def _exited(self, now):
        """Reap the child and schedule the restart; its pipe leaves the select set at once."""
        proc, self.proc = self.proc, None
        try:
            rc = proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait()
        proc.stdout.close()
        self._backoff(now, f"{self.CMD[0]} exited with {rc}")

    def _backoff(self, now, why):
        delay = BACKOFF[min(self.exits, len(BACKOFF) - 1)]
        self.exits += 1
        self.next_start = now + delay
        _log(f"{why}; restarting in {delay:g}s")

    def _gone(self):
        if not self.missing:
            self.missing = True
            _log(self.MISSING)

    def _start(self, now):
        try:
            self.proc = subprocess.Popen(
                list(self.CMD), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            os.set_blocking(self.proc.stdout.fileno(), False)
            self.buf = b""
        except FileNotFoundError:
            self._gone()
        except OSError as e:
            if self.proc is not None:
                self.stop()
            self._backoff(now, f"{self.CMD[0]} failed to start ({e})")

    def _lines(self):
        """Every complete line the child has written since the last call."""
        if self.proc is None:
            return []
        fd = self.proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                chunk = b""
            if not chunk:
                self._exited(time.monotonic())
                break
            self.buf += chunk
        lines = []
        while b"\n" in self.buf:
            raw, self.buf = self.buf.split(b"\n", 1)
            self.exits = 0
            lines.append(raw)
        return lines

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


class Capture(_Tail):
    """`busctl --user monitor` for the listener's life, restarted with backoff when it exits."""

    CMD, MISSING = BUSCTL, "busctl missing; notification capture is off"

    def __init__(self):
        super().__init__()
        self.drop_noted = False

    def pump(self, active, table) -> int:
        """Read what busctl has; while `active`, record every Notify the table attributes."""
        added = 0
        for raw in self._lines():
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


# --- sound mute -------------------------------------------------------------


def audio_table(expanded) -> dict:
    """Normalized `application.name`, `application.process.binary`, and PWA host to the list entry's name."""
    table, products = {"names": {}, "binaries": {}, "hosts": {}}, catalog.load_catalog()
    for entry in expanded or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or ""
        audio = entry.get("audio") if isinstance(entry.get("audio"), dict) else {}
        for field, key in (("name", "names"), ("binary", "binaries")):
            for raw in audio.get(field) or []:
                norm = normalize(raw) if isinstance(raw, str) else ""
                if norm:
                    table[key].setdefault(norm, name)
        for raw in _entry_hosts(entry, products):
            norm = normalize(raw)
            if norm:
                table["hosts"].setdefault(norm, name)
    return table


def _stat_fields(pid, proc):
    """/proc/<pid>/stat after the comm: [0] state, [1] ppid, [19] starttime."""
    try:
        text = (proc / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fields = text.rpartition(")")[2].split()
    return fields if len(fields) > 19 else None


def stream_pid(item):
    props = item.get("properties") if isinstance(item, dict) else None
    raw = props.get("application.process.id") if isinstance(props, dict) else None
    try:
        pid = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def identity(pid, proc=None):
    """`pid:starttime` of a live process, or None when it cannot be read."""
    fields = _stat_fields(pid, proc or PROC) if pid else None
    return f"{pid}:{fields[19]}" if fields else None


def _cmdline_host(pid, proc):
    """The host a Chromium web-app flag names in this process's argv: `--app-id=<host>` or `--app=<url>`."""
    try:
        argv = (proc / str(pid) / "cmdline").read_bytes().split(b"\0")
    except OSError:
        return ""
    for token in argv:
        arg = token.decode("utf-8", "replace")
        if arg.startswith("--app-id="):
            return normalize(arg[9:])
        if arg.startswith("--app="):
            try:
                return normalize(urlsplit(arg[6:]).hostname or "")
            except ValueError:
                return ""
    return ""


def pwa_name(pid, hosts, proc=None):
    """The list entry whose PWA host the stream's process or one of up to ANCESTORS ancestors was launched for."""
    proc = proc or PROC
    for _ in range(ANCESTORS + 1):
        if not pid or pid <= 1:
            return None
        host = _cmdline_host(pid, proc)
        if host in hosts:
            return hosts[host]
        fields = _stat_fields(pid, proc)
        try:
            pid = int(fields[1]) if fields else 0
        except ValueError:
            return None
    return None


def _is_browser(app, binary) -> bool:
    return any(mark in app or mark in binary for mark in _CHROMIUM)


def attribute_stream(item, table, proc=None):
    """The list entry name a sink-input belongs to, or None; a bare browser stream is never a member."""
    props = item.get("properties") if isinstance(item, dict) else None
    if not isinstance(props, dict):
        return None
    app = normalize(props.get("application.name"))
    binary = normalize(os.path.basename(str(props.get("application.process.binary") or "")))
    if not _is_browser(app, binary):
        name = table["names"].get(app) if app else None
        if name is None and binary:
            name = table["binaries"].get(binary)
        if name is not None:
            return name
    return pwa_name(stream_pid(item), table["hosts"], proc)


def muted_path():
    return state.state_path("muted.json")


class Mute:
    """Mute the listed apps' streams while hold is on; unmute only what this plugin muted, by identity."""

    def __init__(self):
        self.active, self.table, self.owned = False, {"names": {}, "binaries": {}, "hosts": {}}, {}
        self.tail = _MuteTail(self)
        self.missing, self.fail_noted, self.retry_at = False, False, 0.0

    def fileno(self):
        return self.tail.fileno()

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        self.tail.tick(now)
        if not self.active and self.owned and now >= self.retry_at:
            self.release(now)

    def _load(self) -> dict:
        raw = state.read_json(muted_path(), {})
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(raw, dict) else {}

    def _save(self):
        try:
            if self.owned:
                state.write_json(muted_path(), self.owned)
            else:
                muted_path().unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            _log(f"cannot write {muted_path()}: {e}")

    def _run(self, cmd):
        """Run one pactl command; None when it failed. A missing binary disables the feature with one line."""
        if self.missing:
            return None
        try:
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  check=False, timeout=IPC_TIMEOUT)
        except FileNotFoundError:
            self.missing = True
            self.tail.missing = True
            self.tail.stop()
            _log(self.tail.MISSING)
            return None
        except (OSError, subprocess.TimeoutExpired) as e:
            return self._fail(f"{cmd[0]}: {e}")
        if proc.returncode != 0:
            return self._fail((proc.stderr or "").strip() or f"{' '.join(cmd)}: exit {proc.returncode}")
        self.fail_noted = False
        return proc.stdout or ""

    def _fail(self, why):
        if not self.fail_noted:
            self.fail_noted = True
            _log(f"pactl: {why}")
        return None

    def _list(self):
        out = self._run(PACTL_LIST)
        if out is None:
            return None
        try:
            items = json.loads(out or "[]")
        except json.JSONDecodeError:
            return self._fail("unexpected list output")
        return [it for it in items if isinstance(it, dict)] if isinstance(items, list) else []

    def _set(self, index, muted) -> bool:
        return self._run(["pactl", "set-sink-input-mute", index, "1" if muted else "0"]) is not None

    def sync(self, on, table, now=None):
        """On every hold transition and list change: mute while on, release when off."""
        self.table = table
        if on and not self.missing:
            if not self.active:
                self.active = True
                self.owned = self._load()
            self.scan()
            self.tick(now)
        elif self.active or muted_path().exists():
            self.release(now)

    def scan(self):
        """Mute every attributable, still audible stream and record its identity.

        A record whose index is gone or now carries another identity is dropped;
        so is one the person unmuted meanwhile, which is then left alone.
        """
        streams = self._list()
        if streams is None:
            return
        owned = {}
        for item in streams:
            index = str(item.get("index"))
            if not index.isdigit():
                continue
            ident = identity(stream_pid(item))
            if self.owned.get(index) == ident and ident is not None:
                if item.get("mute") is True:
                    owned[index] = ident
                continue
            if item.get("mute") is True or ident is None:
                continue
            if attribute_stream(item, self.table) is not None and self._set(index, True):
                owned[index] = ident
        if owned != self.owned:
            self.owned = owned
            self._save()

    def forget(self, index):
        if self.owned.pop(index, None) is not None:
            self._save()

    def pump(self):
        """Consume `pactl subscribe` events: a new or changed sink-input rescans, a removed one drops its record."""
        rescan = False
        for raw in self.tail._lines():
            m = _SINK_INPUT.match(raw.decode("utf-8", "replace"))
            if not m:
                continue
            if m.group(1) == "remove":
                self.forget(m.group(2))
            else:
                rescan = True
        if rescan and self.active:
            self.scan()

    def release(self, now=None):
        """Hold ended or the listener exits: unmute recorded indexes whose identity still matches.

        A record whose stream could not be listed or unmuted stays in the file
        and is retried from `tick` every RELEASE_RETRY seconds; the file clears
        once nothing is left.
        """
        self.active = False
        self.tail.stop()
        owned = self.owned or self._load()
        self.owned = {}
        streams = self._list() if owned else []
        if streams is None:
            self.owned = owned
        else:
            for item in streams:
                index = str(item.get("index"))
                ident = owned.get(index)
                if ident is not None and ident == identity(stream_pid(item)) and item.get("mute") is True \
                        and not self._set(index, False):
                    self.owned[index] = ident
        if self.owned:
            self.retry_at = (time.monotonic() if now is None else now) + RELEASE_RETRY
        self._save()


class _MuteTail(_Tail):
    CMD, MISSING = PACTL_SUBSCRIBE, "pactl missing; sound mute is off"

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def wanted(self) -> bool:
        return self.owner.active and not self.owner.fail_noted

    def _gone(self):
        if not self.owner.missing:
            self.owner.missing = True
            super()._gone()


def cmd_senders(args):
    try:
        cfg = config.load()
    except (config.Invalid, config.Busy) as e:
        print(str(e), file=sys.stderr)
        return 1
    for key in sender_keys(catalog.expand(cfg)):
        print(key)
    return 0
