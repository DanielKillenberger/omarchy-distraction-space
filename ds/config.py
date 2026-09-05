"""Schema, load/save, flocked update, and list/config CLI commands."""

import copy
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from ds import state
from ds.catalog import DEFAULT_LIST, expand, is_class_entry, is_hostname, load_catalog

HOLD_VALUES = ("off-space", "locked", "never")
# A release is a pause, not a policy change: one week is the longest deadline a
# person can ask for, and it keeps the ISO deadline representable.
RELEASE_MAX_MINUTES = 7 * 24 * 60
NUDGE_KEYS = ("app_banner", "block_page")
HOOK_NAMES = ("lock", "unlock", "enter", "leave")
DEFAULTS = {
    "list": list(DEFAULT_LIST),
    "keep_reachable": [],
    "nudges": {"app_banner": True, "block_page": True},
    "site_block": {"enabled": True, "pass_through": True},
    "browser": "auto",
    "open_links_in_space": True,
    "containment": {"snap_back": True, "release_minutes": 30},
    "hold_notifications": "off-space",
    "mute_sounds": True,
    "lock": {"default_minutes": 25, "ask_purpose": True, "reason_min_chars": 50},
    "summary": {"command": "off", "timeout_seconds": 60},
    "hooks": {"lock": [], "unlock": [], "enter": [], "leave": []},
    "log": "~/.local/state/omarchy/distraction-space/log",
}


class Invalid(ValueError):
    pass


class Busy(Exception):
    pass


def omarchy_dir() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    base = Path(raw) if raw else Path.home() / ".config"
    return base / "omarchy"


def config_path() -> Path:
    return omarchy_dir() / "distraction-space.json"


def _bool(v):
    return type(v) is bool


def _nat(v):
    return type(v) is int and v >= 0


def _pos(v):
    return type(v) is int and v >= 1


def _argv(v):
    return isinstance(v, list) and v and all(isinstance(x, str) and x for x in v)


def _need(ok, key):
    if not ok:
        raise Invalid(f"{key}: invalid")


def display_name(entry):
    if isinstance(entry, dict):
        n = entry.get("name")
        return n if isinstance(n, str) else ""
    return str(entry) if entry is not None else ""


def _class_regex_ok(s):
    if not (isinstance(s, str) and s):
        return False
    try:
        re.compile(s)
    except re.error:
        return False
    return True


def _str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _hosts_ok(hosts):
    return isinstance(hosts, list) and bool(hosts) and all(isinstance(h, str) and is_hostname(h) for h in hosts)


def _senders_ok(v):
    return _str_list(v)


def _audio_ok(v):
    if not isinstance(v, dict):
        return False
    for k, val in v.items():
        if k not in ("name", "binary") or not _str_list(val):
            return False
    return True


def valid_list_entry(entry):
    if isinstance(entry, str):
        if is_class_entry(entry):
            return _class_regex_ok(entry[6:])
        return is_hostname(entry) or entry in load_catalog()
    if not isinstance(entry, dict):
        return False
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return False
    has_c, has_h = "class" in entry, "hosts" in entry
    if not has_c and not has_h:
        return False
    if has_c and not _class_regex_ok(entry["class"]):
        return False
    if has_h and not _hosts_ok(entry["hosts"]):
        return False
    if "senders" in entry and not _senders_ok(entry["senders"]):
        return False
    if "audio" in entry and not _audio_ok(entry["audio"]):
        return False
    return True


def parse_add_entry(s):
    entry = s
    if isinstance(s, str) and s.lstrip().startswith("{"):
        try:
            entry = json.loads(s)
        except json.JSONDecodeError:
            raise Invalid(f"list: invalid entry {s!r}") from None
    if valid_list_entry(entry):
        return entry
    raise Invalid(f"list: invalid entry {s!r}")


