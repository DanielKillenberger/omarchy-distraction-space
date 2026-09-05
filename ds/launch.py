"""`distractions open`: the single way into the slice, and the forwarder for everything else.

A target is a URL, a list entry name, or a catalog name, in that order. A web
target runs the distraction browser as a transient scope in `app-distraction.slice`
with the profile flags; a native target runs its desktop entry's `Exec` line the
same way. Everything else is forwarded to the handler setup recorded, outside
the slice, the way that handler would have run it: a URL whose host is neither
listed nor a subdomain of a listed host, no target at all (Omarchy's browser
keybind runs the default browser's Exec with nothing, or with a private-window
flag), and `--app <url>` for an unlisted URL (what `omarchy-launch-webapp`
does). Browser flags pass through to the forward unchanged; a launch into the
space has its own flags and ignores them.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ds import catalog, cgroup, config, hypr, state, ui

PROFILE = "Distraction"
HANDLER_ID = "io.github.danielkillenberger.distraction-space.desktop"
FALLBACK_FORWARDER = "omarchy-launch-browser"
CHROMIUM_FAMILY = ("google-chrome", "brave", "microsoft-edge", "opera", "vivaldi", "helium")
DEFAULT_BROWSER_ID = "chromium.desktop"
SCOPE_ARGV = ["systemd-run", "--user", "--scope", "--quiet", "--collect", f"--slice={cgroup.SLICE}", "--"]
USAGE = "usage: distractions open [--app] [http(s)-url | list entry | catalog name] [browser flags...]"

_EXEC_LINE = re.compile(r"^\s*Exec\s*=\s*(.*?)\s*$")
_FIELD_CODE = re.compile(r"%(.)")
_KEY_ESCAPES = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass
class Target:
    kind: str  # "web" | "native" | "forward"
    url: str | None = None
    entry: dict | None = None
    desktop: str | None = None
    restricted: bool = True


def _log(msg):
    hypr._log_to(state.state_path("log"), f"open: {msg}")


def _notice(title, body):
    print(f"{title}: {body}", file=sys.stderr)
    ui.notify(title, body)


# --- hosts -------------------------------------------------------------------

def _norm_host(host):
    """Lower-cased, without a trailing dot or a port. `www.` stays: the list names its aliases itself."""
    h = str(host or "").strip().lower().rstrip(".")
    if h.count(":") == 1:
        name, port = h.rsplit(":", 1)
        if port.isdigit():
            h = name
    return h


def entry_hosts(entry):
    """The listed hosts plus the PWA host carried only in the entry's class pattern."""
    if not isinstance(entry, dict):
        return []
    out = []
    for pat in entry.get("classes") or []:
        host = catalog.pwa_host(pat)
        if host and catalog.is_hostname(host) and host not in out:
            out.append(host)
    for h in entry.get("hosts") or []:
        if isinstance(h, str) and h and h not in out:
            out.append(h)
    return out


def classify_host(host, exp):
    """The entry whose host equals `host` or is a parent domain of it, or None.

    One classifier serves `open` and the URL handler check. `exp` is the saved
    expansion (dict or bare list); `www.` and a port are ignored on both sides.
    """
    want = _norm_host(host)
    if not want:
        return None
    entries, _extra = hypr._normalize(exp)
    for entry in entries:
        for h in entry_hosts(entry):
            base = _norm_host(h)
            if base and (want == base or want.endswith("." + base)):
                return entry
    return None


