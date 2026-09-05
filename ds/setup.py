"""Privileged wrapper install and removal, the slice unit, launcher entries and the URL handler, the notification-service clone, then plugin rescan."""

from __future__ import annotations

import hashlib
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from ds import catalog, cgroup, config, launch, state

ROOT = Path(__file__).resolve().parent.parent
WRAPPER_DEFAULT = "/usr/local/libexec/omarchy-distraction-space/distractions-nft"
SUDOERS_DEFAULT = "/etc/sudoers.d/omarchy-distraction-space"
NOTIFICATIONS_SOURCE_DEFAULT = "/usr/share/omarchy/shell/plugins/notifications"
CLONE_SOURCE_ID = "omarchy.notifications"
PATCH = ROOT / "shell" / "notifications-silenced-senders.patch"
# The URL handler's desktop id: the file setup writes, and the value `xdg-settings`
# reports once the plugin is the default browser.
PLUGIN_ID = "io.github.danielkillenberger.distraction-space"
HANDLER_ID = launch.HANDLER_ID
assert HANDLER_ID == PLUGIN_ID + ".desktop"
HANDLER_MIME = "x-scheme-handler/http;x-scheme-handler/https;"
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
# Root's record of what it installed, beside the wrapper in root's own directory.
# The leading dot keeps it out of the way; the name is never a command.
RECORD_NAME = ".installed.sha256"

# The root half of `setup`, run once through one `sudo`. The wrapper and the grant
# arrive as bytes on stdin, so root never re-opens a pathname the installing account
# can write: the bytes root validates are the bytes root activates, and there is no
# window between the two for a same-UID process to substitute anything.
ROOT_TRANSACTION = r'''
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile

MAGIC = "@MAGIC@"
MAX_PAYLOAD = @MAX_PAYLOAD@
RECORD_NAME = "@RECORD_NAME@"


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
    record_dest = os.path.join(os.path.dirname(wrapper_dest), RECORD_NAME)
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

        # What root just installed, digested and world-readable, written last so it
        # never claims an install that did not finish. The grant is 0440 in a
        # directory the account cannot traverse, so an unprivileged re-run has no
        # other way to learn there is nothing to do -- and learning that must not
        # cost a password. Only root can write here, so the record cannot be forged
        # by the account the grant names.
        record = (
            hashlib.sha256(wrapper).hexdigest() + "\n" + hashlib.sha256(grant).hexdigest() + "\n"
        ).encode("ascii")
        if installed(record_dest) != record:
            fd, tmp = stage(record, wrapper_dir, 0o444)
            staged.append((fd, tmp))
            activate(fd, tmp, record, record_dest, 0o444)
            staged.pop()
            os.close(fd)
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
'''.replace("@MAGIC@", PAYLOAD_MAGIC).replace("@MAX_PAYLOAD@", str(MAX_PAYLOAD)).replace(
    "@RECORD_NAME@", RECORD_NAME
)


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


def _record_dest(wrapper_path: Path) -> Path:
    return wrapper_path.parent / RECORD_NAME


def _already_current(source: bytes, grant: bytes, wrapper_path: Path) -> bool:
    """True when this install is already the one on disk, decided without privilege.

    The transaction is a no-op when both files match, but reaching it costs a
    password once the sudo timestamp has expired, so a matching re-run has to be
    recognised before sudo is invoked at all. The wrapper is 0755 and root-owned,
    so its bytes are read and compared directly. The grant cannot be: it is 0440
    in `/etc/sudoers.d`, which the account cannot even traverse. Root's record --
    written last, in root's own directory, world-readable -- is what answers for
    it, and it is compared against the digests of the exact bytes this run would
    install, so a changed wrapper or a re-rendered grant fails the check.

    The gap this leaves is a grant removed out of band: nothing unprivileged can
    see behind `/etc/sudoers.d`, so setup would still skip. `setup --remove` takes
    the record with the grant, and the runtime's `sudo -n` already degrades to
    skip-with-notify when the grant is gone, so the failure is visible and the
    repair is `setup --remove` followed by `setup`.
    """
    record = state.read_bounded(_record_dest(wrapper_path), cap=MAX_PAYLOAD)
    if record is None:
        return False
    want = (
        hashlib.sha256(source).hexdigest() + "\n" + hashlib.sha256(grant).hexdigest() + "\n"
    ).encode("ascii")
    if record != want:
        return False
    return state.read_bounded(wrapper_path, cap=MAX_PAYLOAD) == source


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