def validate(cfg):
    _need(isinstance(cfg, dict), "config")
    _need(isinstance(cfg.get("list"), list) and all(map(valid_list_entry, cfg["list"])), "list")
    kr = cfg.get("keep_reachable")
    _need(isinstance(kr, list) and all(isinstance(h, str) and is_hostname(h) for h in kr), "keep_reachable")
    nudges = cfg.get("nudges")
    _need(isinstance(nudges, dict), "nudges")
    for k in NUDGE_KEYS:
        _need(k in nudges and _bool(nudges[k]), f"nudges.{k}")
    sb = cfg.get("site_block")
    _need(isinstance(sb, dict), "site_block")
    _need(_bool(sb.get("enabled")), "site_block.enabled")
    _need(_bool(sb.get("pass_through")), "site_block.pass_through")
    browser = cfg.get("browser")
    _need(browser == "auto" or _argv(browser), "browser")
    _need(_bool(cfg.get("open_links_in_space")), "open_links_in_space")
    containment = cfg.get("containment")
    _need(isinstance(containment, dict), "containment")
    _need(_bool(containment.get("snap_back")), "containment.snap_back")
    minutes = containment.get("release_minutes")
    _need(_pos(minutes) and minutes <= RELEASE_MAX_MINUTES, "containment.release_minutes")
    _need(cfg.get("hold_notifications") in HOLD_VALUES, "hold_notifications")
    _need(_bool(cfg.get("mute_sounds")), "mute_sounds")
    lock = cfg.get("lock")
    _need(isinstance(lock, dict), "lock")
    _need(_nat(lock.get("default_minutes")), "lock.default_minutes")
    _need(_bool(lock.get("ask_purpose")), "lock.ask_purpose")
    _need(_nat(lock.get("reason_min_chars")), "lock.reason_min_chars")
    summary = cfg.get("summary")
    _need(isinstance(summary, dict), "summary")
    cmd = summary.get("command")
    _need(cmd in ("auto", "off") or _argv(cmd), "summary.command")
    _need(_nat(summary.get("timeout_seconds")), "summary.timeout_seconds")
    hooks = cfg.get("hooks")
    _need(isinstance(hooks, dict), "hooks")
    for name in HOOK_NAMES:
        _need(name in hooks and isinstance(hooks[name], list) and all(_argv(x) for x in hooks[name]), f"hooks.{name}")
    log = cfg.get("log")
    _need(isinstance(log, str) and log, "log")


def _merge(raw):
    cfg = copy.deepcopy(DEFAULTS)
    for k, v in raw.items():
        if k in cfg and isinstance(cfg[k], dict) and isinstance(v, dict):
            cfg[k] = {**cfg[k], **v}
        else:
            cfg[k] = v
    return cfg


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _legacy_to_entry(item):
    if valid_list_entry(item):
        return item
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    if not (isinstance(name, str) and name):
        return None
    built = {"name": name}
    klass = item.get("class")
    if not (isinstance(klass, str) and klass):
        klass = item.get("window_class")
    if _class_regex_ok(klass):
        built["class"] = klass
    hosts = item.get("hosts")
    if isinstance(hosts, list):
        kept = [h for h in hosts if isinstance(h, str) and is_hostname(h)]
        if kept:
            built["hosts"] = kept
    if "senders" in item and _senders_ok(item["senders"]):
        built["senders"] = list(item["senders"])
    if "audio" in item and _audio_ok(item["audio"]):
        built["audio"] = dict(item["audio"])
    if "class" in built or "hosts" in built:
        return built if valid_list_entry(built) else None
    return name if valid_list_entry(name) else None


def _legacy_sources():
    items = []
    found = False
    log = None
    app_data = _read_json(omarchy_dir() / "app-list.json")
    if isinstance(app_data, list):
        found = True
        items.extend(app_data)
    focus_data = _read_json(omarchy_dir() / "focus.json")
    if isinstance(focus_data, dict):
        raw_log = focus_data.get("log")
        if isinstance(raw_log, str) and raw_log:
            log = raw_log
        dest = focus_data.get("destinations")
        if isinstance(dest, list):
            found = True
            items.extend(dest)
    return items, found, log


def _seed():
    cfg = copy.deepcopy(DEFAULTS)
    items, found, log = _legacy_sources()
    if found:
        seen = []
        names = set()
        for item in items:
            entry = _legacy_to_entry(item)
            if entry is None:
                continue
            key = display_name(entry)
            if key in names:
                continue
            names.add(key)
            seen.append(entry)
        cfg["list"] = seen
    if log:
        cfg["log"] = log
    return cfg


# The one default that stays out of the file until something sets it: setup
# asks about links exactly once, and "asked" has to survive every other write
# (a `list add`, a menu save) between the first load and the answer.
LINKS_KEY = "open_links_in_space"


def save(cfg):
    validate(cfg)
    state.write_json(config_path(), cfg)


