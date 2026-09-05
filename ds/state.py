"""State, lock, expansion, and runtime file helpers."""

import json
import os
import socket
import stat
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from ds import hypr

# Every JSON file read here is state this plugin writes: kilobytes at most. The cap
# is what a reader will materialize from a path someone else may have grown.
READ_CAP = 1024 * 1024


def state_dir() -> Path:
    raw = os.environ.get("XDG_STATE_HOME")
    base = Path(raw) if raw else Path.home() / ".local" / "state"
    path = base / "omarchy" / "distraction-space"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_dir() -> Path:
    return Path(os.environ["XDG_RUNTIME_DIR"]) if os.environ.get("XDG_RUNTIME_DIR") else Path("/tmp")


def state_path(name):
    return state_dir() / name


def runtime_path(name):
    return runtime_dir() / name


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_bounded(path, cap=READ_CAP):
    """The file's bytes, or None when it is missing, irregular, unreadable, or over `cap`.

    Every path read here is small state this plugin wrote, and each one is
    predictable and sits in a directory the account can write. The descriptor is
    opened without following a symlink and non-blocking, and checked with `fstat`
    before a byte is read, so neither a link pointing somewhere else nor a fifo or
    device swapped in where a state file was can redirect, stall, or fill the
    reader -- the bar's shell process and the listener both come through here.

    Past the cap the read refuses rather than truncating: a caller that got the
    first `cap` bytes of a larger file cannot tell a whole state file from the
    head of one, and JSON that parses after truncation would be believed. One
    byte over is enough to refuse, so `cap` bytes exactly still read clean.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = b""
        while len(data) <= cap:
            chunk = os.read(fd, min(65536, cap + 1 - len(data)))
            if not chunk:
                return data
            data += chunk
        return None
    except OSError:
        return None
    finally:
        os.close(fd)


def read_json(path, default=None):
    data = read_bounded(path)
    if data is None:
        return default
    try:
        return json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parse_iso(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def read_lock():
    unlocked = {"locked": False, "until": None, "purpose": "", "since": None}
    data = read_json(state_path("lock.json"), None)
    if not isinstance(data, dict) or not data.get("locked"):
        return unlocked
    until = data.get("until")
    if until:
        dt = _parse_iso(until) if isinstance(until, str) else None
        if dt is None or dt <= datetime.now(timezone.utc):
            return unlocked
    return {
        "locked": True,
        "until": until if isinstance(until, str) else None,
        "purpose": data["purpose"] if isinstance(data.get("purpose"), str) else "",
        "since": data["since"] if isinstance(data.get("since"), str) else None,
    }


def write_lock(locked, until, purpose):
    write_json(state_path("lock.json"), {
        "locked": bool(locked),
        "since": now_iso() if locked else None,
        "until": until,
        "purpose": purpose or "",
    })


def read_state():
    data = read_json(state_path("state.json"), None)
    return data if isinstance(data, dict) else None


def write_state(obj):
    write_json(state_path("state.json"), obj)


def read_expansion():
    return read_json(state_path("expansion.json"), None)


def write_expansion(obj):
    write_json(state_path("expansion.json"), obj)


def entries_path():
    return state_path("entries.json")


def read_entries():
    """The launcher and handler manifest: files setup wrote, each with its backup, and the previous handler."""
    data = read_json(entries_path(), None)
    data = data if isinstance(data, dict) else {}
    files = []
    for item in data.get("files") if isinstance(data.get("files"), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
            continue
        backup = item.get("backup")
        files.append({"path": item["path"], "backup": backup if isinstance(backup, str) and backup else None})
    previous = data.get("previous_handler")
    return {"files": files, "previous_handler": previous if isinstance(previous, str) and previous else None}


def write_entries(obj):
    write_json(entries_path(), obj)


def request_reload(verb="reload", timeout=2.0):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(str(runtime_path("distraction-space.sock")))
        sock.sendall((verb + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(256)
            if not chunk:
                break
            buf += chunk
        return buf.split(b"\n", 1)[0] == b"ok"
    except OSError:
        return False
    finally:
        sock.close()


def listener_pid():
    st = read_state()
    pid = st.get("listener_pid") if st else None
    if type(pid) is not int or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        return pid
    except OSError:
        return None
    return pid


HEALTH_STALE_SECONDS = 121
PING_TIMEOUT = 0.2


def _listener_health(pid):
    if pid is None:
        return "stopped"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + PING_TIMEOUT
    try:
        sock.settimeout(PING_TIMEOUT)
        sock.connect(str(runtime_path("distraction-space.sock")))
        sock.sendall(b"ping\n")
        buf = b""
        while b"\n" not in buf and len(buf) < 256:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "unresponsive"
            sock.settimeout(remaining)
            chunk = sock.recv(256 - len(buf))
            if not chunk:
                break
            buf += chunk
        return "responsive" if buf.split(b"\n", 1)[0] == b"ok" and b"\n" in buf else "unresponsive"
    except OSError:
        return "unresponsive"
    finally:
        sock.close()


def _health(st, cfg, listener, on_space, locked):
    observed = st.get("observed_at")
    observed = observed if isinstance(observed, dict) else {}
    now = datetime.now(timezone.utc)
    labels = {"site_block": "Site blocking", "notification_hold": "Notification holding", "links": "Listed-link routing"}
    services, reasons = {}, []
    if listener != "responsive":
        reasons.append("Listener is stopped." if listener == "stopped" else "Listener did not respond; saved observations may no longer apply.")
    if cfg is None:
        reasons.append("Saved settings are unreadable; enabled services are unknown.")
    for key, label in labels.items():
        enabled = None if cfg is None else {
            "site_block": cfg["site_block"]["enabled"],
            "notification_hold": cfg["hold_notifications"] != "never",
            "links": cfg["open_links_in_space"],
        }[key]
        expected = "on"
        if key == "notification_hold" and cfg is not None:
            policy = cfg["hold_notifications"]
            expected = ("on" if locked else "off") if policy == "locked" else (
                None if on_space is None else ("off" if on_space else "on"))
        raw_time = observed.get(key)
        when = _parse_iso(raw_time) if isinstance(raw_time, str) else None
        age = (now - when).total_seconds() if when else None
        value = st.get(key)
        if enabled is False:
            kind, reason = "disabled", "Off by choice."
        elif enabled is None:
            kind, reason = "unknown", "Cannot read saved settings."
        elif age is None or age < 0:
            kind, reason = "unknown", "No valid observation time; current behavior is unknown."
        elif age > HEALTH_STALE_SECONDS:
            kind, reason = "stale", "Last observation is stale; current behavior is unknown."
        elif value == "unavailable":
            kind, reason = "unavailable", "Unavailable at the last check."
        elif key == "links" and value == "displaced":
            kind, reason = "displaced", "Browser routing changed. Run distractions setup to apply your choice."
        elif value not in ("on", "off") or expected is None:
            kind, reason = "unknown", "No usable observation of the expected behavior."
        elif value != expected:
            kind = "pending"
            reason = ("Saved on, but routing is off. Run distractions setup to apply your choice." if key == "links"
                      else "Saved choice does not match the last observation; reload or check setup.")
        else:
            kind, reason = "healthy", "On at the last check." if value == "on" else "Idle under the saved policy at the last check."
        services[key] = {"state": kind, "enabled": enabled, "reason": reason,
                         "observed_at": raw_time if when else None,
                         "age_seconds": round(age, 1) if age is not None else None}
        if kind not in ("healthy", "disabled"):
            reasons.append(f"{label}: {reason}")
    kinds = {item["state"] for item in services.values()}
    overall = ("degraded" if listener != "responsive" or kinds & {"pending", "unavailable", "displaced"}
               else "unknown" if kinds & {"unknown", "stale"} else "healthy")
    return {"state": overall, "listener": listener, "reasons": reasons, "services": services}


def status():
    lk = read_lock()
    st = read_state() or {}
    held = st.get("held")
    ipc = st.get("notification_hold")
    pt = st.get("pass_through")
    links = st.get("links")
    browser = st.get("browser")
    released = st.get("released")
    from ds import config
    try:
        cfg = config._read()
    except (config.Invalid, OSError):
        cfg = None
    on_space = hypr.on_space()
    pid = listener_pid()
    health = _health(st, cfg, _listener_health(pid), on_space, lk["locked"])
    observed = st.get("observed_at")
    return {
        "locked": lk["locked"],
        "until": lk["until"],
        "purpose": lk["purpose"],
        "on_space": on_space,
        "site_block": st.get("site_block", "off"),
        "listener_pid": pid,
        "hold": st.get("hold") is True,
        "held": {k: v for k, v in held.items() if isinstance(k, str) and type(v) is int} if isinstance(held, dict) else {},
        "notification_hold": ipc if ipc in ("on", "off", "unavailable") else "off",
        "pass_through": pt if pt in ("on", "off", "unavailable") else "off",
        "links": links if links in ("on", "off", "displaced") else "off",
        "browser": browser if isinstance(browser, str) and browser else None,
        "released": {k: v for k, v in released.items() if isinstance(k, str) and isinstance(v, str)}
        if isinstance(released, dict) else {},
        "updated": st.get("updated") if isinstance(st.get("updated"), str) else None,
        "response_at": now_iso(),
        "observed_at": observed if isinstance(observed, dict) else {},
        "health": health,
    }


def cmd_status(args):
    st = status()
    if getattr(args, "json", False):
        print(json.dumps(st))
        return 0
    print("locked" if st["locked"] else "unlocked")
    if st["purpose"]:
        print(st["purpose"])
    print(f"on_space={st['on_space']} site_block={st['site_block']}")
    print(f"hold={'on' if st['hold'] else 'off'} held={sum(st['held'].values())} "
          f"notification_hold={st['notification_hold']} pass_through={st['pass_through']}")
    print(f"Health: {st['health']['state']}; listener: {st['health']['listener']}")
    for reason in st["health"]["reasons"]:
        print(reason)
    return 0


def cmd_banners(args):
    try:
        text = state_path("log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    lines = []
    for line in text.splitlines():
        if not line:
            continue
        rest = line.split(" ", 1)
        if len(rest) == 2 and rest[1].startswith("banner: "):
            lines.append(line)
    for line in reversed(lines[-args.count:]):
        print(line)
    return 0