def _entry_url(entry):
    hosts = entry_hosts(entry)
    return f"https://{hosts[0]}/" if hosts else None


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
# RFC 3986 authority: optional userinfo, then a reg-name or a bracketed IP
# literal, then an optional port. Nothing outside those character sets, so a
# backslash, a space, or a second `@` never reaches the host split.
_AUTHORITY = re.compile(
    r"^(?:(?:[A-Za-z0-9\-._~!$&'()*+,;=:]|%[0-9A-Fa-f]{2})*@)?"
    r"(?:\[[0-9A-Fa-f:.]+\]|(?:[A-Za-z0-9\-._~!$&'()*+,;=]|%[0-9A-Fa-f]{2})+)"
    r"(?::[0-9]*)?$"
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _url_host(url):
    """The host of an http(s) URL whose authority is well formed, else None.

    A bracketed IPv6 literal that does not close, a space in the authority, or
    a port outside 1-65535 makes the whole argument unusable, so `open` can
    exit 2 instead of forwarding something no handler could take.
    """
    # urlsplit drops tabs and newlines before parsing; a URL carrying them is
    # not one anybody typed, so it is refused whole rather than cleaned.
    if _CONTROL.search(url):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in ("http", "https"):
            return None
        if not _AUTHORITY.match(parts.netloc):
            return None
        host, port = parts.hostname, parts.port
    except ValueError:
        return None
    if not host or port is not None and not 1 <= port <= 65535:
        return None
    if host.startswith("[") or ":" in host:
        # IPv6 literal, already validated by urlsplit's bracket handling.
        return host
    labels = host.rstrip(".").split(".")
    if not all(_HOST_LABEL.match(label) for label in labels):
        return None
    return host


# --- target resolution -------------------------------------------------------

def _find_name(name, names):
    want = name.casefold()
    for n in names:
        if isinstance(n, str) and n.casefold() == want:
            return n
    return None


def _entry_target(entry, restricted):
    desktop = entry.get("desktop")
    if isinstance(desktop, str) and desktop:
        return Target("native", entry=entry, desktop=desktop, restricted=restricted)
    url = _entry_url(entry)
    if url is None:
        return None
    return Target("web", url=url, entry=entry, restricted=restricted)


def resolve_target(arg, exp, cat):
    """A Target for `arg`, or None when it is unusable (exit 2 territory).

    An argument carrying a URL scheme is a URL and nothing else; only http(s)
    resolves. Otherwise a list entry name, otherwise a catalog name, which
    launches unrestricted.
    """
    arg = (arg or "").strip()
    if not arg:
        return None
    if _SCHEME.match(arg):
        host = _url_host(arg)
        if host is None:
            return None
        entry = classify_host(host, exp)
        return Target("web" if entry is not None else "forward", url=arg, entry=entry)
    entries, _extra = hypr._normalize(exp)
    by_name = {e["name"]: e for e in entries if isinstance(e.get("name"), str)}
    name = _find_name(arg, by_name)
    if name is not None:
        return _entry_target(by_name[name], True)
    name = _find_name(arg, cat if isinstance(cat, dict) else {})
    if name is not None:
        entry = catalog.expand_entry(name)
        return _entry_target(entry, False) if entry else None
    return None


# --- desktop entries ---------------------------------------------------------

def data_home():
    raw = os.environ.get("XDG_DATA_HOME")
    return Path(raw) if raw else Path.home() / ".local" / "share"


def _share_dirs():
    """Where desktop files are looked up: the same order `omarchy-launch-webapp` uses,
    with `XDG_DATA_HOME` and `XDG_DATA_DIRS` honored for the person's and the system's halves."""
    raw = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    system = [Path(d) for d in raw.split(":") if d]
    return [data_home(), Path.home() / ".nix-profile" / "share", *system]


def desktop_file(desktop_id):
    """The first desktop file for `desktop_id` across the share dirs, or None.

    A catalog id has no suffix (`org.telegram.desktop` names
    `org.telegram.desktop.desktop`); an `xdg-settings` id carries it. Both
    spellings are tried, suffixed first. A path-shaped id is refused.
    """
    for path in desktop_files(desktop_id):
        return path
    return None


def desktop_files(desktop_id):
    """Every desktop file for `desktop_id` across the share dirs, nearest first."""
    if not isinstance(desktop_id, str) or not desktop_id or "/" in desktop_id or desktop_id.startswith("."):
        return
    names = [desktop_id + ".desktop"]
    if desktop_id.endswith(".desktop"):
        names.append(desktop_id)
    for d in _share_dirs():
        for name in names:
            path = d / "applications" / name
            if path.is_file():
                yield path


def _is_own_launcher(argv):
    """True for an Exec that is this plugin's `distractions open ...`: setup writes such
    an entry in front of a native app's system entry, and a native launch that
    resolved to it would only launch itself again."""
    return bool(argv) and Path(argv[0]).name == "distractions" and argv[1:2] == ["open"]


def read_exec(path):
    """The `Exec=` value of the `[Desktop Entry]` group, or None.

    Only the main group counts: an action group's `Exec` (`[Desktop Action new]`)
    is a different command and must never stand in for the handler.
    """
    data = state.read_bounded(path)
    if data is None:
        return None
    in_main = False
    for line in data.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_main:
                return None
            in_main = stripped == "[Desktop Entry]"
            continue
        if not in_main:
            continue
        m = _EXEC_LINE.match(line)
        if m:
            return m.group(1)
    return None


def _key_unescape(value):
    out, i = [], 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value) and value[i + 1] in _KEY_ESCAPES:
            out.append(_KEY_ESCAPES[value[i + 1]])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_exec(value):
    """Argv from an `Exec` value per the Desktop Entry spec, or None when it is empty or unbalanced.

    Key-file escapes (`\\s`, `\\n`, `\\t`, `\\r`, `\\\\`) are applied first. Then
    the argument grammar the spec shares with `g_shell_parse_argv`: double
    quotes with backslash escapes for `"`, backtick, `$`, and `\\`; single
    quotes taken literally; outside quotes a backslash escapes the next
    character. An unterminated quote or a trailing backslash is unusable.
    Field codes are left in place for `expand_fields`.
    """
    if not isinstance(value, str):
        return None
    text = _key_unescape(value)
    argv, cur, i, n = [], None, 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            cur = "" if cur is None else cur
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\":
                    if i + 1 >= n:
                        return None
                    if text[i + 1] in '"`$\\':
                        i += 1
                cur += text[i]
                i += 1
            if i >= n:
                return None
            i += 1
        elif c == "'":
            cur = "" if cur is None else cur
            i += 1
            while i < n and text[i] != "'":
                cur += text[i]
                i += 1
            if i >= n:
                return None
            i += 1
        elif c == "\\":
            if i + 1 >= n:
                return None
            cur = (cur or "") + text[i + 1]
            i += 2
        elif c.isspace():
            if cur is not None:
                argv.append(cur)
                cur = None
            i += 1
        else:
            cur = (cur or "") + c
            i += 1
    if cur is not None:
        argv.append(cur)
    return argv or None


