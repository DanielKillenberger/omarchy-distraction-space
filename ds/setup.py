"""Privileged wrapper install and removal, the notification-service clone, then plugin rescan."""

from __future__ import annotations

import hashlib
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ds import state

ROOT = Path(__file__).resolve().parent.parent
WRAPPER_DEFAULT = "/usr/local/libexec/omarchy-distraction-space/distractions-nft"
SUDOERS_DEFAULT = "/etc/sudoers.d/omarchy-distraction-space"
NOTIFICATIONS_SOURCE_DEFAULT = "/usr/share/omarchy/shell/plugins/notifications"
CLONE_SOURCE_ID = "omarchy.notifications"
PATCH = ROOT / "shell" / "notifications-silenced-senders.patch"
# The IPC method the shipped patch adds; its presence in the first-party
# Service.qml means Omarchy carries the change and the clone is redundant.
METHOD_MARK = "function silencedSenders("


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


def _shell(*args: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["omarchy-shell", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 1, "", "omarchy-shell missing"
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _rescan() -> int:
    rc, out, err = _shell("shell", "rescanPlugins")
    if rc != 0:
        print(err or out or "rescan failed", file=sys.stderr)
        return 1
    return 0


def notifications_source() -> Path:
    """First-party notification plugin directory the clone is taken from."""
    return Path(os.environ.get("DS_NOTIFICATIONS_SOURCE", NOTIFICATIONS_SOURCE_DEFAULT))


def clone_dir() -> Path:
    """Where `omarchy plugin clone` puts the clone: ~/.config/omarchy/plugins/<user>.notifications."""
    user = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
    return Path.home() / ".config" / "omarchy" / "plugins" / f"{user}.notifications"


def _record_path() -> Path:
    return state.state_path("clone.json")


def _read_record() -> dict | None:
    """The clone record, only when it names this exact clone; anything else is not ours."""
    record, path = state.read_json(_record_path(), None), clone_dir()
    if (
        isinstance(record, dict)
        and record.get("plugin") == path.name
        and record.get("path") == str(path)
        and isinstance(record.get("files"), dict)
        and isinstance(record.get("patch"), str)
    ):
        return record
    return None


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _fingerprint(source: Path) -> dict:
    """SHA-256 of every first-party file the clone copies, plus the shipped patch."""
    files = {}
    for p in sorted(source.rglob("*")):
        if p.is_file():
            files[p.relative_to(source).as_posix()] = _sha256(p)
    return {"files": files, "patch": _sha256(PATCH)}


def _builtin_has_method(source: Path) -> bool:
    try:
        return METHOD_MARK in (source / "Service.qml").read_text(encoding="utf-8")
    except OSError:
        return False


def _patch(dest: Path, *, dry_run: bool) -> bool:
    cmd = ["patch", "-p1", "-d", str(dest), "--no-backup-if-mismatch", "-r", "-"]
    if dry_run:
        cmd.append("--dry-run")
    try:
        with PATCH.open("rb") as f:
            proc = subprocess.run(cmd, stdin=f, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        print(f"patch step unavailable: {e.filename}", file=sys.stderr)
        return False
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout).strip(), file=sys.stderr)
        return False
    return True


def _remove_clone(path: Path) -> bool:
    """Hand the `notifications` target back to the built-in, then drop the clone and its record.

    Enabling a clone puts the built-in on the shell's disabledPlugins list, so
    the directory is only deleted once the shell has restored the built-in;
    otherwise the machine would be left without a notification server.
    """
    rc, out, err = _shell("shell", "setPluginEnabled", path.name, "false")
    if rc != 0:
        print(err or out or "omarchy-shell setPluginEnabled failed", file=sys.stderr)
        return False
    try:
        shutil.rmtree(path)
    except OSError as e:
        print(f"cannot remove {path}: {e}", file=sys.stderr)
        return False
    _unlink(_record_path())
    return True


def _unavailable(reason: str) -> None:
    print(f"notification hold unavailable: {reason}", file=sys.stderr)


def sync_clone() -> int:
    """Keep the patched notification-service clone in step with the built-in.

    Runs between the wrapper step and the rescan. The clone exists only while
    the built-in lacks `silencedSenders`; `clone.json` records what it was
    made from so an Omarchy update (drift) triggers a re-clone.
    """
    source, path, record = notifications_source(), clone_dir(), _read_record()
    ours = record is not None and path.is_dir()
    if not (source / "Service.qml").is_file():
        _unavailable(f"{source} is missing")
        return 0
    if _builtin_has_method(source):
        if ours:
            if not _remove_clone(path):
                return 1
            print(f"removed {path.name}: the built-in now provides silencedSenders", file=sys.stderr)
        _unlink(_record_path())
        return 0
    if path.exists() and not ours:
        _unavailable(f"{path} was not created by this plugin and is left alone")
        return 0
    want = _fingerprint(source)
    if ours and record.get("files") == want["files"] and record.get("patch") == want["patch"]:
        return 0
    if not _patch(source, dry_run=True):
        if ours and not _remove_clone(path):
            return 1
        _unlink(_record_path())
        _unavailable("the shipped patch no longer applies to the first-party files; refresh it and rerun setup")
        return 1
    if ours and not _remove_clone(path):
        return 1
    try:
        proc = subprocess.run(
            ["omarchy-plugin-clone", CLONE_SOURCE_ID],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        _unavailable("omarchy-plugin-clone missing")
        return 1
    if proc.returncode != 0 or not path.is_dir():
        _unavailable((proc.stderr or proc.stdout or "omarchy-plugin-clone failed").strip())
        # The tool can fail after creating and enabling the clone (its closing
        # notification, say); an unrecorded clone left behind would read as
        # foreign on the next run, so take it down now.
        if path.exists() and not _remove_clone(path):
            _unavailable(f"{path} is left over from the failed clone; remove it by hand and rerun setup")
        return 1
    return _finish_clone(path, source, want)


def _finish_clone(path: Path, source: Path, want: dict) -> int:
    """Patch the fresh clone and record it; any failure hands the target back to the built-in."""
    if _patch(path, dry_run=True) and _patch(path, dry_run=False):
        try:
            state.write_json(_record_path(), {"plugin": path.name, "path": str(path), "source": str(source), **want})
            return 0
        except OSError as e:
            print(f"cannot write {_record_path()}: {e}", file=sys.stderr)
    if _remove_clone(path):
        _unavailable("the clone could not be completed; the built-in is back")
    else:
        _unavailable(f"{path} could not be removed; remove it by hand and rerun setup")
    return 1


def remove_clone() -> int:
    """`setup --remove`: drop the clone only when this plugin created it."""
    path, record = clone_dir(), _read_record()
    if record is not None and path.is_dir():
        return 0 if _remove_clone(path) else 1
    if path.exists():
        print(f"leaving {path}: not created by this plugin", file=sys.stderr)
    _unlink(_record_path())
    return 0


def clone_drift() -> str | None:
    """Why the recorded clone no longer matches the first-party files, or None.

    Read-only: the listener shows this once at start; only `setup` re-clones,
    because the notification server changes hands during the rescan.
    """
    record = _read_record()
    if record is None:
        return None
    source = notifications_source()
    if not clone_dir().is_dir():
        return "the clone is missing"
    if _builtin_has_method(source):
        return "the built-in now provides silencedSenders"
    want = _fingerprint(source)
    if record.get("files") != want["files"] or record.get("patch") != want["patch"]:
        return "the first-party notification files or the shipped patch changed"
    return None


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
    clone_rc = sync_clone()
    return 1 if _rescan() != 0 or clone_rc != 0 else 0


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
    clone_rc = remove_clone()
    return 1 if _rescan() != 0 or clone_rc != 0 else 0


def cmd_setup(args):
    if args.remove:
        return remove()
    return install()
