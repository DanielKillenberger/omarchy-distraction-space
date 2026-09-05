"""Lock state, lazy expiry, hooks, and enter/leave/toggle."""

from __future__ import annotations

import copy
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ds import config, hypr, state, summary, ui
from ds.config import DEFAULTS

_alive = []
_cfg_warned = False


def _with_lockfile(fn):
    path = state.runtime_path("distraction-space.lockfile.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            try:
                fcntl.flock(fh, fcntl.LOCK_UN)
            except OSError:
                pass


def is_locked():
    return bool(state.read_lock().get("locked"))


def lock(minutes, purpose):
    purpose = purpose or ""
    until = None if minutes is None else until_iso(minutes)
    # Locking while on the space leaves it the way `leave` does; the lock is written either way.
    if hypr.on_space() is True:
        hypr.cycle("next")

    def _do():
        if is_locked():
            return False
        state.write_lock(True, until, purpose)
        return True

    if _with_lockfile(_do):
        run_hook("lock", {
            "DS_EVENT": "lock",
            "DS_PURPOSE": purpose,
            "DS_MINUTES": "" if minutes is None else str(minutes),
            "DS_REASON": "",
            "DS_HELD": "{}",
        })
    return 0


def unlock(reason):
    reason = reason or ""

    def _do():
        if not is_locked():
            return ("noop", None, None)
        n = _reason_min()
        if n and len(reason) < n:
            return ("short", n, None)
        purpose = state.read_lock().get("purpose") or ""
        try:
            _append_log(
                f"{state.now_iso()} unlock purpose={_one_line(purpose)} reason={_one_line(reason)}"
            )
        except OSError:
            return ("log", None, None)
        # This command marks the boundary, so it claims the held records: the
        # hook's counts and the notice below come from the same claim.
        records = summary.take()
        state.write_lock(False, None, "")
        return ("ok", purpose, records)

    kind, extra, records = _with_lockfile(_do)
    if kind == "short":
        _notify("Reason too short", f"Write at least {extra} characters.")
        print(f"unlock needs at least {extra} characters", file=sys.stderr)
        return 1
    if kind == "log":
        _notify("Could not write unlock log", "The lock is unchanged.")
        return 1
    if kind == "ok":
        run_hook("unlock", {
            "DS_EVENT": "unlock",
            "DS_PURPOSE": extra,
            "DS_MINUTES": "",
            "DS_REASON": reason,
            "DS_HELD": json.dumps(summary.counts(records)),
        })
        summary.notice(records, _load_cfg())
    return 0


def expire_if_due():
    def _do():
        data = state.read_json(state.state_path("lock.json"), None)
        if not isinstance(data, dict) or not data.get("locked"):
            return False
        if is_locked():
            return False
        state.write_lock(False, None, "")
        return True

    return _with_lockfile(_do)


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
    return _cli_lock(args)


def cmd_unlock(args):
    return _cli_unlock(args)


def cmd_enter(args):
    return enter()


def cmd_leave(args):
    return leave()


def cmd_toggle(args):
    return toggle()


def _cli_lock(args):
    if is_locked():
        return 0
    duration = getattr(args, "duration", None)
    purpose_words = getattr(args, "purpose", None) or []
    if duration is None:
        try:
            result = ui.prompt_lock(_load_cfg())
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


def until_iso(minutes):
    """UTC deadline `minutes` from now, whole seconds: the form the lock and the exempt set store."""
    return (datetime.now(timezone.utc) + timedelta(minutes=int(minutes))).replace(
        microsecond=0
    ).isoformat()


def _one_line(text):
    return (text or "").replace("\n", " ").replace("\r", " ")


def _load_cfg():
    global _cfg_warned
    try:
        return config.load()
    except Exception:
        if not _cfg_warned:
            _cfg_warned = True
            _notify("Config invalid", "Using defaults.")
        return copy.deepcopy(DEFAULTS)


def _reason_min():
    return int(_load_cfg()["lock"]["reason_min_chars"])


def _log_path():
    raw = _load_cfg()["log"]
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
    raw = _load_cfg().get("hooks", {}).get(name) or []
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


def _go_to_space():
    try:
        r = subprocess.run(
            ["hyprctl", "dispatch", hypr.focus_workspace_lua(hypr.SPACE)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return 1
    return 0 if r.returncode == 0 else 1