def expand_fields(argv, url=None):
    """Substitute `%u`/`%U`/`%f`/`%F` with `url`, `%%` with `%`, drop every other code.

    An argument that was only a code and got nothing substituted disappears. With
    a URL and no code to carry it, the URL is appended, which is how a handler
    that takes it positionally would have received it.
    """
    out, carried = [], False

    def sub(m, target):
        nonlocal carried
        code = m.group(1)
        if code == "%":
            return "%"
        if code in "uUfF" and target is not None:
            carried = True
            return target
        return ""

    for arg in argv:
        if _FIELD_CODE.fullmatch(arg):
            value = sub(_FIELD_CODE.fullmatch(arg), url)
            if value:
                out.append(value)
            continue
        out.append(_FIELD_CODE.sub(lambda m: sub(m, url), arg))
    if url is not None and not carried:
        out.append(url)
    return out


def exec_argv(desktop_id, url=None, skip_own=False):
    """The launchable argv of `<desktop_id>.desktop`, or None when the file or its Exec is unusable.

    With `skip_own`, an entry whose Exec is this plugin's own launcher is passed
    over for the next file of the same id, which is the shadowed system entry.
    """
    for path in desktop_files(desktop_id):
        argv = parse_exec(read_exec(path))
        if not argv:
            # An unusable file nearer in the search order does not hide a good one behind it.
            continue
        if skip_own and _is_own_launcher(argv):
            continue
        return expand_fields(argv, url) or None
    return None


# --- browser -----------------------------------------------------------------

