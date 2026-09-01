"""State, lock, expansion, and runtime file helpers."""

import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ds import hypr


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


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
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


def status():
    lk = read_lock()
    st = read_state()
    return {
        "locked": lk["locked"],
        "until": lk["until"],
        "purpose": lk["purpose"],
        "on_space": hypr.on_space(),
        "site_block": st.get("site_block", "off") if st else "off",
        "listener_pid": listener_pid(),
        "updated": now_iso(),
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
    return 0