def links_answered() -> bool:
    """Whether the config file itself states `open_links_in_space`.

    In memory the key is always present at its default; in the file it appears
    once setup's question was answered or `config set` named it.
    """
    raw = _read_json(config_path())
    return isinstance(raw, dict) and LINKS_KEY in raw


def set_links(value: bool):
    """Answer the link question: the key written explicitly, every other key kept as it is."""
    def answer(cfg):
        cfg[LINKS_KEY] = value

    return update(answer)


def _read():
    path = config_path()
    if not path.exists():
        cfg = _seed()
        validate(cfg)
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise Invalid("config: invalid JSON") from e
    if not isinstance(raw, dict):
        raise Invalid("config: invalid JSON")
    cfg = _merge(raw)
    validate(cfg)
    return cfg


def load():
    if not config_path().exists():
        return update(lambda cfg: None)
    return _read()


def _lock_timeout(explicit=None):
    if explicit is not None:
        return float(explicit)
    raw = os.environ.get("DS_CONFIG_LOCK_TIMEOUT")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return 5.0


def _acquire(fd, timeout):
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Busy("config busy")
            time.sleep(min(0.05, remaining))


def update(fn, timeout=None):
    timeout = _lock_timeout(timeout)
    lock_path = state.runtime_path("distraction-space.config.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lf:
        _acquire(lf, timeout)
        try:
            answered = links_answered()
            cfg = _read()
            if not answered:
                # `fn` sees the file's own keys: an assignment, whatever the
                # value, is the answer; an untouched default stays out of the file.
                del cfg[LINKS_KEY]
            result = fn(cfg)
            if result is not None:
                cfg = result
            answered = LINKS_KEY in cfg
            cfg = _merge(cfg)
            validate(cfg)
            state.write_json(config_path(), cfg if answered else {k: v for k, v in cfg.items() if k != LINKS_KEY})
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    try:
        state.request_reload()
    except Exception:
        pass
    return cfg


def is_schema_key(dotkey):
    cur = DEFAULTS
    if not dotkey:
        return False
    for part in dotkey.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def get(cfg, dotkey):
    cur = cfg
    for part in dotkey.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotkey)
        cur = cur[part]
    return cur


def set_value(cfg, dotkey, value):
    if not is_schema_key(dotkey):
        raise Invalid(f"{dotkey}: unknown key")
    parts = dotkey.split(".")
    cur = cfg
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _parse_value(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _fail(exc):
    print(str(exc), file=sys.stderr)
    return 1


def cmd_config(args):
    cmd = getattr(args, "config_cmd", None)
    if not cmd:
        return 2
    try:
        if cmd == "path":
            print(config_path())
            return 0
        if cmd == "get":
            print(json.dumps(get(load(), args.key)))
            return 0
        if cmd == "set":
            update(lambda cfg: set_value(cfg, args.key, _parse_value(args.value)))
            return 0
        if cmd == "edit":
            load()
            raw = os.environ.get("EDITOR")
            cmdv = shlex.split(raw) if raw else []
            if not cmdv:
                cmdv = ["omarchy-launch-editor"]
            r = subprocess.run([*cmdv, str(config_path())])
            return 0 if r.returncode == 0 else 1
    except KeyError:
        print(f"{getattr(args, 'key', '')}: unknown key", file=sys.stderr)
        return 1
    except Busy:
        print("config busy", file=sys.stderr)
        return 1
    except (Invalid, FileNotFoundError) as e:
        return _fail(e)
    return 2


def cmd_list(args):
    sub = getattr(args, "list_cmd", None)
    try:
        if sub is None:
            for entry in load()["list"]:
                print(display_name(entry))
            return 0
        if sub == "expand":
            print(json.dumps(expand(load()), indent=2))
            return 0
        if sub == "add":
            entry = parse_add_entry(args.entry)

            def add(cfg):
                if not any(display_name(e) == display_name(entry) for e in cfg["list"]):
                    cfg["list"].append(entry)

            update(add)
            return 0
        if sub == "remove":
            def remove(cfg):
                new = [e for e in cfg["list"] if display_name(e) != args.name]
                if len(new) == len(cfg["list"]):
                    raise KeyError(args.name)
                cfg["list"] = new

            update(remove)
            return 0
    except KeyError:
        print(f"list: {getattr(args, 'name', '')} not found", file=sys.stderr)
        return 1
    except Busy:
        print("config busy", file=sys.stderr)
        return 1
    except Invalid as e:
        return _fail(e)
    return 2