def _default_browser_id():
    try:
        env = dict(os.environ)
        env.pop("BROWSER", None)  # xdg-settings refuses to answer while BROWSER is set; Omarchy exports it
        r = subprocess.run(
            ["xdg-settings", "get", "default-web-browser"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def pick_browser(cfg):
    """The browser argv: config `browser` when it is an argv list, else the Omarchy default
    when it is Chromium-family, else `chromium`; None when no desktop file yields a binary."""
    raw = (cfg or {}).get("browser")
    if isinstance(raw, list) and raw and all(isinstance(x, str) and x for x in raw):
        return list(raw)
    browser_id = _default_browser_id()
    if browser_id == HANDLER_ID:
        # Setup made this plugin the default; the browser it displaced is on record.
        browser_id = state.read_entries().get("previous_handler") or ""
    if not browser_id.startswith(CHROMIUM_FAMILY):
        browser_id = DEFAULT_BROWSER_ID
    argv = exec_argv(browser_id)
    return argv[:1] if argv else None


def profile_dir():
    return data_home() / "omarchy" / "distraction-space" / "browser"


def profile_flags(url):
    return [f"--user-data-dir={profile_dir()}", f"--profile-directory={PROFILE}", f"--app={url}"]


NEW_PROFILE_PREFERENCES = {"browser": {"check_default_browser": False}}


def ensure_profile():
    """Create the distraction profile with Chrome's default-browser prompt off, once.

    Chrome asks per profile and rewrites `Preferences` on exit, so the key is
    written only when the profile directory does not exist yet, before the
    first launch; an existing directory is the person's and is never touched.
    A directory that cannot be made is left to the browser, which creates it.
    """
    profile = profile_dir() / PROFILE
    try:
        profile.mkdir(parents=True)
    except FileExistsError:
        return
    except OSError as e:
        _log(f"{profile}: {e}")
        return
    try:
        state.write_json(profile / "Preferences", NEW_PROFILE_PREFERENCES)
    except OSError as e:
        _log(f"{profile / 'Preferences'}: {e}")


# --- launching ---------------------------------------------------------------

def _settle_seconds():
    try:
        return max(0.0, float(os.environ.get("DS_LAUNCH_SETTLE", "1.0")))
    except ValueError:
        return 1.0


def _detached(argv, program=None, env=None):
    """Start argv in its own session with its streams closed; False when it did not start.

    `program` is the binary whose start is being judged when argv wraps it (the
    scope launcher in front of a browser): it must resolve to an executable
    first. Then the child gets a short settle window: one that exits non-zero
    within it did not start; one that exits zero at once handed off to a
    running instance; one still running is up. A missing binary is not the only
    way a launch fails (permission, EMFILE), so the guard is `OSError`.
    """
    target = program or argv[0]
    if not shutil.which(target):
        _log(f"{target}: not an executable on PATH")
        return False
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, env=env,
        )
    except OSError as e:
        _log(f"{argv[0]}: {e}")
        return False
    try:
        rc = proc.wait(timeout=_settle_seconds())
    except subprocess.TimeoutExpired:
        return True
    if rc != 0:
        _log(f"{target}: exited {rc} at start")
        return False
    return True


def launch_in_slice(argv):
    """Run argv as a transient scope in the slice, detached.

    `systemd-run --scope` blocks until its child exits, so it is never waited on.
    A Chromium that hands the launch to its running instance exits at once and
    the scope ends empty; that is not a failure.
    """
    return _detached(SCOPE_ARGV + list(argv), program=argv[0])


def profile_class(host):
    return re.compile(r"^[a-z-]+-" + re.escape(host) + "__-" + re.escape(PROFILE) + "$")


def focus_window_lua(address):
    """`hyprctl dispatch` argument on the Lua parser: focus one window by address."""
    return f"hl.dsp.focus({{ window = {hypr.lua_string(f'address:{address}')} }})"


def find_window(host, clients):
    pat = profile_class(host)
    for c in clients if isinstance(clients, list) else []:
        if isinstance(c, dict) and pat.match(c.get("class") or "") and c.get("address"):
            return c
    return None


def focus_existing(host):
    """True when a distraction-profile window for `host` exists and was put in front on the space.

    The window is moved to the space silently when it is elsewhere and focused
    only when the person is already on the space, so their workspace never
    changes underneath them.
    """
    try:
        clients = hypr.hyprctl_json("clients")
    except Exception as e:
        _log(f"hyprctl clients: {e}")
        return False
    client = find_window(host, clients)
    if client is None:
        return False
    address = client["address"]
    ws = client.get("workspace")
    if not (isinstance(ws, dict) and ws.get("name") == hypr.SPACE):
        hypr.move_to_space(address)
    if hypr.on_space() is True:
        hypr._run("dispatch", focus_window_lua(address))
    return True


def _open_web(target, cfg):
    host = urlsplit(target.url).hostname or ""
    if focus_existing(host):
        return 0
    browser = pick_browser(cfg)
    if browser is None:
        _notice("No distraction browser", "No Chromium-family browser was found. Set `browser` in the config.")
        return 1
    ensure_profile()
    if launch_in_slice(browser + profile_flags(target.url)):
        return 0
    _notice("Distraction space", f"{browser[0]} could not be started in the slice.")
    return 1


def _open_native(target):
    # Setup puts this plugin's own `distractions open <name>` entry in front of
    # the app's system entry; the launch must reach the app, never itself.
    argv = exec_argv(target.desktop, skip_own=True)
    if argv is None:
        _notice("Distraction space", f"{target.desktop}.desktop has no usable Exec line.")
        return 1
    if launch_in_slice(argv):
        return 0
    _notice("Distraction space", f"{argv[0]} could not be started in the slice.")
    return 1


def forward(url=None, flags=(), app=False):
    """Hand what the space does not own to the previous handler, never inside the slice.

    The handler's Exec carries `url` in its field code, or loses the code when
    there is none, the way `omarchy-launch-browser` runs a browser bare; with
    `app` the URL goes after the Exec as `--app=<url>` instead, the way
    `omarchy-launch-webapp` runs it. `flags` are appended verbatim. No usable
    previous handler (none recorded, this plugin's own entry, an Exec that does
    not parse) falls back to `omarchy-launch-browser` with `BROWSER` dropped;
    that script resolves the default browser again, so when the default is
    this plugin the fallback would only come straight back, and nothing is
    launched: exit 1 with one line, as when the script is missing.
    """
    handler = state.read_entries()["previous_handler"]
    argv = env = None
    if handler and handler != HANDLER_ID:
        argv = exec_argv(handler, None if app else url, skip_own=True)
        if argv is None:
            _log(f"{handler} has no usable Exec line; forwarding through {FALLBACK_FORWARDER}")
    if argv is None:
        if _default_browser_id() == HANDLER_ID:
            _notice("Link not forwarded", f"no previous browser is recorded and {FALLBACK_FORWARDER} would resolve to this plugin again; rerun: distractions setup")
            return 1
        argv = [FALLBACK_FORWARDER] + ([] if url is None or app else [url])
        env = dict(os.environ)
        env.pop("BROWSER", None)
    if app and url is not None:
        argv.append(f"--app={url}")
    argv.extend(flags)
    if _detached(argv, env=env):
        return 0
    _notice("Link not forwarded", f"{argv[0]} could not be started.")
    return 1


def _read_cfg():
    try:
        return config.load()
    except Exception:
        return dict(config.DEFAULTS)


def _expansion(cfg):
    exp = state.read_expansion()
    if exp is not None:
        return exp
    return {"list": catalog.expand(cfg)}


def open_target(arg=None, app=False, flags=()):
    """0 when something was launched or forwarded, 1 when nothing could be, 2 for a malformed target.

    No target forwards bare; an unlisted URL forwards, as an app window with
    `app`; a listed or catalog target opens in the space, where `app` changes
    nothing (the space always opens app windows) and `flags` are not applied.
    """
    flags = list(flags)
    if arg is None:
        return forward(None, flags)
    cfg = _read_cfg()
    target = resolve_target(arg, _expansion(cfg), catalog.load_catalog())
    if target is None:
        print(USAGE, file=sys.stderr)
        return 2
    if target.kind == "forward":
        return forward(target.url, flags, app)
    if flags:
        _log(f"{target.entry.get('name')}: {' '.join(flags)} not applied; a space launch has its own flags")
    if not target.restricted:
        _log(f"{target.entry.get('name')} is not in the list; the launch is not network-restricted")
    if target.kind == "native":
        return _open_native(target)
    return _open_web(target, cfg)


def cmd_open(args):
    return open_target(args.target, app=args.app, flags=getattr(args, "flags", ()))
