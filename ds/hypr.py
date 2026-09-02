"""Hyprland queries, named window rules, silent moves, and workspace cycle."""

import hashlib
import json
import re
import subprocess
import time

from ds import state

SPACE = "distraction"
WORKSPACE_EFFECT = f"name:{SPACE} silent"
RULE_HANDLES = "_G.omarchy_ds_rules"
BANNER_S = 30
GLYPH = "󰈈"

_entries = None
_app_banner = True
_banner_at = {}


def _reset_for_tests():
    global _entries, _app_banner
    _entries = None
    _app_banner = True
    _banner_at.clear()


def hyprctl_json(*args):
    r = subprocess.run(
        ["hyprctl", "-j", *args], capture_output=True, text=True, timeout=5, check=True
    )
    return json.loads(r.stdout)


def active_workspace():
    try:
        data = hyprctl_json("activeworkspace")
    except Exception:
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name if isinstance(name, str) else None


def on_space():
    try:
        data = hyprctl_json("activeworkspace")
    except Exception as e:
        _log(f"hyprctl activeworkspace: {e}")
        return None
    return isinstance(data, dict) and data.get("name") == SPACE


def _log(msg):
    path = state.state_path("log")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{state.now_iso()} {msg}\n")
    except OSError:
        pass


def _run(*args):
    try:
        r = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=5)
    except Exception as e:
        _log(f"hyprctl {' '.join(args)}: {e}")
        return None
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        _log(f"hyprctl {' '.join(args)}: exit {r.returncode} {err}")
        return None
    return r


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "entry"


def _entry_name(entry):
    name = entry.get("name") if isinstance(entry, dict) else None
    return name if isinstance(name, str) and name else "entry"


def _rule_name(entry_name, n):
    raw = entry_name or "entry"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"omarchy-ds-{_slug(raw)}-{digest}-{n}"


def _normalize(expanded):
    extra = {}
    if isinstance(expanded, dict):
        extra = expanded
        items = expanded.get("list") or expanded.get("entries") or []
    elif isinstance(expanded, list):
        items = expanded
    else:
        items = []
    return [e for e in items if isinstance(e, dict)], extra


def _rule_names(entries):
    names, specs = [], []
    for entry in entries:
        raw = _entry_name(entry)
        for n, klass in enumerate(entry.get("classes") or []):
            if not isinstance(klass, str) or not klass:
                continue
            name = _rule_name(raw, n)
            names.append(name)
            specs.append((name, klass))
    return names, specs


