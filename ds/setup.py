"""Privileged wrapper install and removal, then plugin rescan."""

from __future__ import annotations

import os
import pwd
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRAPPER_DEFAULT = "/usr/local/libexec/omarchy-distraction-space/distractions-nft"
SUDOERS_DEFAULT = "/etc/sudoers.d/omarchy-distraction-space"


def wrapper_dest() -> Path:
    """Installed wrapper path; the sudoers grant names exactly this path."""
    return Path(os.environ.get("DS_WRAPPER_DEST", WRAPPER_DEFAULT))


def _sudoers_dest() -> Path:
    return Path(os.environ.get("DS_SUDOERS_DEST", SUDOERS_DEFAULT))


def _principal() -> str | None:
    try:
        name = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        name = ""
    if not name or name == "ALL" or name.startswith("%") or name == "__INSTALL_USER__":
        print("refused: invalid sudoers principal", file=sys.stderr)
        return None
    if any(c in name for c in " \t:+#!"):
        print("refused: invalid sudoers principal", file=sys.stderr)
        return None
    return name


def _writable_ancestor(dest: Path) -> bool:
    for p in dest.parents:
        try:
            if p.exists() and os.access(p, os.W_OK):
                return True
        except OSError:
            return True
    return False


def _install_if_changed(src: Path, dest: Path, mode: str, *, mkdir: bool) -> int:
    inner = (
        f'install -D -m {mode} "$1" "$2"'
        if mkdir
        else f'install -m {mode} "$1" "$2"'
    )
    script = f'cmp -s "$1" "$2" 2>/dev/null || {inner}'
    proc = subprocess.run(
        ["sudo", "sh", "-c", script, "sh", str(src), str(dest)],
        check=False,
    )
    return proc.returncode


def _flush_ok(proc) -> bool:
    if proc.returncode == 0:
        return True
    text = f"{proc.stderr or ''}{proc.stdout or ''}".lower()
    return "no such file or directory" in text or "does not exist" in text


def _rescan() -> int:
    try:
        proc = subprocess.run(
            ["omarchy-shell", "shell", "rescanPlugins"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("omarchy-shell missing", file=sys.stderr)
        return 1
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "rescan failed").strip()
        print(err or "rescan failed", file=sys.stderr)
        return 1
    return 0


def install():
    wrapper = wrapper_dest()
    sudoers = _sudoers_dest()
    if _writable_ancestor(wrapper) or _writable_ancestor(sudoers):
        print("refusing user-writable destination chain", file=sys.stderr)
        return 1
    principal = _principal()
    if principal is None:
        return 1
    shipped = ROOT / "distractions-nft"
    grant = (ROOT / "install" / "sudoers.omarchy-distraction-space").read_text(encoding="utf-8")
    grant = grant.replace("__INSTALL_USER__", principal)
    if "__INSTALL_USER__" in grant or not principal:
        print("refused: sudoers render", file=sys.stderr)
        return 1
    if _install_if_changed(shipped, wrapper, "0755", mkdir=True) != 0:
        print("sudo install wrapper failed", file=sys.stderr)
        return 1
    fd, tmp = tempfile.mkstemp(prefix="ds-sudoers.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(grant)
            fd = -1
        try:
            visudo = subprocess.run(
                ["visudo", "-cf", tmp],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            print("visudo missing", file=sys.stderr)
            return 1
        if visudo.returncode != 0:
            print((visudo.stderr or "visudo failed").strip(), file=sys.stderr)
            return 1
        if _install_if_changed(Path(tmp), sudoers, "0440", mkdir=False) != 0:
            print("sudo install sudoers failed", file=sys.stderr)
            return 1
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return _rescan()


def remove():
    wrapper = wrapper_dest()
    sudoers = _sudoers_dest()
    proc = subprocess.run(
        ["sudo", "-n", str(wrapper), "flush", "ds"],
        capture_output=True,
        text=True,
        check=False,
    )
    if not _flush_ok(proc):
        print((proc.stderr or "nft flush failed").strip() or "nft flush failed", file=sys.stderr)
        return 1
    proc = subprocess.run(
        ["sudo", "rm", "-f", str(wrapper), str(sudoers)],
        check=False,
    )
    if proc.returncode != 0:
        print("sudo rm failed", file=sys.stderr)
        return 1
    return _rescan()


def cmd_setup(args):
    if args.remove:
        return remove()
    return install()
