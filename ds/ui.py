"""Menu UI through omarchy-menu-select, omarchy-menu-input, and notices."""

import json
import subprocess

from ds import catalog, config, hypr

CHECK, UNCHECK = "󰄲", "󰄱"
_BOOL = (
    "nudges.app_banner", "nudges.block_page",
    "mute_sounds", "lock.ask_purpose",
)
_INT = ("lock.default_minutes", "lock.reason_min_chars", "summary.timeout_seconds")
_RO = ("keep_reachable", "hooks.lock", "hooks.unlock", "hooks.enter", "hooks.leave", "log")
_HOLD = ("off-space", "locked", "never")
_SETTINGS = (
    *[("bool", k) for k in _BOOL],
    ("cycle", "hold_notifications", _HOLD),
    ("cmd", "summary.command"),
    *[("int", k) for k in _INT],
    ("list", "list"),
    *[("ro", k) for k in _RO],
)


class Unavailable(Exception):
    """Menu binary missing or failed to launch."""


def _row(glyph, label, sub=""):
    return f"{glyph}\t{label}\t{sub}"


def _run(argv, timeout=None):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    except OSError as e:
        raise Unavailable(str(e)) from e
    if r.returncode == 0:
        return r.stdout
    if r.returncode == 1:
        return None
    raise Unavailable(f"{argv[0]} exited {r.returncode}")


def _idx(rows, out):
    got = (out or "").strip()
    for i, row in enumerate(rows):
        parts = str(row).split("\t")
        stripped = "\t".join(parts[1:]).strip() if len(parts) > 1 else str(row).strip()
        label = parts[1].strip() if len(parts) > 1 else stripped
        if got in (str(row).strip(), stripped, label):
            return i
    return None


def select(prompt, rows, timeout=None):
    rows = [str(r) for r in rows]
    if not rows:
        return None
    out = _run(["omarchy-menu-select", prompt, *rows], timeout=timeout)
    return None if out is None else _idx(rows, out)


def input(prompt, timeout=None):
    out = _run(["omarchy-menu-input", prompt], timeout=timeout)
    return None if out is None else out.rstrip("\r\n")


def notify(title, body, *, glyph=None, action=None, urgent=False):
    cmd = ["omarchy-notification-send"]
    if glyph:
        cmd += ["-g", str(glyph)]
    if urgent:
        cmd += ["-u", "critical"]
    cmd += [str(title), str(body)]
    if action:
        extra = action.split() if isinstance(action, str) else list(action)
        cmd += ["--exec", *extra]
    try:
        subprocess.run(cmd, capture_output=True, timeout=5)
    except Exception:
        pass


def prompt_lock(cfg):
    lock = (cfg or {}).get("lock")
    lock = lock if isinstance(lock, dict) else {}
    default = lock.get("default_minutes", 25)
    if type(default) is not int or default < 0:
        default = 25
    labels = (f"{default} minutes", "50 minutes", "90 minutes", "Until I unlock", "Other…")
    values = (default, 50, 90, None, "other")
    i = select("Lock for", [_row("", x) for x in labels])
    if i is None:
        return None
    mins = values[i]
    if mins == "other":
        raw = input("Minutes")
        if raw is None:
            return None
        try:
            mins = int(raw.strip())
            if mins < 0:
                raise ValueError
        except (TypeError, ValueError):
            notify("Invalid duration", "Enter a whole number of minutes ≥ 0.")
            return None
    purpose = ""
    if lock.get("ask_purpose", True):
        got = input("Purpose")
        purpose = "" if got is None else got
    return (mins, purpose)


def prompt_reason(min_chars):
    return input(f"Reason ({min_chars}+ characters)" if min_chars else "Reason")


def _locked():
    try:
        from ds import lock
        return bool(lock.is_locked())
    except Exception:
        return False


def _cfg_error(exc):
    notify("Invalid config", str(exc))
    return 1


def _mutate(fn):
    try:
        config.update(fn)
    except config.Busy:
        notify("Config busy", "Try again in a moment.")
        return False
    except config.Invalid as e:
        notify("Invalid", str(e))
        return False
    return True