def _user_unit_dir() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    base = Path(raw) if raw else Path.home() / ".config"
    return base / "systemd" / "user"


def sync_slice() -> int:
    """Install the slice unit under the user manager and start it. No root, no prompt."""
    source = ROOT / "install" / cgroup.SLICE
    dest = _user_unit_dir() / cgroup.SLICE
    try:
        data = source.read_bytes()
        current = dest.read_bytes() if dest.is_file() else None
        if current != data:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            rc, err = cgroup.systemctl_user("daemon-reload")
            if rc != 0:
                print(err or "systemctl --user daemon-reload failed", file=sys.stderr)
                return 1
    except OSError as e:
        print(f"cannot install {dest}: {e}", file=sys.stderr)
        return 1
    if not cgroup.ensure_slice():
        print(f"systemctl --user start {cgroup.SLICE} failed", file=sys.stderr)
        return 1
    return 0


def remove_slice() -> int:
    """`setup --remove`: stop the slice and drop its unit file.

    An absent unit file means an earlier remove already finished this step; there
    is nothing of ours to stop, and `systemctl stop` on an unloaded unit fails.
    """
    dest = _user_unit_dir() / cgroup.SLICE
    if not dest.exists():
        return 0
    rc, err = cgroup.systemctl_user("stop", cgroup.SLICE)
    if rc != 0:
        print(err or f"systemctl --user stop {cgroup.SLICE} failed", file=sys.stderr)
        return 1
    try:
        dest.unlink()
    except OSError as e:
        print(f"cannot remove {dest}: {e}", file=sys.stderr)
        return 1
    rc, err = cgroup.systemctl_user("daemon-reload")
    if rc != 0:
        print(err or "systemctl --user daemon-reload failed", file=sys.stderr)
        return 1
    return 0


# The data directory and the browser profile have one owner, `ds/launch.py`;
# setup only writes beside what `open` reads.
data_home = launch.data_home
profile_dir = launch.profile_dir


def applications_dir() -> Path:
    """The person's own applications directory: where Omarchy's web apps live and where the entries shadow from."""
    return data_home() / "applications"


def _backup_dir() -> Path:
    return state.state_path("entries-backup")


def _xdg_env() -> dict[str, str]:
    """The environment for `xdg-settings`: the session's, minus `BROWSER`.

    Omarchy exports `BROWSER`, and `xdg-settings` refuses to change or even
    report the default browser while it is set (exit 4). Omarchy's own
    launcher drops the variable for the call; so does this plugin.
    """
    env = dict(os.environ)
    env.pop("BROWSER", None)
    return env


