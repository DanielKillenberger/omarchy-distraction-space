"""Hyprland queries, named window rules, the three containment layers, and workspace cycle.

A window belongs on the space by class (the distraction profile's rule or a native
class), by process (its pid or an ancestor in the slice), or by adoption (a listed
product's web app running in another browser profile, which is closed and reopened
through `distractions open`). First match wins, every move is silent, and a window
that lands while the person is elsewhere raises the Opened banner.
"""

import hashlib
import json
import re
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path

from ds import catalog, cgroup, state

SPACE = "distraction"
WORKSPACE_EFFECT = f"name:{SPACE} silent"
RULE_HANDLES = "_G.omarchy_ds_rules"
PROFILE_RULE = "omarchy_ds_profile"
GLYPH = "󰈈"
# Adoption runs this checkout's CLI, the same path the banner actions name.
CLI = str(Path(__file__).resolve().parent.parent / "distractions")
OPEN_TIMEOUT = 30
ADOPTED_CAP = 256

_entries = None
_clients_cache = None
_clients_lock = threading.Lock()
# Addresses adoption has handled, oldest first; `closewindow` forgets one, the cap bounds the rest.
_adopted = OrderedDict()


def _reset_for_tests():
    global _entries, _clients_cache
    _entries = None
    _adopted.clear()
    with _clients_lock:
        _clients_cache = None


def _launch():
    # ds.launch imports this module; resolved at call time so neither import is circular.
    from ds import launch
    return launch


def _feedback():
    from ds import feedback
    return feedback


def hyprctl_json(*args):
    r = subprocess.run(
        ["hyprctl", "-j", *args], capture_output=True, text=True, timeout=5, check=True
    )
    return json.loads(r.stdout)


def clients_cached():
    global _clients_cache
    now = time.monotonic()
    with _clients_lock:
        if _clients_cache is not None:
            ts, data = _clients_cache
            if now - ts < 1.0:
                return data
        try:
            data = hyprctl_json("clients")
        except Exception:
            return None
        if not isinstance(data, list):
            return None
        _clients_cache = (now, data)
        return data


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
    _log_to(state.state_path("log"), msg)


def _log_to(path, msg):
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


def _native_classes(entry):
    """The entry's class patterns minus the version 2 per-host web-app pattern.

    A listed product's web-app window is never matched by its host class: the
    distraction profile's window is the profile rule's, any other profile's is
    adoption's.
    """
    if not isinstance(entry, dict):
        return []
    web = {catalog.pwa_class(h) for h in _launch().entry_hosts(entry)}
    return [c for c in entry.get("classes") or [] if isinstance(c, str) and c and c not in web]


def _rule_names(entries):
    """One rule per native class; the profile rule is added by `apply_rules`."""
    names, specs = [], []
    for entry in entries:
        raw = _entry_name(entry)
        for n, klass in enumerate(_native_classes(entry)):
            name = _rule_name(raw, n)
            names.append(name)
            specs.append((name, klass))
    return names, specs


def profile_rule_class():
    """Class pattern of every window of the distraction profile: one rule covers them all."""
    return r"^[a-z-]+-.+__-" + re.escape(_launch().PROFILE) + "$"


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


def focus_workspace_lua(name):
    """`hyprctl dispatch` argument on the Lua parser: focus workspace `name`."""
    return f"hl.dsp.focus({{ workspace = {lua_string(f'name:{name}')} }})"


def move_window_lua(address, workspace=f"name:{SPACE}"):
    """`hyprctl dispatch` argument on the Lua parser: silent move of one window by address."""
    return (
        f"hl.dsp.window.move({{ window = {lua_string(f'address:{address}')}, "
        f"workspace = {lua_string(workspace)}, follow = false }})"
    )


def close_window_lua(address):
    """`hyprctl dispatch` argument on the Lua parser: close one window by address."""
    return f"hl.dsp.window.close({{ window = {lua_string(f'address:{address}')} }})"


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
    global _entries
    entries, _extra = _normalize(expanded)
    _entries = entries
    names, specs = _rule_names(entries)
    names = [PROFILE_RULE, *names]
    specs = [(PROFILE_RULE, profile_rule_class()), *specs]
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


def _strip_www(host):
    h = (host or "").lower()
    if h.startswith("www."):
        return h[4:]
    return h


def entry_for_host(host):
    if not host:
        return None
    want = _strip_www(host if isinstance(host, str) else str(host))
    if not want:
        return None
    for entry in _current_entries():
        for h in entry.get("hosts") or []:
            if not isinstance(h, str) or not h:
                continue
            if _strip_www(h) == want:
                return entry
    return None


def _pattern_hit(pat, klass):
    try:
        return re.search(pat, klass) is not None
    except re.error:
        return pat == klass


def _class_matches(entry, klass):
    if not klass or not isinstance(entry, dict):
        return False
    return any(_pattern_hit(pat, klass) for pat in entry.get("classes") or [] if isinstance(pat, str) and pat)


def entry_clients_on_space(entry, clients):
    if not isinstance(entry, dict) or not entry.get("classes"):
        return False
    if not isinstance(clients, list):
        return False
    matched = [
        c
        for c in clients
        if isinstance(c, dict) and _class_matches(entry, c.get("class") or "")
    ]
    if not matched:
        return False
    for c in matched:
        ws = c.get("workspace")
        name = ws.get("name") if isinstance(ws, dict) else None
        if name != SPACE:
            return False
    return True