def _edit_list():
    try:
        products = set(catalog.names())
        while True:
            cfg = config.load()
            listed = [config.display_name(e) for e in cfg["list"]]
            rows, acts = [], []
            for name in catalog.names():
                rows.append(_row(CHECK if name in listed else UNCHECK, name))
                acts.append(("t", name))
            for e in cfg["list"]:
                name = config.display_name(e)
                if name in products:
                    continue
                rows.append(_row(CHECK, name))
                acts.append(("t", name))
            rows += [_row("", "Add a site or app…"), _row("", "Back")]
            acts += [("a", None), ("b", None)]
            i = select("Edit list", rows)
            if i is None or acts[i][0] == "b":
                return
            kind, name = acts[i]
            if kind == "a":
                raw = input("Site or app")
                if not raw:
                    continue
                try:
                    entry = config.parse_add_entry(raw.strip())
                except config.Invalid as e:
                    notify("Invalid", str(e))
                    continue

                def add(cfg, entry=entry):
                    if not any(config.display_name(x) == config.display_name(entry) for x in cfg["list"]):
                        cfg["list"].append(entry)

                _mutate(add)
                continue

            def tog(cfg, name=name):
                if any(config.display_name(e) == name for e in cfg["list"]):
                    cfg["list"] = [e for e in cfg["list"] if config.display_name(e) != name]
                else:
                    cfg["list"].append(name)

            _mutate(tog)
    except (config.Invalid, OSError) as e:
        return _cfg_error(e)


def _fmt(cfg, key):
    v = config.get(cfg, key)
    if key == "summary.command" and isinstance(v, list):
        return "custom"
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v)


def _settings():
    try:
        while True:
            cfg = config.load()
            rows = [_row("", spec[1], "edit" if spec[0] == "list" else _fmt(cfg, spec[1])) for spec in _SETTINGS]
            rows.append(_row("", "Back"))
            i = select("Settings", rows)
            if i is None or i >= len(_SETTINGS):
                return
            spec = _SETTINGS[i]
            kind, key = spec[0], spec[1]
            if kind == "bool":
                _mutate(lambda c, key=key: config.set_value(c, key, not config.get(c, key)))
            elif kind == "cycle":
                opts = spec[2]

                def cycle(c, key=key, opts=opts):
                    cur = config.get(c, key)
                    nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else opts[0]
                    config.set_value(c, key, nxt)

                _mutate(cycle)
            elif kind == "cmd":
                _mutate(lambda c: config.set_value(
                    c, "summary.command", "off" if config.get(c, "summary.command") == "auto" else "auto",
                ))
            elif kind == "int":
                raw = input(key)
                if raw is None:
                    continue
                try:
                    n = int(raw.strip())
                    if n < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    notify("Invalid value", f"{key} must be an integer ≥ 0")
                    continue
                _mutate(lambda c, key=key, n=n: config.set_value(c, key, n))
            elif kind == "list":
                if _edit_list():
                    return 1
            else:
                notify("Read-only", f"Use: distractions config set {key} <json>")
    except (config.Invalid, OSError) as e:
        return _cfg_error(e)


def _lock_action(locked):
    from ds import lock
    try:
        cfg = config.load()
        if locked:
            min_chars = config.get(cfg, "lock.reason_min_chars")
            if min_chars == 0:
                return lock.unlock("")
            reason = prompt_reason(min_chars)
            return None if reason is None else lock.unlock(reason)
        picked = prompt_lock(cfg)
        return None if picked is None else lock.lock(*picked)
    except (config.Invalid, OSError) as e:
        return _cfg_error(e)


def menu():
    try:
        config.load()
        while True:
            locked = _locked()
            try:
                on = bool(hypr.on_space())
            except Exception:
                on = False
            i = select("Distraction space", [
                _row("", "Unlock…" if locked else "Lock…"),
                _row("", "Leave the space" if on else "Open the space"),
                _row("", "Edit list"),
                _row("", "Settings"),
            ])
            if i is None:
                return 0
            if i == 0:
                rc = _lock_action(locked)
                if rc is None:
                    continue
                return rc or 0
            if i == 1:
                from ds import lock
                return (lock.leave() if on else lock.enter()) or 0
            if i == 2:
                if _edit_list():
                    return 1
            elif i == 3:
                if _settings():
                    return 1
    except Unavailable:
        notify("Menu unavailable", "omarchy-menu-select is missing.")
        return 1
    except (config.Invalid, OSError) as e:
        return _cfg_error(e)


def cmd_menu(args):
    return menu()
