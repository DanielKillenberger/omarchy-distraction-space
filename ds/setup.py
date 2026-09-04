"""Privileged wrapper install and removal, the notification-service clone, then plugin rescan."""

from __future__ import annotations

import hashlib
import os
import pwd
import shutil
import stat
import subprocess
import sys
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


# Both payload halves are small: the shipped wrapper is a few KiB and the grant is
# one line. The cap only stops setup from streaming something absurd into root.
MAX_PAYLOAD = 1024 * 1024
PAYLOAD_MAGIC = "ds-setup-1"

# The root half of `setup`, run once through one `sudo`. The wrapper and the grant
# arrive as bytes on stdin, so root never re-opens a pathname the installing account
# can write: the bytes root validates are the bytes root activates, and there is no
# window between the two for a same-UID process to substitute anything.
ROOT_TRANSACTION = r'''
import os
import shutil
import stat
import subprocess
import sys
import tempfile

MAGIC = "@MAGIC@"
MAX_PAYLOAD = @MAX_PAYLOAD@


def fail(message):
    sys.stderr.write("refused: " + message + "\n")
    raise SystemExit(1)


def read_line():
    line = bytearray()
    while len(line) < 64:
        c = os.read(0, 1)
        if not c:
            fail("short payload")
        if c == b"\n":
            return line.decode("ascii", "replace")
        line += c
    fail("bad payload header")


def read_exact(n):
    out = bytearray()
    while len(out) < n:
        chunk = os.read(0, min(65536, n - len(out)))
        if not chunk:
            fail("short payload")
        out += chunk
    return bytes(out)


def installed(path):
    """What the destination already holds, or None. Never followed through a symlink."""
    try:
        # Non-blocking: a fifo left where a destination was would otherwise hold
        # root open at the `open` itself, before fstat could refuse it.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as e:
        fail("cannot read %s: %s" % (path, e))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            fail("%s is not a regular file" % path)
        if st.st_size > MAX_PAYLOAD:
            return b""
        return os.read(fd, MAX_PAYLOAD)
    finally:
        os.close(fd)


def stage(data, directory, mode):
    """A root-owned file in the destination's own directory, held open by descriptor.

    The name carries a dot, which sudo's #includedir skips, so a staged grant is
    never parsed while it waits. The directory is root-only in a real install, so
    the account being granted cannot reach what is staged there.
    """
    fd, tmp = tempfile.mkstemp(prefix=".ds-stage.", dir=directory)
    try:
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
        os.fchmod(fd, mode)
    except OSError as e:
        os.close(fd)
        os.unlink(tmp)
        fail("cannot stage into %s: %s" % (directory, e))
    return fd, tmp


def activate(fd, tmp, data, dest, mode):
    """Revalidate the staged file through its own descriptor, then rename it into place."""
    st, path_st = os.fstat(fd), os.lstat(tmp)
    if (st.st_dev, st.st_ino) != (path_st.st_dev, path_st.st_ino):
        fail("%s was replaced before activation" % tmp)
    if st.st_nlink != 1 or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != mode:
        fail("%s is no longer the file that was checked" % tmp)
    os.lseek(fd, 0, os.SEEK_SET)
    if os.read(fd, len(data) + 1) != data:
        fail("%s changed after validation" % tmp)
    os.rename(tmp, dest)


def main():
    wrapper_dest, sudoers_dest = sys.argv[1], sys.argv[2]
    if read_line() != MAGIC:
        fail("bad payload header")
    try:
        n_wrapper, n_grant = int(read_line()), int(read_line())
    except ValueError:
        fail("bad payload header")
    if not (0 < n_wrapper <= MAX_PAYLOAD and 0 < n_grant <= MAX_PAYLOAD):
        fail("payload out of range")
    wrapper, grant = read_exact(n_wrapper), read_exact(n_grant)

    wrapper_dir, sudoers_dir = os.path.dirname(wrapper_dest), os.path.dirname(sudoers_dest)
    try:
        os.makedirs(wrapper_dir, 0o755, exist_ok=True)
    except OSError as e:
        fail("cannot create %s: %s" % (wrapper_dir, e))
    if not os.path.isdir(sudoers_dir):
        fail("%s is missing" % sudoers_dir)

    staged = []
    try:
        # The grant is staged and validated first, so a rejected grant costs nothing:
        # nothing has moved yet and any prior grant is still the live one.
        grant_fd = grant_tmp = None
        if installed(sudoers_dest) != grant:
            grant_fd, grant_tmp = stage(grant, sudoers_dir, 0o440)
            staged.append((grant_fd, grant_tmp))
            visudo = shutil.which("visudo") or "/usr/sbin/visudo"
            try:
                checked = subprocess.run([visudo, "-cf", grant_tmp], capture_output=True, text=True)
            except OSError:
                fail("visudo missing")
            if checked.returncode != 0:
                fail((checked.stderr or checked.stdout or "visudo rejected the grant").strip())

        # The wrapper lands before the grant that names it, so the path the grant
        # points at is never a name root has promised NOPASSWD on but not written.
        if installed(wrapper_dest) != wrapper:
            fd, tmp = stage(wrapper, wrapper_dir, 0o755)
            staged.append((fd, tmp))
            activate(fd, tmp, wrapper, wrapper_dest, 0o755)
            staged.pop()
            os.close(fd)

        if grant_tmp is not None:
            activate(grant_fd, grant_tmp, grant, sudoers_dest, 0o440)
            staged.pop()
            os.close(grant_fd)
    finally:
        for fd, tmp in staged:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return 0


raise SystemExit(main())
'''.replace("@MAGIC@", PAYLOAD_MAGIC).replace("@MAX_PAYLOAD@", str(MAX_PAYLOAD))