def _match_entry(klass):
    """The entry whose native class owns this window, or None."""
    if not klass:
        return None
    for entry in _current_entries():
        if any(_pattern_hit(pat, klass) for pat in _native_classes(entry)):
            return entry
    return None


def _webapp_class(host):
    """A Chromium web-app window for `host` or a subdomain of it; group 1 is its browser profile."""
    return re.compile(r"^[a-z-]+-(?:[a-z0-9-]+\.)*" + re.escape(host.lower()) + r"__-(.+)$")


def _webapp_entry(klass):
    """(entry, profile) when `klass` is a listed product's web-app window, else (None, None)."""
    if not klass:
        return None, None
    launch = _launch()
    for entry in _current_entries():
        for host in launch.entry_hosts(entry):
            m = _webapp_class(host).match(klass)
            if m:
                return entry, m.group(1)
    return None, None


def classify(klass, pid):
    """The three containment layers over one window, first match wins.

    Returns `("class" | "slice" | "adopt", entry)` or None. "class" is the profile
    rule or a native class (the entry is None for a profile window of an unlisted
    host); "slice" is a pid, or an ancestor within eight hops, in the slice, with
    an unreadable cgroup counting as outside; "adopt" is a listed product's web
    app in another browser profile, which cannot reach its host from there.
    """
    klass = klass or ""
    if re.match(profile_rule_class(), klass):
        return "class", _webapp_entry(klass)[0]
    entry = _match_entry(klass)
    if entry is not None:
        return "class", entry
    if isinstance(pid, int) and pid > 0 and cgroup.ancestor_in_slice(pid):
        return "slice", None
    entry, _profile = _webapp_entry(klass)
    if entry is not None:
        return "adopt", entry
    return None


def _on_space(client):
    ws = client.get("workspace")
    return isinstance(ws, dict) and ws.get("name") == SPACE


def contain(client, klass=None, opened=False):
    """Run the layers over one window: move or adopt it, then raise the Opened banner.

    `opened` marks a fresh `openwindow`, which the profile rule may already have
    placed on the space: the banner fires for it without a move. A scan or a move
    event announces only a window it moved. Returns the layer that claimed the
    window, or None.
    """
    if not isinstance(client, dict):
        return None
    klass = klass or client.get("class") or client.get("initialClass") or ""
    decision = classify(klass, client.get("pid"))
    if decision is None:
        return None
    layer, entry = decision
    name = _entry_name(entry) if isinstance(entry, dict) else None
    if layer == "adopt":
        landed = _adopt(client, name)
    elif _on_space(client):
        # Already there: a fresh window the rule placed is announced, a scan or
        # a move event of a window that was there all along is not.
        landed = opened
    else:
        # Off the space, fresh or not: only a move Hyprland accepted has landed.
        landed = move_to_space(client.get("address"))
    if name and landed:
        _feedback().opened(name)
    return layer


def move_to_space(address):
    """True when Hyprland accepted the move; a refused dispatch is logged by `_run`."""
    if not address:
        return False
    return _run("dispatch", move_window_lua(address)) is not None


def _adopt(client, name):
    """Layer 3, once per window address: reopen the product through `open`, then close the window.

    `open` runs first, so a failed launch leaves the window in place, moved to the
    space by class, with one log line. Returns False for an address already handled.
    """
    address = client.get("address")
    key = _norm_addr(address)
    if not key:
        return False
    if key in _adopted:
        # `open` already ran for this address. Only a close that Hyprland refused
        # is still owed, and it is retried here without launching anything.
        if _adopted[key] == "close-pending" and _run("dispatch", close_window_lua(address)) is not None:
            _adopted[key] = "done"
        return False
    _adopted[key] = "done"
    while len(_adopted) > ADOPTED_CAP:
        _adopted.popitem(last=False)
    why = _open(name)
    if why is None:
        if _run("dispatch", close_window_lua(address)) is None:
            _adopted[key] = "close-pending"
            _log(f"adopt: close of {address} refused; retried on its next event")
        return True
    _log(f"adopt: open {name} failed ({why}); window {address} moved by class")
    # Nothing new opened in the space: the window has landed only when the
    # fallback move actually happened.
    return not _on_space(client) and move_to_space(address)


def _open(name):
    """`distractions open <name>` from this checkout, waited on since it detaches the launch itself.

    None on exit 0, else why it failed.
    """
    try:
        r = subprocess.run(
            [CLI, "open", name],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=OPEN_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    if r.returncode == 0:
        return None
    err = (r.stderr or r.stdout or "").strip().splitlines()
    return f"exit {r.returncode}" + (f": {err[-1]}" if err else "")


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
    address = payload.split(",", 1)[0].strip()
    if not address:
        return
    if kind == "closewindow":
        _adopted.pop(_norm_addr(address), None)
        return
    if kind not in ("openwindow", "movewindow", "movewindowv2"):
        return
    client = _client_by_address(address)
    klass = client.get("class") if isinstance(client, dict) else ""
    if kind == "openwindow" and not klass:
        parts = payload.split(",", 3)
        if len(parts) >= 3:
            klass = parts[2]
    if not isinstance(client, dict):
        client = {"address": address}
    contain(client, klass, opened=kind == "openwindow")


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
    return _run("dispatch", focus_workspace_lua(name)) is not None


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
