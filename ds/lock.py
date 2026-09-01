"""Lock state, lazy expiry, hooks, and enter/leave/toggle."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ds import config, hypr, state, ui
from ds.config import DEFAULTS

_alive = []


def is_locked():
    return bool(state.read_lock().get("locked"))


def lock(minutes, purpose):
    if is_locked():
        return 0
    purpose = purpose or ""
    until = None if minutes is None else _until_iso(minutes)
    state.write_lock(True, until, purpose)
    run_hook("lock", {
        "DS_EVENT": "lock",
        "DS_PURPOSE": purpose,
        "DS_MINUTES": "" if minutes is None else str(minutes),
        "DS_REASON": "",
        "DS_HELD": "{}",
    })
    return 0


def unlock(reason):
    if not is_locked():
        return 0
    reason = reason or ""
    n = _reason_min()
    if n and len(reason) < n:
        _notify("Reason too short", f"Write at least {n} characters.")
        print(f"unlock needs at least {n} characters", file=sys.stderr)
        return 1
    purpose = state.read_lock().get("purpose") or ""
    state.write_lock(False, None, "")
    try:
        _append_log(
            f"{state.now_iso()} unlock purpose={_one_line(purpose)} reason={_one_line(reason)}"
        )
    except OSError:
        pass
    run_hook("unlock", {
        "DS_EVENT": "unlock",
        "DS_PURPOSE": purpose,
        "DS_MINUTES": "",
        "DS_REASON": reason,
        "DS_HELD": "{}",
    })
    return 0


def expire_if_due():
    data = state.read_json(state.state_path("lock.json"), None)
    if not isinstance(data, dict) or not data.get("locked"):
        return False
    if is_locked():
        return False
    state.write_lock(False, None, "")
    return True


def run_hook(name, env):
    argvs = _hook_argvs(name)
    if not argvs:
        return
    merged = {
        "DS_EVENT": name,
        "DS_PURPOSE": "",
        "DS_MINUTES": "",
        "DS_REASON": "",
        "DS_HELD": "{}",
    }
    if env:
        for key, value in env.items():
            merged[str(key)] = "" if value is None else str(value)
    child_env = os.environ.copy()
    child_env.update(merged)
    logf = _open_log()
    _alive[:] = [p for p in _alive if p.poll() is None]
    try:
        for argv in argvs:
            try:
                _alive.append(subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=logf if logf is not None else subprocess.DEVNULL,
                    stderr=logf if logf is not None else subprocess.DEVNULL,
                    start_new_session=True,
                    env=child_env,
                ))
            except Exception:
                pass
    finally:
        if logf is not None:
            try:
                logf.close()
            except OSError:
                pass


def enter():
    if hypr.on_space() is True:
        return 0
    if is_locked():
        _lock_notice()
        return 1
    held = None
    if _entry_confirm_on():
        held = _try_confirm_lock()
        if held is None:
            return 0
        try:
            try:
                decision = ui.confirm_enter(timeout=30)
            except ui.Unavailable:
                decision = "unavailable"
            if decision == "stay":
                return 0
            if decision == "unavailable":
                _notify("Entry confirm unavailable", "Entering the distraction space.")
            elif decision != "enter":
                return 0
            if is_locked():
                _lock_notice()
                return 1
            if hypr.on_space() is True:
                return 0
        finally:
            _release(held)
            held = None
    return _go_to_space()


def leave():
    if hypr.on_space() is True:
        return 0 if hypr.cycle("next") else 1
    return 0


def toggle():
    if hypr.on_space() is True:
        return leave()
    return enter()


def cmd_lock(args):
    raise NotImplementedError


def cmd_unlock(args):
    raise NotImplementedError


def cmd_enter(args):
    raise NotImplementedError


def cmd_leave(args):
    raise NotImplementedError


def cmd_toggle(args):
    raise NotImplementedError


# After tests/test_status.py drops lock/unlock/enter/leave/toggle from STUBS:
#   def cmd_lock(args): return _cli_lock(args)
#   def cmd_unlock(args): return _cli_unlock(args)
#   def cmd_enter(args): return enter()
#   def cmd_leave(args): return leave()
#   def cmd_toggle(args): return toggle()


def _cli_lock(args):
    if is_locked():
        return 0
    duration = getattr(args, "duration", None)
    purpose_words = getattr(args, "purpose", None) or []
    if duration is None:
        try:
            result = ui.prompt_lock(_cfg_or_defaults())
        except ui.Unavailable:
            _notify("Lock prompt unavailable", "Pass minutes and purpose as arguments.")
            print("lock prompt unavailable; pass minutes and purpose as arguments", file=sys.stderr)
            return 1
        if result is None:
            return 0
        minutes, purpose = result
        return lock(minutes, purpose)
    if duration == "forever":
        minutes = None
    else:
        try:
            minutes = int(duration)
        except (TypeError, ValueError):
            print("lock: minutes must be an integer or forever", file=sys.stderr)
            return 1
        if minutes < 0:
            print("lock: minutes must be >= 0", file=sys.stderr)
            return 1
    return lock(minutes, " ".join(purpose_words))


def _cli_unlock(args):
    if not is_locked():
        return 0
    reason_words = getattr(args, "reason", None) or []
    reason = " ".join(reason_words).strip()
    if not reason:
        if _reason_min() <= 0:
            return unlock("")
        try:
            reason = ui.prompt_reason(_reason_min())
        except ui.Unavailable:
            _notify("Unlock prompt unavailable", "Pass the reason as arguments.")
            print("unlock prompt unavailable; pass the reason as arguments", file=sys.stderr)
            return 1
        if reason is None:
            return 0
    return unlock(reason)


def _until_iso(minutes):
    return (datetime.now(timezone.utc) + timedelta(minutes=int(minutes))).replace(
        microsecond=0
    ).isoformat()


def _one_line(text):
    return (text or "").replace("\n", " ").replace("\r", " ")


def _try_cfg():
    try:
        path = config.config_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _cfg_or_defaults():
    cfg = _try_cfg()
    return cfg if cfg is not None else DEFAULTS


def _reason_min():
    cfg = _try_cfg()
    if isinstance(cfg, dict):
        lk = cfg.get("lock")
        if isinstance(lk, dict) and type(lk.get("reason_min_chars")) is int:
            return lk["reason_min_chars"]
    return 50


def _entry_confirm_on():
    cfg = _try_cfg()
    if not isinstance(cfg, dict):
        return True
    nudges = cfg.get("nudges")
    if not isinstance(nudges, dict) or "entry_confirm" not in nudges:
        return True
    return bool(nudges["entry_confirm"])


def _log_path():
    cfg = _try_cfg()
    raw = cfg.get("log") if isinstance(cfg, dict) else None
    if not isinstance(raw, str) or not raw or raw == DEFAULTS["log"]:
        return state.state_path("log")
    return Path(os.path.expanduser(raw))


def _open_log():
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        return open(path, "a", encoding="utf-8")
    except OSError:
        return None


def _append_log(line):
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _hook_argvs(name):
    cfg = _try_cfg()
    if not isinstance(cfg, dict):
        return []
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict):
        return []
    raw = hooks.get(name) or []
    if not isinstance(raw, list):
        return []
    out = []
    for argv in raw:
        if isinstance(argv, list) and argv and all(isinstance(x, str) and x for x in argv):
            out.append(argv)
    return out


def _notify(title, body, **kw):
    try:
        ui.notify(title, body, **kw)
    except Exception:
        pass


def _lock_notice():
    lk = state.read_lock()
    purpose = lk.get("purpose") or ""
    until = lk.get("until")
    body = purpose or "The distraction space is locked."
    if until:
        body = f"{body} Until {until}"
    _notify("Distraction space locked", body, urgent=True)


def _try_confirm_lock():
    path = state.runtime_path("distraction-space.confirm")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fh = open(path, "a+", encoding="utf-8")
    except OSError:
        return False
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    except OSError:
        fh.close()
        return False
    return fh


def _release(fh):
    if not fh:
        return
    try:
        fcntl.flock(fh, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        fh.close()
    except OSError:
        pass


def _go_to_space():
    try:
        r = subprocess.run(
            ["hyprctl", "dispatch", "workspace", f"name:{hypr.SPACE}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return 1
    return 0 if r.returncode == 0 else 1