def _pinned_source(path: Path) -> bytes | None:
    """The shipped wrapper's bytes, read through one descriptor that refuses a symlink.

    Root installs these bytes rather than this pathname, so what was checked here is
    what lands: nothing re-resolves the plugin directory, which the user can write.
    """
    try:
        # Non-blocking, so a fifo in the plugin directory cannot stall setup
        # before fstat gets to refuse it.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        print(f"refused: cannot read {path}: {e}", file=sys.stderr)
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            print(f"refused: {path} is not a regular file", file=sys.stderr)
            return None
        data = b""
        while len(data) <= MAX_PAYLOAD:
            chunk = os.read(fd, 65536)
            if not chunk:
                return data
            data += chunk
        print(f"refused: {path} is over {MAX_PAYLOAD} bytes", file=sys.stderr)
        return None
    except OSError as e:
        print(f"refused: cannot read {path}: {e}", file=sys.stderr)
        return None
    finally:
        os.close(fd)


def _root_transaction(wrapper: bytes, grant: bytes, wrapper_path: Path, sudoers_path: Path) -> int:
    """One sudo, one prompt: validate and activate both files inside root.

    Everything privileged happens in this single invocation, so setup asks for a
    password once and a re-run whose bytes already match does no work inside it.
    """
    header = f"{PAYLOAD_MAGIC}\n{len(wrapper)}\n{len(grant)}\n".encode("ascii")
    proc = subprocess.run(
        ["sudo", "python3", "-c", ROOT_TRANSACTION, str(wrapper_path), str(sudoers_path)],
        input=header + wrapper + grant,
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


# Set by sync_clone / remove_clone when the notification service changed hands
# (clone created, re-cloned, or removed). Read once by install/remove.
_service_changed = False


def _settle_service() -> None:
    """Make the running shell match the clone step.

    Verified 2026-09-02: `rescanPlugins` reloads the clone's files but the
    running notification service kept the built-in until the shell restarted.
    When the live answer disagrees with what the clone step left on disk,
    restart the shell once. Best effort: a failed restart is reported, and the
    listener's start-time check names `distractions setup` again.
    """
    global _service_changed
    if not _service_changed:
        return
    _service_changed = False
    expect = _read_record() is not None or _builtin_has_method(notifications_source())
    rc, out, _err = _shell("notifications", "silencedSenders")
    live = rc == 0 and out.startswith("[")
    if live == expect:
        return
    print("the rescan did not swap the notification service; restarting the shell", file=sys.stderr)
    try:
        proc = subprocess.run(
            ["omarchy", "restart", "shell"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"omarchy restart shell: {e}", file=sys.stderr)
        return
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout or "omarchy restart shell failed").strip(), file=sys.stderr)


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
            _mark_changed()
            print(f"removed {path.name}: the built-in now provides silencedSenders", file=sys.stderr)
        elif path.exists():
            # Left alone, but it shadows a built-in that already has the method.
            _unavailable(f"{path} was not created by this plugin and is left alone; it hides the built-in service that now provides silencedSenders")
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


def _mark_changed() -> None:
    global _service_changed
    _service_changed = True


def _finish_clone(path: Path, source: Path, want: dict) -> int:
    """Patch the fresh clone and record it; any failure hands the target back to the built-in."""
    if _patch(path, dry_run=True) and _patch(path, dry_run=False):
        try:
            state.write_json(_record_path(), {"plugin": path.name, "path": str(path), "source": str(source), **want})
            _mark_changed()
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
        if not _remove_clone(path):
            return 1
        _mark_changed()
        return 0
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
    source = _pinned_source(shipped)
    if source is None:
        return 1
    if _root_transaction(source, grant.encode("utf-8"), wrapper, sudoers) != 0:
        print("sudo setup transaction failed", file=sys.stderr)
        return 1
    clone_rc = sync_clone()
    rescan_rc = _rescan()
    if rescan_rc == 0:
        _settle_service()
    return 1 if rescan_rc != 0 or clone_rc != 0 else 0


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
    rescan_rc = _rescan()
    if rescan_rc == 0:
        _settle_service()
    return 1 if rescan_rc != 0 or clone_rc != 0 else 0


def cmd_setup(args):
    if args.remove:
        return remove()
    return install()