def lua_string(value):
    """Double-quoted Lua literal for any Python string (regex patterns included)."""
    out = ['"']
    for ch in value:
        code = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif code < 32 or code == 127:
            out.append(f"\\{code:03d}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def set_rule_lua(name, klass, workspace=WORKSPACE_EFFECT):
    """Lua for `hyprctl eval`: retire any previous handle under `name`, then create the rule.

    `hyprctl keyword` refuses on the Lua config parser (exit 0, message on stdout), so
    rules go through `hl.window_rule`. Handles live in a Lua global table so a later
    disable or re-apply can reach them. The old handle is disabled first so two rules
    never share a name (whether Hyprland replaces or duplicates by name is unverified).
    A create error propagates so eval exits nonzero; `apply_rules` then re-sets the
    name from its recorded class.
    """
    key = lua_string(name)
    # The first line never starts with "-": hyprctl parses a leading "--" as a flag.
    return "\n".join(
        [
            f"local rules = {RULE_HANDLES} or {{}}  -- omarchy-ds set {name}",
            f"{RULE_HANDLES} = rules",
            f"local old = rules[{key}]",
            "if old ~= nil then pcall(function() old:set_enabled(false) end) end",
            "local rule = hl.window_rule({ "
            f"name = {key}, match = {{ class = {lua_string(klass)} }}, workspace = {lua_string(workspace)}"
            " })",
            f"rules[{key}] = rule",
        ]
    )


def disable_rule_lua(name):
    """Lua for `hyprctl eval`: disable the stored handle for `name`; a missing handle is a no-op."""
    key = lua_string(name)
    return "\n".join(
        [
            f"local rules = {RULE_HANDLES}  -- omarchy-ds disable {name}",
            f"local rule = rules and rules[{key}]",
            f"if rule ~= nil then rules[{key}] = nil; pcall(function() rule:set_enabled(false) end) end",
        ]
    )


def is_config_reload(line):
    """True for the socket2 `configreloaded` event, which drops every eval-created rule."""
    raw = (line or "").strip() if isinstance(line, str) else ""
    if raw.startswith(">>"):
        raw = raw[2:]
    return raw.split(">>", 1)[0] == "configreloaded"


def _read_rule_names():
    data = state.read_json(state.state_path("rules.json"), [])
    if isinstance(data, list):
        return [n for n in data if isinstance(n, str)]
    if isinstance(data, dict) and isinstance(data.get("names"), list):
        return [n for n in data["names"] if isinstance(n, str)]
    return []


def apply_rules(expanded):
    global _entries, _app_banner
    entries, extra = _normalize(expanded)
    _entries = entries
    nudges = extra.get("nudges")
    if isinstance(nudges, dict) and "app_banner" in nudges:
        _app_banner = bool(nudges["app_banner"])
    names, specs = _rule_names(entries)
    if len(names) != len(set(names)):
        _log("apply_rules: generated windowrule names collide; skipped")
        return False
    old = _read_rule_names()
    old_specs = _read_rule_specs()
    created = []
    for name, klass in specs:
        if _run("eval", set_rule_lua(name, klass, WORKSPACE_EFFECT)) is None:
            _rollback_created(created + [name], old_specs)
            _notify("Distraction list", "Window rules could not be updated. Keeping the previous set.")
            return False
        created.append(name)
    desired = set(names)
    recorded = list(names)
    seen = set(names)
    for name in old:
        if name not in desired:
            if _run("eval", disable_rule_lua(name)) is None:
                if name not in seen:
                    recorded.append(name)
                    seen.add(name)
    new_specs = dict(specs)
    for name in recorded:
        if name not in new_specs and name in old_specs:
            new_specs[name] = old_specs[name]
    state.write_json(state.state_path("rules.json"), recorded)
    state.write_json(state.state_path("rule-specs.json"), new_specs)
    return True


def _read_rule_specs():
    data = state.read_json(state.state_path("rule-specs.json"), {})
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v}


def _rollback_created(created, old_specs):
    """Restore the previous active set after a failed batch.

    Names that existed before are re-set with their recorded class; names this batch
    brought into being are disabled. `created` includes the name whose create just
    failed: the fragment retires the old handle before creating, so a Lua-level
    failure leaves that name with no live rule until this re-set puts it back. Both registries stay untouched so the next apply
    retries the whole set. A name with no recorded class (registry written before
    rule-specs.json existed) is disabled.
    """
    for name in reversed(created):
        prev = old_specs.get(name)
        if prev is not None:
            _run("eval", set_rule_lua(name, prev, WORKSPACE_EFFECT))
        else:
            _run("eval", disable_rule_lua(name))


