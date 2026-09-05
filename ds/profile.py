"""`distractions profile import`: a one-time copy of the existing browser profile into the distraction profile.

The source is the main profile of the browser `open` would pick, or the
directory `--from` names. Both browsers must be closed, checked through `/proc`
(`DS_PROC_ROOT` in tests) and the source's `SingletonLock`, before a byte
moves. The copy skips the caches Chromium regenerates, lands in a temporary
sibling, and is renamed into place only when it completed; an existing
destination is renamed to a dated backup with `--replace` and never deleted.
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

from ds import launch, state

USAGE = "usage: distractions profile import [--from <profile-dir>] [--replace]"
MAIN_PROFILE = "Default"
# Desktop-id prefix -> (user-data directory under ~/.config, main profile inside
# it or "" when the user-data directory is the profile, process names of the
# binary when it runs without --user-data-dir). The same family `launch` accepts.
BROWSERS = {
    "google-chrome": ("google-chrome", MAIN_PROFILE, ("chrome", "google-chrome", "google-chrome-stable", "google-chrome-beta", "google-chrome-unstable")),
    "chromium": ("chromium", MAIN_PROFILE, ("chromium", "chromium-browser")),
    "brave": ("BraveSoftware/Brave-Browser", MAIN_PROFILE, ("brave", "brave-browser", "brave-bin")),
    "microsoft-edge": ("microsoft-edge", MAIN_PROFILE, ("msedge", "microsoft-edge", "microsoft-edge-stable")),
    "opera": ("opera", "", ("opera",)),
    "vivaldi": ("vivaldi", MAIN_PROFILE, ("vivaldi", "vivaldi-bin", "vivaldi-stable")),
    "helium": ("net.imput.helium", MAIN_PROFILE, ("helium",)),
}
# Relative paths inside the profile that Chromium regenerates, plus the singleton
# files a running instance leaves; none of them is carried across.
SKIPPED = frozenset({
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
    "ShaderCache", "GrShaderCache", "Service Worker/CacheStorage", "Service Worker/ScriptCache",
    "SingletonLock", "SingletonSocket", "SingletonCookie",
})
PROGRESS_STEP = 100 * 1024 * 1024


class Refused(Exception):
    """A precondition failed or the copy failed; the message names the reason and the fix."""


def _err(msg):
    print(msg, file=sys.stderr)


def config_home():
    raw = os.environ.get("XDG_CONFIG_HOME")
    return Path(raw) if raw else Path.home() / ".config"


def _proc_root(proc):
    if proc is not None:
        return Path(proc)
    return Path(os.environ.get("DS_PROC_ROOT") or "/proc")


# --- source ------------------------------------------------------------------

def browser_id(cfg):
    """The desktop id `open` resolves to, before its chromium fallback: config `browser`
    as a binary name when it is an argv, else the Omarchy default, else the recorded
    previous handler when this plugin is the default."""
    raw = (cfg or {}).get("browser")
    if isinstance(raw, list) and raw and all(isinstance(x, str) and x for x in raw):
        return Path(raw[0]).name
    bid = launch._default_browser_id()
    if bid == launch.HANDLER_ID:
        bid = state.read_entries().get("previous_handler") or ""
    return bid


def browser_key(bid):
    """The `BROWSERS` key `bid` starts with, or None for a browser without a known profile."""
    for key in BROWSERS:
        if bid.startswith(key):
            return key
    return None


def source_for(cfg):
    """The main profile directory of the browser `open` would pick.

    Raises `Refused` when that browser has no Chromium-family profile to import.
    """
    bid = browser_id(cfg)
    key = browser_key(bid)
    if key is None:
        raise Refused(
            f"{bid or 'the default browser'} is not a Chromium-family browser with a known profile; "
            "only Chromium-family profiles import. Name one with --from <profile-dir>."
        )
    subdir, profile, _names = BROWSERS[key]
    return config_home() / subdir / profile


def user_data_dir_of(src):
    """(user-data directory, browser key) for the canonical profile directory `src`.

    A known browser's user-data directory is matched by its resolved path: the
    profile itself when the browser keeps it at the root (Opera), else its
    parent. Elsewhere the parent is the user-data directory and the browser is
    unknown, so only the `--user-data-dir` and `SingletonLock` checks apply.
    """
    src = Path(src)
    for key, (subdir, profile, _names) in BROWSERS.items():
        udd = (config_home() / subdir).resolve()
        if src == (udd / profile if profile else udd):
            return udd, key
    return src.parent, None


# --- running checks ----------------------------------------------------------

def _cmdline(pid_dir):
    data = state.read_bounded(pid_dir / "cmdline")
    if not data:
        return None
    return [a.decode("utf-8", errors="replace") for a in data.split(b"\0") if a]


def _user_data_dir_arg(argv):
    for arg in argv:
        if arg.startswith("--user-data-dir="):
            return arg[len("--user-data-dir="):]
    return None


def is_running(user_data_dir, proc=None, names=()):
    """Why the browser of `user_data_dir` counts as running, or None when it does not.

    A process of this user carrying `--user-data-dir=<user_data_dir>`, a process
    named in `names` (the browser's binary running with its default directory)
    with no `--user-data-dir` at all, or a `SingletonLock` in the directory whose
    target names a live pid on this host.
    """
    user_data_dir = Path(user_data_dir).resolve()
    root = _proc_root(proc)
    uid = os.getuid()
    try:
        entries = sorted(root.iterdir())
    except OSError:
        entries = []
    for pid_dir in entries:
        if not pid_dir.name.isdigit():
            continue
        try:
            if os.stat(pid_dir).st_uid != uid:
                continue
        except OSError:
            continue
        argv = _cmdline(pid_dir)
        if not argv:
            continue
        udd = _user_data_dir_arg(argv)
        if udd is not None:
            if Path(udd).expanduser().resolve() == user_data_dir:
                return f"pid {pid_dir.name} runs with --user-data-dir={user_data_dir}"
            continue
        if names and Path(argv[0]).name in names:
            return f"pid {pid_dir.name} ({Path(argv[0]).name}) runs on its default profile directory"
    live = _singleton_pid(user_data_dir / "SingletonLock", root)
    if live is not None:
        return f"{user_data_dir / 'SingletonLock'} names live pid {live}"
    return None


def _singleton_pid(lock, root):
    """The pid a live `SingletonLock` names, or None for a missing, foreign-host, or stale lock."""
    try:
        target = os.readlink(lock)
    except OSError:
        return None
    host, sep, pid = target.rpartition("-")
    if not sep or not pid.isdigit() or host != socket.gethostname():
        return None
    return int(pid) if (root / pid).is_dir() else None


# --- the copy ----------------------------------------------------------------

def _contains(a, b):
    return a == b or a in b.parents


def _free_name(path):
    """`path` itself when nothing sits there, else `path-2`, `path-3`, ..."""
    candidate = path
    n = 1
    while candidate.exists() or candidate.is_symlink():
        n += 1
        candidate = path.with_name(f"{path.name}-{n}")
    return candidate


def _copy_file(src, dst):
    shutil.copy2(src, dst)
    return os.lstat(dst).st_size


def copy_profile(src, tmp):
    """`src` into `tmp` minus `SKIPPED`, symlinks preserved; returns the byte count.

    One progress line per `PROGRESS_STEP` bytes on stderr.
    """
    src = Path(src)
    copied = 0
    reported = 0

    def ignore(directory, names):
        rel = Path(directory).relative_to(src)
        skipped = []
        for name in names:
            path = name if rel == Path(".") else f"{rel.as_posix()}/{name}"
            if path in SKIPPED:
                skipped.append(name)
        return skipped

    def copy(s, d):
        nonlocal copied, reported
        copied += _copy_file(s, d)
        while copied - reported >= PROGRESS_STEP:
            reported += PROGRESS_STEP
            _err(f"profile import: {reported // (1024 * 1024)} MB copied")

    shutil.copytree(src, tmp, symlinks=True, ignore=ignore, copy_function=copy, dirs_exist_ok=True)
    return copied


def import_profile(src, dst, replace=False, proc=None):
    """Copy `src` into `dst` after every precondition holds; returns (bytes, seconds).

    Raises `Refused` before any byte moves when a precondition fails, and after
    the copy failed with the temporary sibling (and the backup) named.
    """
    # The source is canonical from here on: a relative or symlinked `--from`
    # must reach the same user-data directory, browser, and lock as the real
    # one. The destination stays lexical: its parent is the `--user-data-dir`
    # `open` passes, and a symlinked `Distraction` is moved aside as the link,
    # never as its target; only the overlap check looks through it.
    src, dst = Path(src).expanduser().resolve(), Path(dst)
    if not (src / "Preferences").is_file():
        raise Refused(f"{src} is not a Chromium profile: it has no Preferences file.")
    if _contains(src, dst.resolve()) or _contains(dst.resolve(), src):
        raise Refused(f"{src} is or contains {dst}; the source and the destination must be separate directories.")
    user_data, key = user_data_dir_of(src)
    names = BROWSERS[key][2] if key else ()
    why = is_running(user_data, proc, names)
    if why is not None:
        raise Refused(f"the source browser is running ({why}); close it and run the import again.")
    why = is_running(dst.parent, proc)
    if why is not None:
        raise Refused(f"the distraction browser is running ({why}); close it and run the import again.")
    if (dst.exists() or dst.is_symlink()) and not replace:
        raise Refused(f"{dst} exists; --replace moves it aside to a dated backup first.")

    # The sibling exists before the destination moves, so a failed copy always
    # has a directory to name and a backup is never made for a copy that could
    # not even start.
    tmp = dst.with_name(f"{dst.name}.import-{os.getpid()}")
    try:
        if tmp.exists() or tmp.is_symlink():
            stale = _free_name(tmp.with_name(tmp.name + ".stale"))
            os.rename(tmp, stale)
            _err(f"profile import: an earlier interrupted copy at {tmp} was moved to {stale}")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        os.mkdir(tmp)
    except OSError as e:
        raise Refused(f"could not prepare the temporary copy at {tmp} ({e}); fix that directory and run the import again.") from e
    backup = None
    if dst.exists() or dst.is_symlink():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = _free_name(dst.with_name(f"{dst.name}.bak-{stamp}"))
        try:
            os.rename(dst, backup)
        except OSError as e:
            os.rmdir(tmp)  # still empty: nothing was copied yet
            raise Refused(f"could not move {dst} aside to {backup} ({e}); the existing profile is untouched.") from e
        _err(f"profile import: the existing profile was moved to {backup}")

    started = time.monotonic()
    try:
        copied = copy_profile(src, tmp)
        os.rename(tmp, dst)
    except (OSError, shutil.Error) as e:
        kept = [f"the partial copy stays at {tmp}"] if tmp.exists() else []
        if backup is not None:
            kept.append(f"the previous profile stays at {backup}")
        raise Refused(f"the copy failed ({e}); {'; '.join(kept) or 'nothing was left behind'}; nothing was written to {dst}.") from e
    elapsed = time.monotonic() - started
    _err(f"profile import: {copied} bytes in {elapsed:.1f} s")
    return copied, elapsed


# --- command -----------------------------------------------------------------

def cmd_import(args):
    dst = launch.profile_dir() / launch.PROFILE
    try:
        source = getattr(args, "source", None)
        src = Path(source).expanduser() if source else source_for(launch._read_cfg())
        copied, _elapsed = import_profile(src, dst, replace=getattr(args, "replace", False))
    except Refused as e:
        _err(f"profile import: {e}")
        return 1
    print(dst)
    print(f"{copied} bytes copied from {src}")
    print("The next `distractions open` registers the profile; your Google account will show as signed in twice.")
    return 0


def cmd_profile(args):
    if getattr(args, "profile_cmd", None) == "import":
        return cmd_import(args)
    _err(USAGE)
    return 2