def _xdg_settings(*args: str) -> tuple[int, str]:
    """`xdg-settings` as the person, never through sudo. A missing tool answers like its own exit 3.

    `get` runs on the listener's loop and gets 5 s so a hung tool cannot hold
    it; `set` runs from setup, rewrites mimeapps and the desktop cache, and on
    this machine takes several seconds, so it gets 60 s.
    """
    budget = 60 if args[:1] == ("set",) else 5
    try:
        proc = subprocess.run(
            ["xdg-settings", *args], capture_output=True, text=True, check=False, timeout=budget, env=_xdg_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return 3, ""
    return proc.returncode, (proc.stdout or "").strip()


def default_handler() -> tuple[bool, str | None]:
    """`(answered, id)`: the desktop id `xdg-settings` reports as the default browser.

    `answered` is False when the tool could not say. Nothing that depends on the
    answer may then change the default or delete the file that holds it, since
    there is no record to hand back.
    """
    rc, out = _xdg_settings("get", "default-web-browser")
    if rc != 0:
        return False, None
    return True, (out or None)


def _owned_files(old: dict) -> list[dict] | None:
    """The manifest's files, or None when any entry points outside the plugin's own directories.

    Every path must be a direct child of the applications directory and every
    backup the same name under the backup directory. Anything else is a record
    this plugin did not write, and remove must never unlink or move what it says.
    """
    apps, backups = applications_dir(), _backup_dir()
    out = []
    for item in old["files"]:
        path = Path(item["path"])
        if not path.is_absolute() or path.parent != apps or path.name in ("", ".", ".."):
            return None
        backup = item["backup"]
        if backup is not None and Path(backup) != backups / path.name:
            return None
        out.append({"path": str(path), "backup": backup})
    return out


def _refuse_manifest() -> int:
    print(f"refusing: {state.entries_path()} names files outside {applications_dir()}; "
          "delete or fix that record and rerun", file=sys.stderr)
    return 1


_EXEC_PLAIN = re.compile(r"^[A-Za-z0-9_./:=+@,-]+$")


def _exec_arg(arg: str) -> str:
    """One Exec argument, quoted per the Desktop Entry spec, then escaped once more for the file layer."""
    if _EXEC_PLAIN.match(arg):
        return arg
    quoted = "".join("\\" + c if c in '\\"`$' else c for c in arg)
    return '"' + quoted.replace("\\", "\\\\").replace("%", "%%") + '"'


def _icon_name(name: str) -> str:
    """Omarchy's `safe_icon_name`: the icon its web-app installer fetched for the same product."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _class_prefix(cfg: dict, handler: str | None) -> str:
    """The window-class prefix the distraction browser will carry.

    A configured `browser` argv names the binary `open` runs, so its basename
    decides; otherwise the default browser's desktop id does, the same case list
    `open` follows when the config says `auto`.
    """
    raw = (cfg or {}).get("browser")
    if isinstance(raw, list) and raw and isinstance(raw[0], str) and raw[0]:
        stem = Path(raw[0]).name
    else:
        stem = (handler or "").removesuffix(".desktop")
    if stem.startswith("google-chrome") or stem == "chrome":
        return "chrome"
    for family in ("brave", "microsoft-edge", "opera", "vivaldi", "helium", "chromium"):
        if stem.startswith(family):
            return family
    return "chromium"


def _app_host(entry: dict) -> str | None:
    """The host `open` launches the entry with: the same first host `launch.entry_hosts` picks."""
    hosts = launch.entry_hosts(entry)
    return hosts[0] if hosts else None


def _wm_class(entry: dict, cfg: dict, handler: str | None) -> str | None:
    if entry.get("desktop"):
        klass = (entry.get("classes") or [None])[0]
        return klass if isinstance(klass, str) and _EXEC_PLAIN.match(klass) else None
    host = _app_host(entry)
    return f"{_class_prefix(cfg, handler)}-{host}__-{launch.PROFILE}" if host else None


def _entry_file(entry: dict) -> str:
    """Web products shadow Omarchy's `<Name>.desktop`; native products shadow the system `<id>.desktop`."""
    desktop = entry.get("desktop")
    return f"{desktop}.desktop" if desktop else f"{entry['name']}.desktop"


def _render_entry(entry: dict, cfg: dict, handler: str | None) -> str:
    name = entry["name"]
    exec_line = " ".join(_exec_arg(a) for a in (str(ROOT / "distractions"), "open", name))
    lines = [
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        f"Name={name}",
        f"Comment={name} in the distraction space",
        f"Exec={exec_line}",
        f"Icon={entry.get('desktop') or _icon_name(name)}",
        "Terminal=false",
        "StartupNotify=true",
    ]
    wm = _wm_class(entry, cfg, handler)
    if wm:
        lines.append(f"StartupWMClass={wm}")
    return "\n".join(lines) + "\n"


def _render_handler() -> str:
    exec_line = " ".join((_exec_arg(str(ROOT / "distractions")), "open", "%u"))
    return "\n".join([
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        "Name=Distraction space",
        "Comment=Opens listed links in the distraction space and forwards the rest",
        f"Exec={exec_line}",
        "Icon=web-browser",
        "Terminal=false",
        "NoDisplay=true",
        f"MimeType={HANDLER_MIME}",
    ]) + "\n"


# Omarchy's web-app launcher: every entry whose Exec starts with it opens in the
# default browser, which is this plugin while links are on.
WEBAPP_LAUNCHER = "omarchy-launch-webapp"
_EXEC_KEY = re.compile(r"^\s*Exec\s*=")
# Entries this process has already reported as left alone: once per setup run,
# once per listener lifetime, never once a minute.
_skipped: set[str] = set()


def _skip(path: Path, why: str) -> None:
    if str(path) not in _skipped:
        _skipped.add(str(path))
        print(f"{path}: {why}; the entry is left alone", file=sys.stderr)


def _is_own(exec_value: str | None) -> bool:
    """True when an Exec value is this plugin's launcher, whichever setup wrote it."""
    return launch._is_own_launcher(launch.parse_exec(exec_value) or [])


def _own_file(path: Path) -> bool:
    return _is_own(launch.read_exec(path))


def _replace_exec(text: str, exec_line: str) -> str | None:
    """`text` with the main group's Exec value replaced and every other byte as it was; None without one."""
    lines, in_main = text.splitlines(keepends=True), False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_main:
                return None
            in_main = stripped == "[Desktop Entry]"
            continue
        if in_main and _EXEC_KEY.match(line):
            ending = line[len(line.rstrip("\r\n")):]
            lines[i] = "Exec=" + exec_line + (ending or "\n")
            return "".join(lines)
    return None


def _forward_entry(path: Path, backup: str | None) -> str | None:
    """The rewrite of an Omarchy web-app entry at `path`, or None when there is none to make.

    Omarchy's file is the one at `path` unless that is this plugin's launcher
    already, in which case it is the backup taken when it was first rewritten.
    Only Exec changes: `distractions open --app <url> [extra]`, the URL and the
    extra arguments carried over through the desktop-entry grammar both ways,
    so an unlisted web app opens in the previous browser as an app window and
    a listed one in the space. One that cannot be parsed is named once.
    """
    source, value = path, launch.read_exec(path)
    if value is None or _is_own(value):
        source = Path(backup) if backup else None
        value = launch.read_exec(source) if source is not None else None
    if value is None:
        return None
    argv, tokens = launch.parse_exec(value), value.split()
    head = argv[0] if argv else tokens[0] if tokens else ""
    if Path(head).name != WEBAPP_LAUNCHER:
        return None
    args = launch.expand_fields(argv[1:]) if argv else []
    data = state.read_bounded(source)
    try:
        text = data.decode("utf-8") if data is not None else None
    except UnicodeDecodeError:
        text = None
    rewritten = None
    if args and text is not None:
        exec_line = " ".join(_exec_arg(a) for a in (str(ROOT / "distractions"), "open", "--app", *args))
        rewritten = _replace_exec(text, exec_line)
    if rewritten is None:
        _skip(source, "the Exec line could not be parsed")
    return rewritten


def _plan(exp: dict, cfg: dict | None, handler: str | None, with_handler: bool, owned: dict[str, str | None]) -> list[tuple[Path, str]]:
    """Every file this run wants under the applications directory, in write order.

    Listed products first, then every Omarchy web-app entry that is not one of
    them, rewritten to forward, then the handler when `with_handler`. `owned`
    is the manifest's path-to-backup map: a rewritten entry's source is its
    backup, since the file at its path is already the rewrite.
    """
    apps, plan, seen = applications_dir(), [], set()
    for entry in exp.get("list") or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        # A name becomes a filename and a desktop-entry value: no path parts, no
        # hidden files, and no control character that could start a second key.
        if not isinstance(name, str) or not name or "/" in name or name.startswith(".") \
                or any(ord(c) < 32 or c == "\x7f" for c in name):
            continue
        path = apps / _entry_file(entry)
        if path in seen:
            continue
        seen.add(path)
        plan.append((path, _render_entry(entry, cfg, handler)))
    try:
        present = sorted(p for p in apps.iterdir() if p.suffix == ".desktop" and p.is_file())
    except OSError:
        present = []
    for path in present:
        if path in seen or path.name == HANDLER_ID:
            continue
        text = _forward_entry(path, owned.get(str(path)))
        if text is not None:
            plan.append((path, text))
    if with_handler:
        plan.append((apps / HANDLER_ID, _render_handler()))
    return plan


def _write_text(path: Path, text: str) -> None:
    """Whole-file replace: a reader sees the old entry or the new one, never a partial."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o755)
        os.replace(tmp, path)
    except OSError:
        _unlink(Path(tmp))
        raise


UDD_TIMEOUT = 60.0


def _update_desktop_database(apps: Path) -> None:
    """Best effort: the entries are already in place and the record written; a slow
    or missing cache refresh changes nothing about what setup owns."""
    tool = shutil.which("update-desktop-database")
    if not tool:
        return
    try:
        subprocess.run([tool, str(apps)], capture_output=True, check=False, timeout=UDD_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"update-desktop-database did not finish: {e}; the menu refreshes on its own later", file=sys.stderr)


def _rollback(journal: list[tuple]) -> None:
    """Undo this run's writes and moves, newest first; the old manifest on disk stays the record.

    Every file this run replaced or dropped was moved aside first, so reversing
    the journal puts the exact pre-run bytes back, owned entries included.
    """
    for step in reversed(journal):
        try:
            if step[0] == "wrote":
                _unlink(Path(step[1]))
            else:
                shutil.move(step[2], step[1])
        except OSError as e:
            print(f"rollback: {e}", file=sys.stderr)


def _write_links(links: str) -> None:
    """`links` in state.json, so `status` answers before the listener's next check rewrites it."""
    current = state.read_state() or {}
    if current.get("links") != links:
        try:
            state.write_state({**current, "links": links})
        except OSError as e:
            print(f"cannot record links in state: {e}", file=sys.stderr)


def _restore_handler(previous: str | None) -> bool:
    """Hand the default browser back; only called while the plugin's handler holds it.

    False means the default still points at the plugin's handler, so the caller
    must leave that handler file in place.
    """
    if not previous:
        print("no previous default browser is recorded; choose one with: xdg-settings set default-web-browser <id>.desktop", file=sys.stderr)
        return False
    rc, _out = _xdg_settings("set", "default-web-browser", previous)
    if rc != 0:
        print(f"xdg-settings could not restore {previous} as the default browser (exit {rc})", file=sys.stderr)
        return False
    return True


def _unchanged(old: dict, owned: dict[str, str | None], plan: list[tuple[Path, str]], previous: str | None) -> bool:
    """True when every planned file already holds its text and the manifest would be rewritten as it is.

    The sync runs once a minute from the listener, so the common case has to
    cost a few reads and no write: no owned file to drop, every planned file
    byte-for-byte what it would be written as (which also makes it this
    plugin's own, so its backup carries over), and the record the same.
    """
    wanted = {str(path) for path, _text in plan}
    if any(path not in wanted for path in owned):
        return False
    files = []
    for path, text in plan:
        if state.read_bounded(path) != text.encode("utf-8"):
            return False
        files.append({"path": str(path), "backup": owned.get(str(path))})
    return old == {"files": files, "previous_handler": previous}


def _sync_files(old: dict, owned: dict[str, str | None], plan: list[tuple[Path, str]], previous: str | None) -> int:
    """The plan written under the applications directory and recorded, finished or rolled back as one.

    A file at a planned path that is not this plugin's launcher is Omarchy's (or
    the person's): it is moved whole into `entries-backup/` and recorded beside
    the entry, replacing an older backup, so the backup is always the latest
    entry the plugin displaced; nothing this plugin did not write is ever edited
    or deleted. An owned path the plan no longer carries hands back what it
    shadowed, unless its launcher is already gone: a launcher the person removed
    shadows nothing, and bringing its backup back would resurrect the web app
    they removed, so the backup goes with the record. The manifest is written
    last, after every file it names. Nothing to change is nothing written.
    """
    if _unchanged(old, owned, plan, previous):
        return 0
    wanted = {str(path) for path, _text in plan}
    apps, backups, journal, files, staged = applications_dir(), _backup_dir(), [], [], []

    def move(src: Path, dst: Path) -> None:
        shutil.move(str(src), str(dst))
        journal.append(("moved", str(src), str(dst)))

    def stage(path: Path) -> None:
        # A file about to be replaced or dropped is moved aside whole, so a
        # rollback puts its exact bytes back and success discards the copy.
        backups.mkdir(parents=True, exist_ok=True)
        dest = backups / f".stage-{path.name}"
        _unlink(dest)
        move(path, dest)
        staged.append(dest)

    def held(backup: str | None) -> bool:
        return bool(backup) and (Path(backup).exists() or Path(backup).is_symlink())

    try:
        apps.mkdir(parents=True, exist_ok=True)
        for path_s, backup in owned.items():
            if path_s in wanted:
                continue
            path = Path(path_s)
            present = path.is_file() or path.is_symlink()
            if present:
                stage(path)
            if held(backup):
                move(Path(backup), path) if present else stage(Path(backup))
        for path, text in plan:
            backup = owned.get(str(path))
            # A file or link is moved aside whole; anything else (a directory) is
            # not a launcher entry and the write below refuses it.
            present = path.is_file() or path.is_symlink()
            if present and not _own_file(path):
                if held(backup):
                    stage(Path(backup))
                backups.mkdir(parents=True, exist_ok=True)
                dest = backups / path.name
                move(path, dest)
                backup = str(dest)
            elif present:
                stage(path)
            _write_text(path, text)
            journal.append(("wrote", str(path)))
            files.append({"path": str(path), "backup": backup})
        state.write_entries({"files": files, "previous_handler": previous})
    except OSError as e:
        print(f"cannot write launcher entries under {apps}: {e}", file=sys.stderr)
        _rollback(journal)
        return 1
    for dest in staged:
        _unlink(dest)
    _update_desktop_database(apps)
    return 0


def refresh_entries(exp: dict, cfg: dict | None) -> int:
    """The listener's half of the entry sync: what setup wrote, kept written.

    Runs on `refresh` and once a period, so an entry Omarchy regenerates (a web
    app installed or reinstalled) is rewritten within a minute. Only once setup
    has written the manifest, and never the default browser: the handler file
    stays exactly as recorded, the recorded previous handler stands, and
    `xdg-settings` is not asked, so a default the person moved elsewhere is the
    link check's notice and never fought over here.
    """
    if not state.entries_path().exists():
        return 0
    old = state.read_entries()
    owned_files = _owned_files(old)
    if owned_files is None:
        return _refuse_manifest()
    owned = {item["path"]: item["backup"] for item in owned_files}
    holds = any(Path(p).name == HANDLER_ID for p in owned)
    previous = old["previous_handler"]
    return _sync_files(old, owned, _plan(exp, cfg, previous, holds, owned), previous)


def sync_entries(exp: dict, cfg: dict) -> int:
    """Launcher entries, the rewritten Omarchy web apps, and the URL handler, then the default browser.

    The files are `_sync_files`' one transaction; only after the manifest names
    every one of them is the default browser switched.
    """
    old = state.read_entries()
    owned_files = _owned_files(old)
    if owned_files is None:
        return _refuse_manifest()
    owned = {item["path"]: item["backup"] for item in owned_files}
    answered, handler = default_handler()
    if answered and handler and handler != HANDLER_ID:
        previous = handler
    else:
        previous = old["previous_handler"]
    # Switching links off while the default still points at the handler: hand
    # the default back BEFORE the handler file goes, and keep the file whenever
    # that cannot be shown to have happened.
    keep_handler = False
    if not cfg["open_links_in_space"]:
        holds = any(Path(p).name == HANDLER_ID for p in owned)
        if answered and handler == HANDLER_ID:
            keep_handler = not _restore_handler(old["previous_handler"])
        elif not answered and holds:
            keep_handler = True
    plan = _plan(exp, cfg, previous, cfg["open_links_in_space"] or keep_handler, owned)
    if _sync_files(old, owned, plan, previous) != 0:
        return 1
    if not cfg["open_links_in_space"]:
        if keep_handler:
            print("links: displaced -- the default browser still points at the handler, so the handler "
                  "stays until it is handed back; rerun: distractions setup", file=sys.stderr)
            _write_links("displaced")
        else:
            _write_links("off")
        return 0
    if not answered:
        print("links: displaced -- xdg-settings could not report the default browser, so it was left alone; "
              "rerun: distractions setup", file=sys.stderr)
        _write_links("displaced")
        return 0
    rc = 0
    if handler != HANDLER_ID:
        rc, _out = _xdg_settings("set", "default-web-browser", HANDLER_ID)
    if rc != 0:
        print(f"links: displaced -- xdg-settings could not make {HANDLER_ID} the default browser (exit {rc}); rerun: distractions setup", file=sys.stderr)
    _write_links("on" if rc == 0 else "displaced")
    return 0


def remove_entries() -> int:
    """`setup --remove`: the previous default back, exactly the manifest's files gone, every backup home."""
    old = state.read_entries()
    files = _owned_files(old)
    if files is None:
        return _refuse_manifest()
    if files:
        # The handler file is deleted below, so the default must be known to point
        # elsewhere first: an unanswered query or a failed restore keeps everything.
        answered, handler = default_handler()
        if not answered:
            print("xdg-settings could not report the default browser; the launcher entries and the "
                  "handler stay in place until it can", file=sys.stderr)
            return 1
        if handler == HANDLER_ID and not _restore_handler(old["previous_handler"]):
            print("the default browser still points at the handler; nothing was removed", file=sys.stderr)
            return 1
    try:
        for item in files:
            path = Path(item["path"])
            present = path.is_file() or path.is_symlink()
            _unlink(path)
            if item["backup"]:
                backup = Path(item["backup"])
                if not (backup.exists() or backup.is_symlink()):
                    print(f"backup {backup} is missing; {path} stays removed", file=sys.stderr)
                elif present:
                    shutil.move(str(backup), str(path))
                else:
                    # The launcher was removed by hand (or by Omarchy's web-app
                    # remover); its backup would only bring that web app back.
                    backup.unlink()
        _unlink(state.entries_path())
        if files:
            _update_desktop_database(applications_dir())
    except OSError as e:
        print(f"cannot remove launcher entries: {e}", file=sys.stderr)
        return 1
    try:
        _backup_dir().rmdir()
    except OSError:
        pass
    _write_links("off")
    prof = profile_dir()
    if prof.exists():
        print(f"kept the browser profile at {prof}")
    return 0


def _load_cfg() -> dict | None:
    try:
        return config.load()
    except Exception as e:
        print(f"{e}; launcher entries and the link handler are left as they are", file=sys.stderr)
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
    grant_bytes = grant.encode("utf-8")
    if not _already_current(source, grant_bytes, wrapper):
        if _root_transaction(source, grant_bytes, wrapper, sudoers) != 0:
            print("sudo setup transaction failed", file=sys.stderr)
            return 1
    slice_rc = sync_slice()
    cfg = _load_cfg()
    entries_rc = sync_entries({"list": catalog.expand(cfg)}, cfg) if cfg is not None else 1
    clone_rc = sync_clone()
    rescan_rc = _rescan()
    if rescan_rc == 0:
        _settle_service()
    return 1 if rescan_rc != 0 or clone_rc != 0 or slice_rc != 0 or entries_rc != 0 else 0


def remove():
    # The user-level half first, in reverse of install: nothing here needs root,
    # so a person whose grant is already gone still gets their launcher back.
    if remove_entries() != 0:
        return 1
    wrapper = wrapper_dest()
    sudoers = _sudoers_dest()
    # The root half is installed and removed as one set: wrapper, grant, and the
    # record beside the wrapper. The grant's directory cannot be read from here,
    # so the two files next to each other stand for the set. When both are gone
    # an earlier remove already finished this half, and calling sudo again would
    # only fail once the grant that made it passwordless is gone with it.
    root_half = wrapper.is_file() or _record_dest(wrapper).is_file()
    if root_half:
        # `flush ds` destroys the table outright and needs no slice.
        proc = subprocess.run(
            ["sudo", "-n", str(wrapper), "flush", "ds"],
            capture_output=True,
            text=True,
            check=False,
        )
        if not _flush_ok(proc):
            print((proc.stderr or "nft flush failed").strip() or "nft flush failed", file=sys.stderr)
            return 1
    # The slice goes before the root teardown: while the wrapper and its grant
    # still exist a retry can flush again, so a failure here leaves remove
    # repeatable instead of half done.
    if remove_slice() != 0:
        return 1
    if root_half:
        proc = subprocess.run(
            ["sudo", "rm", "-f", str(wrapper), str(sudoers), str(_record_dest(wrapper))],
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