def _notify(title, body):
    try:
        subprocess.run(
            ["omarchy-notification-send", "-g", GLYPH, title, body],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        pass


def _current_entries():
    if _entries is not None:
        return _entries
    entries, _extra = _normalize(state.read_expansion())
    return entries


def _want_banner():
    exp = state.read_expansion()
    if isinstance(exp, dict):
        nudges = exp.get("nudges")
        if isinstance(nudges, dict) and "app_banner" in nudges:
            return bool(nudges["app_banner"])
    try:
        from ds.config import config_path
        path = config_path()
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            nudges = raw.get("nudges") if isinstance(raw, dict) else None
            if isinstance(nudges, dict) and "app_banner" in nudges:
                return bool(nudges["app_banner"])
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return _app_banner


def _norm_addr(a):
    s = str(a or "").lower()
    return s[2:] if s.startswith("0x") else s


def _client_by_address(address):
    try:
        clients = hyprctl_json("clients")
    except Exception as e:
        _log(f"hyprctl clients: {e}")
        return None
    if not isinstance(clients, list):
        return None
    want = _norm_addr(address)
    for c in clients:
        if isinstance(c, dict) and _norm_addr(c.get("address")) == want:
            return c
    return None


def _match_entry(klass):
    if not klass:
        return None
    for entry in _current_entries():
        for pat in entry.get("classes") or []:
            if not isinstance(pat, str) or not pat:
                continue
            try:
                if re.search(pat, klass):
                    return entry
            except re.error:
                if pat == klass:
                    return entry
    return None


def move_to_space(address):
    if not address:
        return
    _run("dispatch", "movetoworkspacesilent", f"name:{SPACE},address:{address}")


def _maybe_banner(name):
    now = time.monotonic()
    last = _banner_at.get(name)
    if last is not None and now - last < BANNER_S:
        return
    _banner_at[name] = now
    try:
        subprocess.run(
            [
                "omarchy-notification-send",
                "-g",
                GLYPH,
                f"{name} lives in the distraction space",
                "Super+D opens it.",
                "--exec",
                "distractions enter",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        pass


def handle_event(line):
    try:
        _handle_event(line)
    except Exception as e:
        _log(f"handle_event: {e}")


def _handle_event(line):
    if not isinstance(line, str):
        return
    raw = line.strip()
    if raw.startswith(">>"):
        raw = raw[2:]
    if ">>" not in raw:
        return
    kind, payload = raw.split(">>", 1)
    if kind not in ("openwindow", "movewindow", "movewindowv2"):
        return
    address = payload.split(",", 1)[0].strip()
    if not address:
        return
    client = _client_by_address(address)
    klass = client.get("class") if isinstance(client, dict) else ""
    if kind == "openwindow" and not klass:
        parts = payload.split(",", 3)
        if len(parts) >= 3:
            klass = parts[2]
    if isinstance(client, dict) and not klass:
        klass = client.get("initialClass") or ""
    match = _match_entry(klass)
    if match is None:
        return
    ws_name = None
    if isinstance(client, dict) and isinstance(client.get("workspace"), dict):
        ws_name = client["workspace"].get("name")
    addr = client.get("address") if isinstance(client, dict) else address
    if ws_name != SPACE:
        move_to_space(addr or address)
    if _want_banner():
        here = on_space()
        if here is False:
            _maybe_banner(match.get("name") or klass)
        elif here is None:
            _log("on_space unknown; skipping banner")


def cycle(direction):
    delta = -1 if direction in ("prev", "previous", -1, "<") else 1
    try:
        spaces = hyprctl_json("workspaces")
        active = hyprctl_json("activeworkspace")
    except Exception as e:
        _log(f"hyprctl workspaces: {e}")
        return False
    if not isinstance(spaces, list) or not isinstance(active, dict):
        return False
    occupied = [
        w
        for w in spaces
        if isinstance(w, dict)
        and w.get("name") != SPACE
        and int(w.get("windows") or 0) > 0
    ]
    occupied.sort(key=lambda w: w.get("id") or 0)
    if not occupied:
        return True
    ids = [w.get("id") for w in occupied]
    names = {w.get("id"): w.get("name") for w in occupied}
    cur = active.get("id")
    if cur in ids:
        dest = ids[(ids.index(cur) + delta) % len(ids)]
    elif cur is None:
        dest = ids[0] if delta > 0 else ids[-1]
    elif delta > 0:
        dest = next((i for i in ids if i > cur), ids[0])
    else:
        dest = next((i for i in reversed(ids) if i < cur), ids[-1])
    name = names.get(dest)
    if not name:
        return True
    return _run("dispatch", "workspace", f"name:{name}") is not None


def cmd_next(args):
    try:
        return 0 if cycle("next") else 1
    except Exception as e:
        _log(f"next: {e}")
        return 1


def cmd_prev(args):
    try:
        return 0 if cycle("prev") else 1
    except Exception as e:
        _log(f"prev: {e}")
        return 1
